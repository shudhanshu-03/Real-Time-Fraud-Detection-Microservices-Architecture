"""
Custom exception hierarchy for the Fraud Detection Platform.

Provides a structured exception base class and domain-specific subclasses
that map cleanly to HTTP status codes.  The :func:`exception_handler`
function can be registered with a FastAPI application to convert any
:class:`FraudPlatformException` into a consistent JSON error response.

Usage::

    from fastapi import FastAPI
    from fraud_common.exceptions import (
        FraudPlatformException,
        NotFoundError,
        exception_handler,
    )

    app = FastAPI()
    app.add_exception_handler(FraudPlatformException, exception_handler)

    @app.get("/items/{item_id}")
    async def get_item(item_id: str):
        raise NotFoundError(message=f"Item {item_id} not found")
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import Request
from fastapi.responses import JSONResponse


# ---------------------------------------------------------------------------
# Base Exception
# ---------------------------------------------------------------------------


class FraudPlatformException(Exception):
    """Base exception for all fraud platform errors.

    Attributes:
        message: Human-readable error description.
        error_code: Machine-readable error identifier (e.g. ``"NOT_FOUND"``).
        status_code: HTTP status code associated with this error.
        details: Optional structured details about the error.
    """

    def __init__(
        self,
        message: str = "An unexpected error occurred.",
        error_code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the exception to a JSON-compatible dictionary.

        Returns:
            A dictionary matching the :class:`fraud_common.models.ErrorResponse`
            schema.
        """
        payload: Dict[str, Any] = {
            "error_code": self.error_code,
            "message": self.message,
            "correlation_id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
        }
        if self.details is not None:
            payload["details"] = self.details
        return payload


# ---------------------------------------------------------------------------
# HTTP 4xx Errors
# ---------------------------------------------------------------------------


class ValidationError(FraudPlatformException):
    """Raised when request validation fails (HTTP 400).

    Attributes:
        message: Description of the validation failure.
        details: Optional mapping of field names to error descriptions.
    """

    def __init__(
        self,
        message: str = "Validation error.",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            status_code=400,
            details=details,
        )


class AuthenticationError(FraudPlatformException):
    """Raised when authentication credentials are missing or invalid (HTTP 401).

    Attributes:
        message: Description of the authentication failure.
    """

    def __init__(
        self,
        message: str = "Authentication required.",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="AUTHENTICATION_ERROR",
            status_code=401,
            details=details,
        )


class AuthorizationError(FraudPlatformException):
    """Raised when the authenticated user lacks required permissions (HTTP 403).

    Attributes:
        message: Description of the authorisation failure.
    """

    def __init__(
        self,
        message: str = "Insufficient permissions.",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="AUTHORIZATION_ERROR",
            status_code=403,
            details=details,
        )


class NotFoundError(FraudPlatformException):
    """Raised when a requested resource does not exist (HTTP 404).

    Attributes:
        message: Description of what was not found.
    """

    def __init__(
        self,
        message: str = "Resource not found.",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="NOT_FOUND",
            status_code=404,
            details=details,
        )


class ConflictError(FraudPlatformException):
    """Raised when a request conflicts with the current resource state (HTTP 409).

    Attributes:
        message: Description of the conflict.
    """

    def __init__(
        self,
        message: str = "Resource conflict.",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="CONFLICT",
            status_code=409,
            details=details,
        )


class RateLimitError(FraudPlatformException):
    """Raised when the client has exceeded the rate limit (HTTP 429).

    Attributes:
        message: Description of the rate limit violation.
    """

    def __init__(
        self,
        message: str = "Rate limit exceeded. Please retry later.",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            details=details,
        )


# ---------------------------------------------------------------------------
# HTTP 5xx Errors
# ---------------------------------------------------------------------------


class ServiceUnavailableError(FraudPlatformException):
    """Raised when a downstream dependency is unreachable (HTTP 503).

    Attributes:
        message: Description of the unavailable service.
    """

    def __init__(
        self,
        message: str = "Service temporarily unavailable.",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="SERVICE_UNAVAILABLE",
            status_code=503,
            details=details,
        )


class KafkaPublishError(FraudPlatformException):
    """Raised when a message cannot be published to Kafka (HTTP 500).

    Attributes:
        message: Description of the Kafka publish failure.
    """

    def __init__(
        self,
        message: str = "Failed to publish message to Kafka.",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="KAFKA_PUBLISH_ERROR",
            status_code=500,
            details=details,
        )


class ScoringTimeoutError(FraudPlatformException):
    """Raised when the fraud scoring pipeline exceeds its time budget (HTTP 504).

    Attributes:
        message: Description of the scoring timeout.
    """

    def __init__(
        self,
        message: str = "Fraud scoring timed out.",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="SCORING_TIMEOUT",
            status_code=504,
            details=details,
        )


# ---------------------------------------------------------------------------
# FastAPI Exception Handler
# ---------------------------------------------------------------------------


async def exception_handler(
    request: Request,
    exc: FraudPlatformException,
) -> JSONResponse:
    """Convert a :class:`FraudPlatformException` into a JSON response.

    Register this handler with a FastAPI application to ensure all platform
    exceptions produce a consistent error payload::

        app.add_exception_handler(FraudPlatformException, exception_handler)

    Args:
        request: The incoming HTTP request that triggered the exception.
        exc: The platform exception to handle.

    Returns:
        A :class:`JSONResponse` with the appropriate HTTP status code and
        a body conforming to the :class:`fraud_common.models.ErrorResponse`
        schema.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )
