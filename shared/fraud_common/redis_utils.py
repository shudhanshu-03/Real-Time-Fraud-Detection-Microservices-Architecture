"""
redis_utils — Redis utilities for the Real-Time Fraud Detection platform.

Provides production-grade wrappers around ``redis.asyncio`` for common
patterns used across fraud-detection microservices: caching, counters,
sliding-window velocity checks, and distributed locking.

Key components
--------------
* :class:`RedisClient` — async connection-pool wrapper with JSON helpers.
* :class:`VelocityCounter` — sliding-window rate counter backed by sorted
  sets.
* :class:`DistributedLock` — Redis-based distributed lock (Redlock-lite)
  with auto-release.
* :func:`get_redis_client` — factory function driven by service settings.

Usage example::

    from fraud_common.redis_utils import get_redis_client, VelocityCounter

    redis = get_redis_client(settings)
    async with redis:
        vc = VelocityCounter(redis)
        await vc.increment("card", "4111-xxxx", window_seconds=3600)
        count = await vc.get_count("card", "4111-xxxx", window_seconds=3600)
"""

from __future__ import annotations

import json
import time
import uuid
import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional, Union

import redis.asyncio as redis
import structlog

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_REDIS_URL = "redis://localhost:6379/0"
_DEFAULT_POOL_SIZE = 20
_DEFAULT_LOCK_TTL_SECONDS = 30
_DEFAULT_LOCK_RETRY_INTERVAL = 0.1
_DEFAULT_LOCK_RETRY_COUNT = 50


# ---------------------------------------------------------------------------
# RedisClient
# ---------------------------------------------------------------------------


