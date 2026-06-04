"""
Redis-backed sliding-window rate limiter middleware.

Uses Redis sorted sets to implement a sliding window algorithm that
accurately tracks request counts per client.  Falls back to allowing
requests through when Redis is unavailable (graceful degradation).
"""

import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)


class RateLimiter:
    """
    Sliding-window rate limiter backed by Redis sorted sets.

    Each client is assigned a Redis key whose members are request
    timestamps.  On every call the window is trimmed, the current
    timestamp is added, and the cardinality is checked against the
    configured limit.
    """

    def __init__(self, redis_client: Any) -> None:
        """
        Initialise the rate limiter.

        Args:
            redis_client: An ``redis.asyncio.Redis`` instance (or *None*
                if Redis is unavailable).
        """
        self._redis = redis_client

    async def check_rate_limit(
        self,
        client_id: str,
        limit: int = settings.rate_limit_per_minute,
        window: int = 60,
    ) -> tuple[bool, int, int]:
        """
        Check whether the client has exceeded its rate limit.

        Args:
            client_id: Unique identifier for the client (JWT ``sub`` or IP).
            limit: Maximum number of requests allowed in the window.
            window: Window size in seconds.

        Returns:
            A tuple of ``(allowed, remaining, retry_after)``.

            * *allowed* – ``True`` if the request should proceed.
            * *remaining* – number of requests left in the current window.
            * *retry_after* – seconds until the window resets (relevant
              only when *allowed* is ``False``).
        """
        if self._redis is None:
            # Graceful degradation: allow the request if Redis is down
            return True, limit, 0

        now = time.time()
        key = f"rate_limit:{client_id}"
        window_start = now - window

        try:
            pipe = self._redis.pipeline()
            # Remove entries outside the sliding window
            pipe.zremrangebyscore(key, 0, window_start)
            # Add current request timestamp
            pipe.zadd(key, {str(now): now})
            # Count entries in the window
            pipe.zcard(key)
            # Set TTL so stale keys are eventually cleaned up
            pipe.expire(key, window + 10)
            results = await pipe.execute()

            request_count: int = results[2]
            remaining = max(0, limit - request_count)

            if request_count > limit:
                retry_after = int(window - (now - window_start))
                logger.warning(
                    "rate_limit_exceeded",
                    client_id=client_id,
                    count=request_count,
                    limit=limit,
                )
                return False, 0, max(retry_after, 1)

            return True, remaining, 0

        except Exception:
            # Graceful degradation on any Redis error
            logger.exception("rate_limiter_redis_error", client_id=client_id)
            return True, limit, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware that enforces per-client rate limiting.

    The client identifier is extracted from the JWT ``sub`` claim when
    available, otherwise it falls back to the remote IP address.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Apply rate limiting before forwarding the request."""

        # Skip rate limiting for health and metrics endpoints
        if request.url.path in ("/health", "/metrics"):
            return await call_next(request)

        client_id = self._extract_client_id(request)

        # Obtain the rate limiter from app state (set during lifespan)
        rate_limiter: RateLimiter | None = getattr(
            request.app.state, "rate_limiter", None
        )

        if rate_limiter is not None:
            allowed, remaining, retry_after = await rate_limiter.check_rate_limit(
                client_id=client_id,
                limit=settings.rate_limit_per_minute,
                window=60,
            )

            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Rate limit exceeded. Please try again later.",
                        "retry_after": retry_after,
                    },
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(settings.rate_limit_per_minute),
                        "X-RateLimit-Remaining": "0",
                    },
                )

            response: Response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(settings.rate_limit_per_minute)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            return response

        # No rate limiter configured – pass through
        return await call_next(request)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_client_id(request: Request) -> str:
        """
        Determine a stable client identifier for rate-limit bucketing.

        Prefers the JWT ``sub`` claim when available, falling back to
        the originating IP address.
        """
        auth_header: str | None = request.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            try:
                from jose import jwt as _jwt

                token = auth_header.split(" ", 1)[1]
                payload = _jwt.decode(
                    token,
                    settings.jwt_secret_key,
                    algorithms=[settings.jwt_algorithm],
                    options={"verify_exp": False},
                )
                subject = payload.get("sub")
                if subject:
                    return f"user:{subject}"
            except Exception:
                pass  # Fall through to IP-based identification

        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return f"ip:{forwarded.split(',')[0].strip()}"

        client_host = request.client.host if request.client else "unknown"
        return f"ip:{client_host}"
