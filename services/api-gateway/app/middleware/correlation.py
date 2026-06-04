"""
Correlation ID middleware for the API Gateway.

Ensures every request/response cycle carries a unique correlation ID for
end-to-end distributed tracing across microservices.
"""

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
import structlog

logger = structlog.get_logger(__name__)

CORRELATION_ID_HEADER = "X-Correlation-ID"


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that extracts or generates a correlation ID for every request.

    If the incoming request contains an ``X-Correlation-ID`` header its value
    is reused; otherwise a new UUID-4 is generated.  The correlation ID is:

    * stored in ``request.state.correlation_id`` so downstream handlers and
      other middleware can access it,
    * injected into the response headers for client-side tracing,
    * bound to the structlog context for automatic inclusion in log entries.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Process the request, attaching a correlation ID."""

        # Extract existing correlation ID or generate a new one
        correlation_id: str = request.headers.get(
            CORRELATION_ID_HEADER, str(uuid.uuid4())
        )

        # Store in request state for downstream access
        request.state.correlation_id = correlation_id

        # Bind to structlog context so all log messages include it
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        logger.debug(
            "request_started",
            method=request.method,
            path=str(request.url.path),
            correlation_id=correlation_id,
        )

        response: Response = await call_next(request)

        # Inject correlation ID into response headers
        response.headers[CORRELATION_ID_HEADER] = correlation_id

        logger.debug(
            "request_completed",
            method=request.method,
            path=str(request.url.path),
            status_code=response.status_code,
            correlation_id=correlation_id,
        )

        return response
