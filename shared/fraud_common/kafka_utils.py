"""
kafka_utils — Production-grade Kafka utilities for the Fraud Detection platform.

Provides high-level abstractions over ``aiokafka`` for reliable event
publishing, consumption, idempotent processing, and dead-letter-queue
management.  Every microservice in the platform should use these helpers
rather than interacting with ``aiokafka`` directly.

Key components
--------------
* :class:`EventEnvelope` — canonical event wrapper used across all topics.
* :class:`FraudKafkaProducer` — async producer with retry & back-pressure.
* :class:`FraudKafkaConsumer` — async consumer with idempotency, retry, and
  DLQ routing.
* :class:`DLQHandler` — dead-letter-queue reader / replayer.

Usage example::

    from fraud_common.kafka_utils import (
        EventEnvelope, FraudKafkaProducer, FraudKafkaConsumer,
    )

    async with FraudKafkaProducer(bootstrap_servers="kafka:9092") as producer:
        envelope = EventEnvelope(
            event_type="transaction.scored",
            source_service="scoring-engine",
            payload={"txn_id": "abc", "score": 0.87},
        )
        await producer.publish_with_retry("fraud.events", key="abc", event_envelope=envelope)
"""

from __future__ import annotations

import asyncio
import json
import signal
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.errors import KafkaError

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_BOOTSTRAP_SERVERS = "localhost:9092"
_DEFAULT_DLQ_SUFFIX = ".dlq"
_DEFAULT_DEDUP_TTL_SECONDS = 86_400  # 24 hours
_DEFAULT_MAX_RETRIES = 3
_BACKOFF_BASE_SECONDS = 0.5