class RedisClient:
    """Async Redis client with connection-pool management and JSON helpers.

    Designed to be used as an **async context manager** so the connection
    pool is cleanly shut down on exit::

        async with RedisClient(url="redis://redis:6379/0") as client:
            await client.set("key", "value", ttl=300)

    Parameters:
        url: Redis connection URL (``redis://host:port/db``).
        max_connections: Maximum size of the connection pool.
        decode_responses: Decode byte responses to ``str``.
        socket_timeout: Per-command socket timeout in seconds.
        socket_connect_timeout: Connection-establishment timeout in seconds.
    """

    def __init__(
        self,
        url: str = _DEFAULT_REDIS_URL,
        max_connections: int = _DEFAULT_POOL_SIZE,
        decode_responses: bool = True,
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 5.0,
    ) -> None:
        self._url = url
        self._max_connections = max_connections
        self._decode_responses = decode_responses
        self._socket_timeout = socket_timeout
        self._socket_connect_timeout = socket_connect_timeout
        self._pool: Optional[redis.ConnectionPool] = None
        self._client: Optional[redis.Redis] = None

    # -- lifecycle / context manager -----------------------------------------

    async def connect(self) -> None:
        """Initialise the connection pool and the Redis client instance.

        Idempotent — calling on an already-connected client is a no-op.
        """
        if self._client is not None:
            return

        self._pool = redis.ConnectionPool.from_url(
            self._url,
            max_connections=self._max_connections,
            decode_responses=self._decode_responses,
            socket_timeout=self._socket_timeout,
            socket_connect_timeout=self._socket_connect_timeout,
        )
        self._client = redis.Redis(connection_pool=self._pool)
        logger.info(
            "redis.connected",
            url=self._url,
            max_connections=self._max_connections,
        )

    async def disconnect(self) -> None:
        """Close all connections in the pool."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        if self._pool is not None:
            await self._pool.disconnect()
            self._pool = None
            logger.info("redis.disconnected", url=self._url)

    async def __aenter__(self) -> "RedisClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.disconnect()

    @property
    def client(self) -> redis.Redis:
        """Return the underlying ``redis.Redis`` instance.

        Raises:
            RuntimeError: If the client has not been connected.
        """
        if self._client is None:
            raise RuntimeError(
                "RedisClient is not connected. "
                "Call connect() or use the async context manager."
            )
        return self._client

    # -- basic operations ----------------------------------------------------

    async def get(self, key: str) -> Optional[str]:
        """Retrieve the string value for *key*, or ``None`` if missing.

        Parameters:
            key: Redis key.

        Returns:
            The stored value, or ``None``.
        """
        try:
            value = await self.client.get(key)
            return value
        except redis.RedisError as exc:
            logger.error("redis.get_failed", key=key, error=str(exc))
            raise

    async def set(
        self,
        key: str,
        value: Union[str, int, float],
        ttl: Optional[int] = None,
    ) -> bool:
        """Set a string *value* on *key* with an optional TTL (seconds).

        Parameters:
            key: Redis key.
            value: Value to store.
            ttl: Time-to-live in seconds.  ``None`` means no expiry.

        Returns:
            ``True`` on success.
        """
        try:
            result = await self.client.set(key, value, ex=ttl)
            logger.debug("redis.set", key=key, ttl=ttl)
            return bool(result)
        except redis.RedisError as exc:
            logger.error("redis.set_failed", key=key, error=str(exc))
            raise

    async def delete(self, key: str) -> int:
        """Delete *key*.

        Parameters:
            key: Redis key to remove.

        Returns:
            Number of keys removed (0 or 1).
        """
        try:
            removed = await self.client.delete(key)
            logger.debug("redis.delete", key=key, removed=removed)
            return int(removed)
        except redis.RedisError as exc:
            logger.error("redis.delete_failed", key=key, error=str(exc))
            raise

    async def incr(self, key: str, ttl: Optional[int] = None) -> int:
        """Atomically increment an integer counter on *key*.

        If *key* does not exist it is initialised to ``0`` before
        incrementing.  When a *ttl* is provided the expiry is set **only
        on the first increment** (i.e. when the value becomes ``1``).

        Parameters:
            key: Redis key.
            ttl: TTL in seconds (set only on key creation).

        Returns:
            The value after incrementing.
        """
        try:
            value = await self.client.incr(key)
            if ttl is not None and value == 1:
                await self.client.expire(key, ttl)
            logger.debug("redis.incr", key=key, value=value)
            return int(value)
        except redis.RedisError as exc:
            logger.error("redis.incr_failed", key=key, error=str(exc))
            raise

    # -- JSON helpers --------------------------------------------------------

    async def get_json(self, key: str) -> Optional[Any]:
        """Retrieve and deserialise a JSON value.

        Parameters:
            key: Redis key.

        Returns:
            The deserialised Python object, or ``None`` if *key* is missing.
        """
        raw = await self.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("redis.get_json_decode_failed", key=key, error=str(exc))
            raise

    async def set_json(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """Serialise *value* as JSON and store it.

        Parameters:
            key: Redis key.
            value: Any JSON-serialisable value.
            ttl: Time-to-live in seconds.

        Returns:
            ``True`` on success.
        """
        try:
            serialised = json.dumps(value, separators=(",", ":"))
            return await self.set(key, serialised, ttl=ttl)
        except (TypeError, ValueError) as exc:
            logger.error("redis.set_json_encode_failed", key=key, error=str(exc))
            raise

    # -- pipeline ------------------------------------------------------------

    def pipeline(self) -> redis.client.Pipeline:
        """Return a pipeline for batching multiple commands.

        Use as an async context manager::

            async with client.pipeline() as pipe:
                pipe.set("a", 1)
                pipe.set("b", 2)
                results = await pipe.execute()

        Returns:
            An ``redis.client.Pipeline`` instance bound to this pool.
        """
        return self.client.pipeline()

    # -- health check --------------------------------------------------------

    async def ping(self) -> bool:
        """Send a ``PING`` to verify connectivity.

        Returns:
            ``True`` if the server responds with ``PONG``.
        """
        try:
            return bool(await self.client.ping())
        except redis.RedisError as exc:
            logger.error("redis.ping_failed", error=str(exc))
            return False


# ---------------------------------------------------------------------------
# VelocityCounter
# ---------------------------------------------------------------------------


class VelocityCounter:
    """Sliding-window rate counter backed by Redis sorted sets.

    Each counter is stored as a sorted set where:

    * **member** = unique event identifier (UUID) to avoid collisions.
    * **score** = event timestamp (epoch seconds).

    To query the count within a window we simply ``ZCOUNT`` scores in
    ``[now - window, now]`` and garbage-collect stale entries.

    Parameters:
        redis_client: A connected :class:`RedisClient`.
        key_prefix: Prefix for all velocity-counter keys.
    """

    def __init__(
        self,
        redis_client: RedisClient,
        key_prefix: str = "fraud:velocity",
    ) -> None:
        self._redis = redis_client
        self._prefix = key_prefix

    def _key(self, entity_type: str, entity_id: str) -> str:
        """Build the Redis key for an entity's velocity counter."""
        return f"{self._prefix}:{entity_type}:{entity_id}"

    async def increment(
        self,
        entity_type: str,
        entity_id: str,
        window_seconds: int,
    ) -> int:
        """Record a new event and return the updated count within *window*.

        Old entries outside the window are pruned automatically.

        Parameters:
            entity_type: Entity category (e.g. ``"card"``, ``"ip"``).
            entity_id: Unique entity identifier.
            window_seconds: Sliding window duration in seconds.

        Returns:
            The number of events in the current window **after** incrementing.
        """
        key = self._key(entity_type, entity_id)
        now = time.time()
        window_start = now - window_seconds
        member = f"{now}:{uuid.uuid4()}"

        pipe = self._redis.pipeline()
        # Remove entries older than the window.
        pipe.zremrangebyscore(key, "-inf", window_start)
        # Add the new event.
        pipe.zadd(key, {member: now})
        # Count remaining events.
        pipe.zcard(key)
        # Set expiry slightly longer than the window to auto-clean.
        pipe.expire(key, window_seconds + 60)
        results = await pipe.execute()

        count: int = int(results[2])
        logger.debug(
            "velocity.increment",
            entity_type=entity_type,
            entity_id=entity_id,
            window_seconds=window_seconds,
            count=count,
        )
        return count

    async def get_count(
        self,
        entity_type: str,
        entity_id: str,
        window_seconds: int,
    ) -> int:
        """Return the number of events within the sliding window.

        Stale entries are pruned before counting.

        Parameters:
            entity_type: Entity category.
            entity_id: Unique entity identifier.
            window_seconds: Sliding window duration in seconds.

        Returns:
            Event count within the window.
        """
        key = self._key(entity_type, entity_id)
        now = time.time()
        window_start = now - window_seconds

        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(key, "-inf", window_start)
        pipe.zcount(key, window_start, "+inf")
        results = await pipe.execute()

        count: int = int(results[1])
        logger.debug(
            "velocity.get_count",
            entity_type=entity_type,
            entity_id=entity_id,
            window_seconds=window_seconds,
            count=count,
        )
        return count

    async def check_threshold(
        self,
        entity_type: str,
        entity_id: str,
        window_seconds: int,
        threshold: int,
    ) -> bool:
        """Check whether the event count meets or exceeds *threshold*.

        Parameters:
            entity_type: Entity category.
            entity_id: Unique entity identifier.
            window_seconds: Sliding window duration in seconds.
            threshold: The limit to compare against.

        Returns:
            ``True`` if ``count >= threshold``.
        """
        count = await self.get_count(entity_type, entity_id, window_seconds)
        exceeded = count >= threshold
        if exceeded:
            logger.warning(
                "velocity.threshold_exceeded",
                entity_type=entity_type,
                entity_id=entity_id,
                window_seconds=window_seconds,
                count=count,
                threshold=threshold,
            )
        return exceeded


