"""Structured Logging Configuration for Control-Plane API.

CAB-281: Standardized JSON logging for Loki integration.

Uses structlog for consistent JSON log output compatible with
Promtail/Loki log aggregation pipeline.
"""

import logging
import sys
from typing import Literal

import structlog
from structlog.types import Processor

from .config import settings


def configure_logging(
    log_level: str = None,
    log_format: Literal["json", "text"] = None,
) -> None:
    """Configure structured logging for the application.

    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Output format ("json" for production, "text" for development)
    """
    level = log_level or settings.LOG_LEVEL
    fmt = log_format or settings.LOG_FORMAT

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )

    # Shared processors for all formats
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if fmt == "json":
        # JSON format for production/Loki ingestion
        processors = shared_processors + [
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Human-readable format for development
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured structlog logger

    Example:
        from src.logging_config import get_logger
        logger = get_logger(__name__)
        logger.info("Processing request", tenant_id="acme", api_id="123")
    """
    return structlog.get_logger(name)


# Convenience function to bind context to all loggers
def bind_context(**kwargs) -> None:
    """Bind context variables to all subsequent log messages.

    Useful for request-scoped context like tenant_id, request_id, etc.

    Example:
        bind_context(tenant_id="acme", request_id="abc-123")
        logger.info("Processing")  # Will include tenant_id and request_id
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_context() -> None:
    """Clear all bound context variables."""
    structlog.contextvars.clear_contextvars()


def unbind_context(*keys: str) -> None:
    """Remove specific context variables.

    Args:
        *keys: Context variable names to remove
    """
    structlog.contextvars.unbind_contextvars(*keys)