# ---------------------------------------------------------------------------
# EventEnvelope
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EventEnvelope:
    """Canonical envelope wrapping every event published to Kafka.

    Every field except *payload* has a sensible default so callers only need
    to supply the business-relevant data.

    Attributes:
        event_id: Globally unique identifier (auto-generated UUID-4).
        event_type: Dot-namespaced event type, e.g. ``transaction.created``.
        source_service: Name of the originating microservice.
        correlation_id: Optional correlation / trace ID for distributed
            tracing.  Falls back to *event_id* when not provided.
        timestamp: ISO-8601 UTC timestamp (auto-generated).
        payload: Arbitrary JSON-serialisable business data.
    """

    event_type: str
    source_service: str
    payload: Dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: Optional[str] = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # -- helpers -------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the envelope to a plain ``dict``.

        The *correlation_id* is normalised to *event_id* when ``None``.
        """
        data = asdict(self)
        if data["correlation_id"] is None:
            data["correlation_id"] = data["event_id"]
        return data

    def to_json(self) -> bytes:
        """Serialise the envelope to compact UTF-8 JSON bytes."""
        return json.dumps(self.to_dict(), separators=(",", ":")).encode("utf-8")

    @classmethod
    def from_json(cls, raw: bytes) -> "EventEnvelope":
        """Deserialise a JSON blob back into an :class:`EventEnvelope`.

        Raises:
            json.JSONDecodeError: If *raw* is not valid JSON.
            TypeError: If required fields are missing.
        """
        data: Dict[str, Any] = json.loads(raw)
        return cls(
            event_id=data["event_id"],
            event_type=data["event_type"],
            source_service=data["source_service"],
            correlation_id=data.get("correlation_id"),
            timestamp=data["timestamp"],
            payload=data.get("payload", {}),
        )


# ---------------------------------------------------------------------------
# FraudKafkaProducer
# ---------------------------------------------------------------------------


class FraudKafkaProducer:
    """Async Kafka producer with built-in retry and structured logging.

    Designed to be used as an **async context manager**::

        async with FraudKafkaProducer(bootstrap_servers="kafka:9092") as p:
            await p.publish("topic", key="k", event_envelope=envelope)

    Parameters:
        bootstrap_servers: Comma-separated broker list.
        client_id: Kafka client identifier.
        acks: Producer acknowledgement level (``"all"`` recommended for
            durability).
        linger_ms: How long to wait before sending a batch.
        max_batch_size: Maximum batch size in bytes.
        compression_type: Compression codec (``"gzip"`` | ``"snappy"`` |
            ``"lz4"`` | ``None``).
    """

    def __init__(
        self,
        bootstrap_servers: str = _DEFAULT_BOOTSTRAP_SERVERS,
        client_id: str = "fraud-producer",
        acks: str = "all",
        linger_ms: int = 10,
        max_batch_size: int = 16_384,
        compression_type: Optional[str] = "gzip",
    ) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._producer: Optional[AIOKafkaProducer] = None
        self._client_id = client_id
        self._acks = acks
        self._linger_ms = linger_ms
        self._max_batch_size = max_batch_size
        self._compression_type = compression_type
        self._started = False

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        """Create and start the underlying ``AIOKafkaProducer``.

        This is idempotent — calling it on an already-started producer is a
        no-op.
        """
        if self._started:
            logger.warning("producer.already_started", client_id=self._client_id)
            return

        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            client_id=self._client_id,
            acks=self._acks,
            linger_ms=self._linger_ms,
            max_batch_size=self._max_batch_size,
            compression_type=self._compression_type,
            key_serializer=lambda k: k.encode("utf-8") if isinstance(k, str) else k,
            value_serializer=lambda v: v if isinstance(v, bytes) else json.dumps(v).encode("utf-8"),
        )
        await self._producer.start()
        self._started = True
        logger.info(
            "producer.started",
            bootstrap_servers=self._bootstrap_servers,
            client_id=self._client_id,
        )

    async def stop(self) -> None:
        """Flush pending messages and stop the producer gracefully."""
        if self._producer is not None and self._started:
            await self._producer.stop()
            self._started = False
            logger.info("producer.stopped", client_id=self._client_id)

    # -- context manager -----------------------------------------------------

    async def __aenter__(self) -> "FraudKafkaProducer":
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.stop()

    # -- publishing ----------------------------------------------------------

    async def publish(
        self,
        topic: str,
        key: str,
        event_envelope: EventEnvelope,
    ) -> None:
        """Publish an :class:`EventEnvelope` to *topic*.

        Parameters:
            topic: Destination Kafka topic.
            key: Partitioning key (e.g. transaction ID).
            event_envelope: The event to publish.

        Raises:
            RuntimeError: If the producer has not been started.
            KafkaError: On unrecoverable Kafka failures.
        """
        if not self._started or self._producer is None:
            raise RuntimeError(
                "FraudKafkaProducer.start() must be called before publishing."
            )

        payload_bytes = event_envelope.to_json()
        try:
            record_metadata = await self._producer.send_and_wait(
                topic, key=key, value=payload_bytes
            )
            logger.info(
                "event.published",
                topic=topic,
                key=key,
                event_id=event_envelope.event_id,
                event_type=event_envelope.event_type,
                partition=record_metadata.partition,
                offset=record_metadata.offset,
            )
        except KafkaError as exc:
            logger.error(
                "event.publish_failed",
                topic=topic,
                key=key,
                event_id=event_envelope.event_id,
                error=str(exc),
            )
            raise

    async def publish_with_retry(
        self,
        topic: str,
        key: str,
        event_envelope: EventEnvelope,
        max_retries: int = _DEFAULT_MAX_RETRIES,
    ) -> None:
        """Publish with exponential-backoff retry.

        After exhausting all retries the last exception is re-raised so the
        caller can decide how to handle the permanent failure (e.g. write to
        a fallback store).

        Parameters:
            topic: Destination Kafka topic.
            key: Partitioning key.
            event_envelope: The event to publish.
            max_retries: Maximum number of retry attempts.

        Raises:
            KafkaError: If all retry attempts fail.
        """
        last_exc: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                await self.publish(topic, key, event_envelope)
                return
            except (KafkaError, OSError) as exc:
                last_exc = exc
                backoff = _BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                logger.warning(
                    "event.publish_retry",
                    topic=topic,
                    key=key,
                    event_id=event_envelope.event_id,
                    attempt=attempt,
                    max_retries=max_retries,
                    backoff_seconds=backoff,
                    error=str(exc),
                )
                await asyncio.sleep(backoff)

        logger.error(
            "event.publish_exhausted",
            topic=topic,
            key=key,
            event_id=event_envelope.event_id,
            max_retries=max_retries,
        )
        raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# DLQHandler
# ---------------------------------------------------------------------------


class DLQHandler:
    """Manages a dead-letter-queue (DLQ) topic.

    Failed messages are written to ``<original_topic>.dlq`` with metadata
    about the failure.  This class also supports **replaying** DLQ messages
    back into the original topic.

    Parameters:
        producer: A started :class:`FraudKafkaProducer`.
        dlq_suffix: Suffix appended to the original topic name.
    """

    def __init__(
        self,
        producer: FraudKafkaProducer,
        dlq_suffix: str = _DEFAULT_DLQ_SUFFIX,
    ) -> None:
        self._producer = producer
        self._dlq_suffix = dlq_suffix

    def _dlq_topic(self, original_topic: str) -> str:
        """Return the DLQ topic name for *original_topic*."""
        return f"{original_topic}{self._dlq_suffix}"

    async def send_to_dlq(
        self,
        original_topic: str,
        key: str,
        event_envelope: EventEnvelope,
        error_message: str,
        retry_count: int,
    ) -> None:
        """Publish a failed event to the DLQ topic.

        The DLQ message wraps the original envelope with additional error
        metadata so operators can inspect and replay.

        Parameters:
            original_topic: The topic the message was originally consumed
                from.
            key: Partitioning key.
            event_envelope: The original event.
            error_message: Human-readable error description.
            retry_count: How many processing attempts were made.
        """
        dlq_payload: Dict[str, Any] = {
            "original_topic": original_topic,
            "original_event": event_envelope.to_dict(),
            "error_message": error_message,
            "retry_count": retry_count,
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }
        dlq_envelope = EventEnvelope(
            event_type="dlq.entry",
            source_service="dlq-handler",
            correlation_id=event_envelope.correlation_id or event_envelope.event_id,
            payload=dlq_payload,
        )
        dlq_topic = self._dlq_topic(original_topic)
        try:
            await self._producer.publish(dlq_topic, key, dlq_envelope)
            logger.info(
                "dlq.sent",
                dlq_topic=dlq_topic,
                original_topic=original_topic,
                event_id=event_envelope.event_id,
            )
        except KafkaError as exc:
            # If even the DLQ publish fails we log critically but do not
            # re-raise — we never want DLQ failures to crash the consumer.
            logger.critical(
                "dlq.publish_failed",
                dlq_topic=dlq_topic,
                event_id=event_envelope.event_id,
                error=str(exc),
            )

    async def replay(
        self,
        original_topic: str,
        bootstrap_servers: str = _DEFAULT_BOOTSTRAP_SERVERS,
        group_id: str = "dlq-replayer",
        batch_size: int = 100,
    ) -> int:
        """Replay messages from the DLQ back into *original_topic*.

        Reads up to *batch_size* messages from the DLQ, extracts the
        original event, and republishes it.

        Parameters:
            original_topic: The topic to replay messages into.
            bootstrap_servers: Kafka broker list.
            group_id: Consumer group for the DLQ reader.
            batch_size: Max messages to process per invocation.

        Returns:
            Number of successfully replayed messages.
        """
        dlq_topic = self._dlq_topic(original_topic)
        consumer = AIOKafkaConsumer(
            dlq_topic,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            max_poll_records=batch_size,
        )
        replayed = 0
        try:
            await consumer.start()
            messages = await consumer.getmany(timeout_ms=5_000)
            for _tp, records in messages.items():
                for record in records:
                    try:
                        wrapper = json.loads(record.value)
                        # Unwrap the DLQ wrapper → original event payload
                        original_data = wrapper.get("payload", {}).get(
                            "original_event", wrapper
                        )
                        envelope = EventEnvelope(
                            event_id=original_data.get("event_id", str(uuid.uuid4())),
                            event_type=original_data["event_type"],
                            source_service=original_data["source_service"],
                            correlation_id=original_data.get("correlation_id"),
                            timestamp=original_data.get(
                                "timestamp",
                                datetime.now(timezone.utc).isoformat(),
                            ),
                            payload=original_data.get("payload", {}),
                        )
                        key = record.key.decode("utf-8") if record.key else envelope.event_id
                        await self._producer.publish(original_topic, key, envelope)
                        replayed += 1
                    except Exception as exc:  # noqa: BLE001
                        logger.error(
                            "dlq.replay_failed",
                            offset=record.offset,
                            error=str(exc),
                        )
            await consumer.commit()
        finally:
            await consumer.stop()

        logger.info(
            "dlq.replay_complete",
            dlq_topic=dlq_topic,
            original_topic=original_topic,
            replayed=replayed,
        )
        return replayed


# ---------------------------------------------------------------------------
# FraudKafkaConsumer
# ---------------------------------------------------------------------------

# Type alias for the async handler function every consumer invokes.
MessageHandler = Callable[[EventEnvelope], Awaitable[None]]


class FraudKafkaConsumer:
    """Async Kafka consumer with idempotency, retry, and DLQ routing.

    Designed to be used as an **async context manager**::

        async with FraudKafkaConsumer(
            topics=["fraud.events"],
            bootstrap_servers="kafka:9092",
            group_id="scoring-engine",
            redis_client=redis_client,
        ) as consumer:
            await consumer.consume(handler_fn)

    Parameters:
        topics: List of Kafka topics to subscribe to.
        bootstrap_servers: Comma-separated broker list.
        group_id: Consumer group identifier.
        redis_client: An *optional* ``redis.asyncio.Redis`` instance used
            for idempotency de-duplication.  When ``None`` idempotency
            checks are **skipped**.
        dlq_producer: Optional producer for DLQ publishing.  When ``None``
            a dedicated producer is created automatically.
        auto_commit: Enable Kafka auto-commit (disable for at-least-once).
        max_retries: Maximum handler retry attempts before DLQ routing.
        dedup_ttl_seconds: TTL for the Redis de-duplication key.
    """

    def __init__(
        self,
        topics: List[str],
        bootstrap_servers: str = _DEFAULT_BOOTSTRAP_SERVERS,
        group_id: str = "fraud-consumer",
        redis_client: Any = None,
        dlq_producer: Optional[FraudKafkaProducer] = None,
        auto_commit: bool = False,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        dedup_ttl_seconds: int = _DEFAULT_DEDUP_TTL_SECONDS,
    ) -> None:
        self._topics = topics
        self._bootstrap_servers = bootstrap_servers
        self._group_id = group_id
        self._redis = redis_client
        self._auto_commit = auto_commit
        self._max_retries = max_retries
        self._dedup_ttl = dedup_ttl_seconds
        self._consumer: Optional[AIOKafkaConsumer] = None
        self._running = False
        self._dlq_producer = dlq_producer
        self._dlq_handler: Optional[DLQHandler] = None
        self._owns_dlq_producer = False  # tracks if we created the producer

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        """Create and start the underlying ``AIOKafkaConsumer``.

        Also initialises the DLQ producer if one was not provided.
        """
        if self._running:
            logger.warning("consumer.already_started", group_id=self._group_id)
            return

        self._consumer = AIOKafkaConsumer(
            *self._topics,
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._group_id,
            auto_offset_reset="earliest",
            enable_auto_commit=self._auto_commit,
            value_deserializer=lambda v: v,  # raw bytes — we deserialise ourselves
            key_deserializer=lambda k: k.decode("utf-8") if k else None,
        )
        await self._consumer.start()

        # Ensure we have a DLQ producer.
        if self._dlq_producer is None:
            self._dlq_producer = FraudKafkaProducer(
                bootstrap_servers=self._bootstrap_servers,
                client_id=f"{self._group_id}-dlq-producer",
            )
            await self._dlq_producer.start()
            self._owns_dlq_producer = True

        self._dlq_handler = DLQHandler(producer=self._dlq_producer)
        self._running = True
        logger.info(
            "consumer.started",
            topics=self._topics,
            group_id=self._group_id,
        )

    async def stop(self) -> None:
        """Gracefully stop the consumer and its DLQ producer (if owned)."""
        self._running = False
        if self._consumer is not None:
            await self._consumer.stop()
            logger.info("consumer.stopped", group_id=self._group_id)
        if self._owns_dlq_producer and self._dlq_producer is not None:
            await self._dlq_producer.stop()

    # -- context manager -----------------------------------------------------

    async def __aenter__(self) -> "FraudKafkaConsumer":
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.stop()

    # -- consuming -----------------------------------------------------------

    async def consume(self, handler_fn: MessageHandler) -> None:
        """Enter the main consume loop.

        Each message is deserialised into an :class:`EventEnvelope`,
        de-duplicated via Redis (if available), and dispatched to
        *handler_fn*.  On failure the message is retried with exponential
        backoff; after *max_retries* it is routed to the DLQ.

        The loop runs until :meth:`stop` is called or a ``SIGTERM`` /
        ``SIGINT`` is received.

        Parameters:
            handler_fn: Async callable accepting an :class:`EventEnvelope`.
        """
        if not self._running or self._consumer is None:
            raise RuntimeError(
                "FraudKafkaConsumer.start() must be called before consuming."
            )

        # Register graceful shutdown signals (Unix-only; ignored on Windows).
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._request_shutdown)
            except NotImplementedError:
                # Windows does not support add_signal_handler for all signals.
                pass

        logger.info("consumer.loop_started", topics=self._topics)
        try:
            async for message in self._consumer:
                if not self._running:
                    break
                await self._process_message(message, handler_fn)
        except asyncio.CancelledError:
            logger.info("consumer.loop_cancelled", group_id=self._group_id)
        finally:
            logger.info("consumer.loop_exited", group_id=self._group_id)

    def _request_shutdown(self) -> None:
        """Signal handler that requests a clean shutdown."""
        logger.info("consumer.shutdown_requested", group_id=self._group_id)
        self._running = False

    # -- internal processing -------------------------------------------------

    async def _process_message(
        self,
        message: Any,
        handler_fn: MessageHandler,
    ) -> None:
        """Deserialise, de-dup, and dispatch a single Kafka message."""
        try:
            envelope = EventEnvelope.from_json(message.value)
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            logger.error(
                "consumer.deserialise_failed",
                topic=message.topic,
                offset=message.offset,
                error=str(exc),
            )
            # Un-parseable messages go straight to the DLQ.
            if self._dlq_handler is not None:
                bad_envelope = EventEnvelope(
                    event_type="unknown",
                    source_service="unknown",
                    payload={"raw": message.value.decode("utf-8", errors="replace")},
                )
                await self._dlq_handler.send_to_dlq(
                    original_topic=message.topic,
                    key=message.key or "unknown",
                    event_envelope=bad_envelope,
                    error_message=f"Deserialisation error: {exc}",
                    retry_count=0,
                )
            return

        # Idempotency check via Redis.
        if await self._is_duplicate(envelope.event_id):
            logger.debug(
                "consumer.duplicate_skipped",
                event_id=envelope.event_id,
                topic=message.topic,
            )
            # Commit offset so the duplicate is not re-delivered.
            if not self._auto_commit and self._consumer is not None:
                await self._consumer.commit()
            return

        # Dispatch to handler with retry.
        await self._handle_with_retry(message, envelope, handler_fn)

        # Mark event as processed (idempotency).
        await self._mark_processed(envelope.event_id)

        # Manual commit.
        if not self._auto_commit and self._consumer is not None:
            await self._consumer.commit()

    async def _handle_with_retry(
        self,
        message: Any,
        envelope: EventEnvelope,
        handler_fn: MessageHandler,
        max_retries: Optional[int] = None,
    ) -> None:
        """Invoke *handler_fn* with exponential-backoff retry.

        On final failure the message is published to the DLQ.
        """
        retries = max_retries if max_retries is not None else self._max_retries
        last_exc: Optional[Exception] = None

        for attempt in range(1, retries + 1):
            try:
                await handler_fn(envelope)
                return  # success
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                backoff = _BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                logger.warning(
                    "consumer.handler_retry",
                    event_id=envelope.event_id,
                    attempt=attempt,
                    max_retries=retries,
                    backoff_seconds=backoff,
                    error=str(exc),
                )
                if attempt < retries:
                    await asyncio.sleep(backoff)

        # All retries exhausted — route to DLQ.
        logger.error(
            "consumer.handler_exhausted",
            event_id=envelope.event_id,
            max_retries=retries,
        )
        if self._dlq_handler is not None:
            await self._dlq_handler.send_to_dlq(
                original_topic=message.topic,
                key=message.key or envelope.event_id,
                event_envelope=envelope,
                error_message=str(last_exc),
                retry_count=retries,
            )

    # -- idempotency helpers -------------------------------------------------

    async def _is_duplicate(self, event_id: str) -> bool:
        """Check Redis to see if *event_id* was already processed.

        Returns ``False`` when no Redis client is configured (idempotency
        disabled).
        """
        if self._redis is None:
            return False
        try:
            key = f"fraud:dedup:{event_id}"
            return bool(await self._redis.exists(key))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "consumer.dedup_check_failed",
                event_id=event_id,
                error=str(exc),
            )
            # Fail open — process the message rather than risk data loss.
            return False

    async def _mark_processed(self, event_id: str) -> None:
        """Record *event_id* in Redis with a 24-hour TTL."""
        if self._redis is None:
            return
        try:
            key = f"fraud:dedup:{event_id}"
            await self._redis.set(key, "1", ex=self._dedup_ttl)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "consumer.dedup_mark_failed",
                event_id=event_id,
                error=str(exc),
            )