# ---------------------------------------------------------------------------
# DistributedLock
# ---------------------------------------------------------------------------


class DistributedLock:
    """Redis-based distributed lock with auto-release.

    Implements the single-node **Redlock** algorithm with a unique lock
    token to prevent accidental release by a different holder.

    Usage::

        lock = DistributedLock(redis_client, "my-resource")
        async with lock:
            # critical section
            ...

    Parameters:
        redis_client: A connected :class:`RedisClient`.
        resource: Unique name of the resource to lock.
        ttl_seconds: Auto-release timeout in seconds.
        retry_count: Number of acquire attempts before giving up.
        retry_interval: Seconds between acquire attempts.
    """

    # Lua script for atomic release — only the holder can unlock.
    _RELEASE_SCRIPT = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """

    # Lua script for atomic TTL extension.
    _EXTEND_SCRIPT = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("pexpire", KEYS[1], ARGV[2])
    else
        return 0
    end
    """

    def __init__(
        self,
        redis_client: RedisClient,
        resource: str,
        ttl_seconds: int = _DEFAULT_LOCK_TTL_SECONDS,
        retry_count: int = _DEFAULT_LOCK_RETRY_COUNT,
        retry_interval: float = _DEFAULT_LOCK_RETRY_INTERVAL,
    ) -> None:
        self._redis = redis_client
        self._resource = resource
        self._ttl_seconds = ttl_seconds
        self._retry_count = retry_count
        self._retry_interval = retry_interval
        self._lock_key = f"fraud:lock:{resource}"
        self._lock_token: Optional[str] = None

    # -- acquire / release ---------------------------------------------------

    async def acquire(self) -> bool:
        """Attempt to acquire the lock.

        Retries up to *retry_count* times with *retry_interval* sleep.

        Returns:
            ``True`` if the lock was acquired successfully.
        """
        token = str(uuid.uuid4())

        for attempt in range(1, self._retry_count + 1):
            acquired = await self._redis.client.set(
                self._lock_key,
                token,
                ex=self._ttl_seconds,
                nx=True,
            )
            if acquired:
                self._lock_token = token
                logger.info(
                    "lock.acquired",
                    resource=self._resource,
                    token=token,
                    attempt=attempt,
                )
                return True

            logger.debug(
                "lock.retry",
                resource=self._resource,
                attempt=attempt,
                retry_count=self._retry_count,
            )
            await asyncio.sleep(self._retry_interval)

        logger.warning(
            "lock.acquire_failed",
            resource=self._resource,
            retry_count=self._retry_count,
        )
        return False

    async def release(self) -> bool:
        """Release the lock if held by this instance.

        Uses a Lua script to ensure atomicity: only the current token
        holder can delete the key.

        Returns:
            ``True`` if the lock was successfully released.
        """
        if self._lock_token is None:
            logger.warning("lock.release_no_token", resource=self._resource)
            return False

        result = await self._redis.client.eval(
            self._RELEASE_SCRIPT,
            1,
            self._lock_key,
            self._lock_token,
        )
        released = bool(result)
        if released:
            logger.info("lock.released", resource=self._resource)
        else:
            logger.warning("lock.release_mismatch", resource=self._resource)
        self._lock_token = None
        return released

    async def extend(self, additional_seconds: Optional[int] = None) -> bool:
        """Extend the lock TTL.

        Parameters:
            additional_seconds: New TTL in seconds.  Defaults to the
                original *ttl_seconds*.

        Returns:
            ``True`` if the TTL was extended.
        """
        if self._lock_token is None:
            return False

        ttl_ms = (additional_seconds or self._ttl_seconds) * 1000
        result = await self._redis.client.eval(
            self._EXTEND_SCRIPT,
            1,
            self._lock_key,
            self._lock_token,
            str(ttl_ms),
        )
        extended = bool(result)
        if extended:
            logger.debug(
                "lock.extended",
                resource=self._resource,
                ttl_ms=ttl_ms,
            )
        return extended

    @property
    def is_locked(self) -> bool:
        """Return ``True`` if this instance currently holds the lock."""
        return self._lock_token is not None

    # -- context manager -----------------------------------------------------

    async def __aenter__(self) -> "DistributedLock":
        acquired = await self.acquire()
        if not acquired:
            raise TimeoutError(
                f"Could not acquire distributed lock for resource "
                f"'{self._resource}' after {self._retry_count} retries."
            )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.release()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_redis_client(settings: Any) -> RedisClient:
    """Factory: build a :class:`RedisClient` from application settings.

    *settings* is expected to expose the following attributes (all optional;
    sensible defaults are used when missing):

    * ``redis_url`` — full Redis URL (default ``redis://localhost:6379/0``).
    * ``redis_max_connections`` — connection pool size (default ``20``).
    * ``redis_socket_timeout`` — per-command timeout (default ``5.0``).
    * ``redis_socket_connect_timeout`` — connect timeout (default ``5.0``).

    Parameters:
        settings: An object (e.g. pydantic ``BaseSettings``) carrying Redis
            configuration.

    Returns:
        A **not-yet-connected** :class:`RedisClient`.  Callers must use
        ``await client.connect()`` or the async context manager.
    """
    url: str = getattr(settings, "redis_url", _DEFAULT_REDIS_URL)
    max_connections: int = getattr(settings, "redis_max_connections", _DEFAULT_POOL_SIZE)
    socket_timeout: float = getattr(settings, "redis_socket_timeout", 5.0)
    socket_connect_timeout: float = getattr(
        settings, "redis_socket_connect_timeout", 5.0
    )

    logger.info(
        "redis.factory",
        url=url,
        max_connections=max_connections,
    )
    return RedisClient(
        url=url,
        max_connections=max_connections,
        socket_timeout=socket_timeout,
        socket_connect_timeout=socket_connect_timeout,
    )
