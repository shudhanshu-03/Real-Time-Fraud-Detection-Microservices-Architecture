"""
FastAPI Middleware for the Real-Time Fraud Detection Platform.

This module provides a suite of production-grade middleware components that are
shared across all microservices in the fraud detection ecosystem. Each middleware
is designed to be composable and follows the Starlette BaseHTTPMiddleware pattern.

Middleware Stack (applied via ``setup_middleware``):
    1. **ErrorHandlingMiddleware** — outermost; catches unhandled exceptions and
       returns a structured JSON error envelope so that no raw tracebacks leak
       to clients.
    2. **CorrelationIdMiddleware** — extracts or generates a ``X-Correlation-ID``
       header, making distributed tracing trivial across Kafka consumers, gRPC
       calls, and REST endpoints.
    3. **RequestLoggingMiddleware** — innermost; emits a structured log line for
       every request with method, path, status code, and duration in
       milliseconds.

Usage::

    from fastapi import FastAPI
    from fraud_common.middleware import setup_middleware

    app = FastAPI()
    setup_middleware(app)
"""

from __future__ import annotations

import traceback
import uuid
import time
from typing import Callable

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse
import structlog

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Header constants
# ---------------------------------------------------------------------------
CORRELATION_ID_HEADER: str = "X-Correlation-ID"
"""The HTTP header used for propagating correlation / trace IDs."""


