"""
Structured logging configuration for the Fraud Detection Platform.

Sets up `structlog <https://www.structlog.org/>`_ with environment-aware
rendering:

- **Production / Staging** — JSON lines suitable for log aggregation
  (e.g. Elasticsearch, Loki, Datadog).
- **Development** — coloured, human-readable console output.

Every log event is automatically enriched with:

- ``timestamp`` (ISO-8601)
- ``log_level``
- ``service`` name
- ``correlation_id`` (when bound to the context)

Usage::

    from fraud_common.logging import setup_logging, get_logger

    setup_logging(service_name="scoring-engine", log_level="INFO")
    logger = get_logger(__name__)

    logger.info("transaction.scored", transaction_id="abc-123", score=0.87)
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def _add_service_name(
    logger: Any,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Structlog processor that injects the service name.

    The service name is stored as a module-level attribute set by
    :func:`setup_logging`.

    Args:
        logger: The wrapped logger object (unused).
        method_name: Name of the log method called (unused).
        event_dict: Mutable event dictionary for the current log entry.

    Returns:
        The enriched event dictionary.
    """
    event_dict.setdefault("service", _SERVICE_NAME)
    return event_dict


def _add_correlation_id(
    logger: Any,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Structlog processor that propagates the correlation ID from context.

    The correlation ID should be bound via
    ``structlog.contextvars.bind_contextvars(correlation_id=...)``.

    Args:
        logger: The wrapped logger object (unused).
        method_name: Name of the log method called (unused).
        event_dict: Mutable event dictionary for the current log entry.

    Returns:
        The enriched event dictionary.
    """
    # Correlation ID comes from contextvars binding — already merged by
    # the merge_contextvars processor.  This processor only ensures the
    # key exists (defaulting to ``None``) so downstream consumers can
    # rely on a consistent schema.
    event_dict.setdefault("correlation_id", None)
    return event_dict


# Module-level state set by setup_logging().
_SERVICE_NAME: str = "unknown"


def setup_logging(
    service_name: str,
    log_level: str = "INFO",
    environment: str = "development",
) -> None:
    """Configure structured logging for the application.

    This function should be called once during service startup, before
    any loggers are created.

    Args:
        service_name: Logical name of the microservice (e.g.
            ``"transaction-ingestion"``).
        log_level: Minimum log level (e.g. ``"DEBUG"``, ``"INFO"``).
        environment: Deployment environment.  ``"production"`` and
            ``"staging"`` produce JSON output; everything else uses a
            coloured console renderer.
    """
    global _SERVICE_NAME  # noqa: PLW0603
    _SERVICE_NAME = service_name

    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Shared processors applied to every log event.
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        _add_service_name,
        _add_correlation_id,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if environment in ("production", "staging"):
        # JSON renderer for machine consumption.
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        # Coloured console renderer for local development.
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure the standard-library root logger so that logs from
    # third-party libraries (uvicorn, sqlalchemy, etc.) are also
    # formatted consistently.
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(numeric_level)

    # Quieten noisy third-party loggers.
    for noisy in ("uvicorn.access", "aiokafka", "kafka"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger for the given module or component.

    Args:
        name: Logger name, typically ``__name__``.

    Returns:
        A :class:`structlog.stdlib.BoundLogger` instance ready for use.

    Example::

        logger = get_logger(__name__)
        logger.info("server.started", host="0.0.0.0", port=8000)
    """
    return structlog.get_logger(name)