# ═══════════════════════════════════════════════════════════════════════════
# 1. CorrelationIdMiddleware
# ═══════════════════════════════════════════════════════════════════════════


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Extract or generate a correlation ID for every inbound request.

    If the incoming request carries an ``X-Correlation-ID`` header the value
    is reused; otherwise a new UUID-4 is generated.  The resolved ID is:

    * Stored on ``request.state.correlation_id`` so downstream handlers and
      other middleware can access it without re-parsing headers.
    * Echoed back in the ``X-Correlation-ID`` response header, allowing
      clients and API gateways to correlate responses.
    * Bound to the *structlog* context via :pymethod:`structlog.contextvars.bind_contextvars`
      so that every subsequent log line emitted during request processing
      automatically includes ``correlation_id``.

    Parameters
    ----------
    app : FastAPI
        The ASGI application instance.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Process the request, ensuring a correlation ID is always present.

        Parameters
        ----------
        request : Request
            The inbound HTTP request.
        call_next : RequestResponseEndpoint
            Callable to forward the request to the next middleware / route.

        Returns
        -------
        Response
            The HTTP response with the ``X-Correlation-ID`` header set.
        """
        # Extract existing correlation ID or mint a new one.
        correlation_id: str = request.headers.get(
            CORRELATION_ID_HEADER, str(uuid.uuid4())
        )

        # Attach to request state for access in route handlers.
        request.state.correlation_id = correlation_id

        # Bind to structlog context so all log lines include the ID.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        response: Response = await call_next(request)

        # Echo the correlation ID back to the caller.
        response.headers[CORRELATION_ID_HEADER] = correlation_id

        return response


# ═══════════════════════════════════════════════════════════════════════════
# 2. RequestLoggingMiddleware
# ═══════════════════════════════════════════════════════════════════════════


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Emit a structured log line for every HTTP request/response cycle.

    Each log entry contains:

    * ``http_method`` – GET, POST, PUT, …
    * ``http_path`` – the URL path (query string excluded for brevity).
    * ``http_status`` – the integer status code of the response.
    * ``duration_ms`` – wall-clock time spent processing the request,
      measured in milliseconds with microsecond precision.

    The middleware uses :pymod:`time.perf_counter` for high-resolution
    timing that is immune to system-clock adjustments.

    Parameters
    ----------
    app : FastAPI
        The ASGI application instance.
    exclude_paths : set[str] | None
        Optional set of URL paths (e.g. ``{"/healthz", "/readyz"}``)
        that should **not** produce log output.  Useful for silencing
        noisy liveness / readiness probes in Kubernetes.
    """

    def __init__(
        self,
        app: FastAPI,
        exclude_paths: set[str] | None = None,
    ) -> None:
        super().__init__(app)
        self.exclude_paths: set[str] = exclude_paths or set()

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Time the request and log the result.

        Parameters
        ----------
        request : Request
            The inbound HTTP request.
        call_next : RequestResponseEndpoint
            Callable to forward the request to the next middleware / route.

        Returns
        -------
        Response
            The unmodified downstream response.
        """
        # Skip logging for excluded paths (e.g. health checks).
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        start_time: float = time.perf_counter()

        response: Response = await call_next(request)

        duration_ms: float = round((time.perf_counter() - start_time) * 1000, 3)

        # Determine log level based on status code.
        log_method: Callable[..., None]
        if response.status_code >= 500:
            log_method = logger.error
        elif response.status_code >= 400:
            log_method = logger.warning
        else:
            log_method = logger.info

        log_method(
            "http_request_completed",
            http_method=request.method,
            http_path=request.url.path,
            http_status=response.status_code,
            duration_ms=duration_ms,
            client_host=request.client.host if request.client else "unknown",
        )

        return response


# ═══════════════════════════════════════════════════════════════════════════
# 3. ErrorHandlingMiddleware
# ═══════════════════════════════════════════════════════════════════════════


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Catch unhandled exceptions and return a structured JSON error response.

    This middleware acts as the **outermost** safety net.  Any exception that
    escapes the application's route handlers and inner middleware is caught
    here, logged with a full traceback, and translated into a consistent
    JSON error envelope::

        {
            "error": {
                "type": "InternalServerError",
                "message": "An unexpected error occurred. Please try again later.",
                "correlation_id": "a1b2c3d4-…",
                "status_code": 500
            }
        }

    .. important::

        The raw exception message is **never** exposed to the client in
        production.  Only a generic user-facing message is returned to
        prevent information leakage.

    Parameters
    ----------
    app : FastAPI
        The ASGI application instance.
    debug : bool
        When ``True`` the actual exception message is included in the JSON
        response.  **Never** enable in production.
    """

    def __init__(self, app: FastAPI, debug: bool = False) -> None:
        super().__init__(app)
        self.debug: bool = debug

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Wrap the downstream call in a try/except safety net.

        Parameters
        ----------
        request : Request
            The inbound HTTP request.
        call_next : RequestResponseEndpoint
            Callable to forward the request to the next middleware / route.

        Returns
        -------
        Response
            The downstream response on success, or a ``500`` JSON envelope
            on unhandled failure.
        """
        try:
            return await call_next(request)
        except Exception as exc:
            # Retrieve correlation ID if it was set by CorrelationIdMiddleware.
            correlation_id: str = getattr(
                request.state, "correlation_id", "unknown"
            )

            # Log full traceback for operational debugging.
            logger.exception(
                "unhandled_exception",
                exc_type=type(exc).__name__,
                exc_message=str(exc),
                http_method=request.method,
                http_path=request.url.path,
                correlation_id=correlation_id,
                traceback=traceback.format_exc(),
            )

            # Build a safe error envelope for the client.
            error_detail: str
            if self.debug:
                error_detail = f"{type(exc).__name__}: {exc}"
            else:
                error_detail = (
                    "An unexpected error occurred. Please try again later."
                )

            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "type": "InternalServerError",
                        "message": error_detail,
                        "correlation_id": correlation_id,
                        "status_code": 500,
                    }
                },
                headers={CORRELATION_ID_HEADER: correlation_id},
            )


# ═══════════════════════════════════════════════════════════════════════════
# Helper – setup_middleware
# ═══════════════════════════════════════════════════════════════════════════


def setup_middleware(
    app: FastAPI,
    *,
    debug: bool = False,
    exclude_logging_paths: set[str] | None = None,
) -> None:
    """Register all fraud-platform middleware on the given FastAPI application.

    Middleware is added in **reverse** order of desired execution because
    Starlette processes middleware as a stack (last-added runs first)::

        Request  ──►  ErrorHandling  ──►  CorrelationId  ──►  RequestLogging  ──►  Route
        Response ◄──  ErrorHandling  ◄──  CorrelationId  ◄──  RequestLogging  ◄──  Route

    This means:

    * ``ErrorHandlingMiddleware`` wraps everything—if any inner middleware
      or route raises, the error is caught and a structured JSON response
      is returned.
    * ``CorrelationIdMiddleware`` runs next, ensuring the correlation ID
      is available for logging and error responses.
    * ``RequestLoggingMiddleware`` runs closest to the route, giving the
      most accurate duration measurement.

    Parameters
    ----------
    app : FastAPI
        The FastAPI application to instrument.
    debug : bool
        If ``True``, raw exception messages are included in error responses.
        Must be ``False`` in production environments.
    exclude_logging_paths : set[str] | None
        URL paths to suppress from request logging (e.g. health-check
        endpoints).  Defaults to ``{"/healthz", "/readyz", "/metrics"}``.

    Example
    -------
    ::

        from fastapi import FastAPI
        from fraud_common.middleware import setup_middleware

        app = FastAPI(title="Transaction Ingestion Service")
        setup_middleware(app, debug=False)
    """
    if exclude_logging_paths is None:
        exclude_logging_paths = {"/healthz", "/readyz", "/metrics"}

    # Added in reverse order: last added = first to execute.
    app.add_middleware(
        RequestLoggingMiddleware,
        exclude_paths=exclude_logging_paths,
    )
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(ErrorHandlingMiddleware, debug=debug)

    logger.info(
        "middleware_initialized",
        middleware=[
            "ErrorHandlingMiddleware",
            "CorrelationIdMiddleware",
            "RequestLoggingMiddleware",
        ],
        debug_mode=debug,
        excluded_paths=sorted(exclude_logging_paths),
    )
