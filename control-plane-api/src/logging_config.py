"""Structured Logging Configuration for Control-Plane API.

CAB-281: Standardized JSON logging for Loki integration.
CAB-330: Enhanced logging with component-level control, masking, and context binding.

Uses structlog for consistent JSON log output compatible with
Promtail/Loki log aggregation pipeline.
"""

import logging
import re
import sys
import uuid
from typing import Any, Literal

import structlog
from structlog.types import Processor

from .config import settings


class SensitiveDataMasker:
    """Processor to mask sensitive data in log output."""

    def __init__(self, patterns: list[str], mask_value: str = "[REDACTED]"):
        self.patterns = [re.compile(p, re.IGNORECASE) for p in patterns]
        self.mask_value = mask_value

    def __call__(
        self, logger: logging.Logger, method_name: str, event_dict: dict[str, Any]
    ) -> dict[str, Any]:
        """Mask sensitive values in the event dict."""
        if not settings.LOG_MASKING_ENABLED:
            return event_dict

        return self._mask_dict(event_dict)

    def _mask_dict(self, d: dict[str, Any]) -> dict[str, Any]:
        """Recursively mask sensitive keys in a dict."""
        result = {}
        for key, value in d.items():
            if any(pattern.search(key) for pattern in self.patterns):
                result[key] = self.mask_value
            elif isinstance(value, dict):
                result[key] = self._mask_dict(value)
            elif isinstance(value, list):
                result[key] = [
                    self._mask_dict(v) if isinstance(v, dict) else v for v in value
                ]
            else:
                result[key] = value
        return result


class ComponentLevelFilter(logging.Filter):
    """Filter that applies per-component log levels."""

    def __init__(self, component_levels: dict[str, str], default_level: str = "INFO"):
        super().__init__()
        self.component_levels = {
            name: getattr(logging, level.upper(), logging.INFO)
            for name, level in component_levels.items()
        }
        self.default_level = getattr(logging, default_level.upper(), logging.INFO)

    def filter(self, record: logging.LogRecord) -> bool:
        """Apply component-specific log level filtering."""
        # Find the most specific matching component level
        logger_name = record.name
        level = self.default_level

        # Check for exact match first
        if logger_name in self.component_levels:
            level = self.component_levels[logger_name]
        else:
            # Check for parent logger matches
            for component, component_level in self.component_levels.items():
                if logger_name.startswith(component + "."):
                    level = component_level
                    break
                elif component.startswith(logger_name + "."):
                    continue
                elif logger_name.startswith(component):
                    level = component_level

        return record.levelno >= level


def add_app_context(
    logger: logging.Logger, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Add application context to all log entries."""
    # Add environment and version
    if settings.LOG_CONTEXT_TENANT_ID or settings.LOG_CONTEXT_USER_ID:
        event_dict.setdefault("environment", settings.ENVIRONMENT)
        event_dict.setdefault("version", settings.VERSION)

    # Add component/service identifier
    if "component" not in event_dict:
        event_dict["component"] = "control-plane-api"

    return event_dict


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

    # Get component-specific levels
    component_levels = settings.log_components_dict

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Allow all, filter per-component

    # Clear existing handlers
    root_logger.handlers.clear()

    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(message)s"))

    # Add component-level filter
    handler.addFilter(
        ComponentLevelFilter(component_levels, default_level=level)
    )

    root_logger.addHandler(handler)

    # Configure specific loggers to reduce noise
    noisy_loggers = [
        "urllib3",
        "httpcore",
        "httpx",
        "asyncio",
        "aiokafka",
        "kafka",
    ]
    for logger_name in noisy_loggers:
        noisy_logger = logging.getLogger(logger_name)
        log_level_for_logger = component_levels.get(logger_name, "WARNING")
        noisy_logger.setLevel(getattr(logging, log_level_for_logger.upper(), logging.WARNING))

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
        add_app_context,
    ]

    # Add masking processor if enabled
    if settings.LOG_MASKING_ENABLED:
        masker = SensitiveDataMasker(settings.log_masking_patterns_list)
        shared_processors.append(masker)

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


def generate_request_id() -> str:
    """Generate a unique request ID."""
    return str(uuid.uuid4())


def bind_request_context(
    request_id: str = None,
    tenant_id: str = None,
    user_id: str = None,
    trace_id: str = None,
    span_id: str = None,
) -> str:
    """Bind request-specific context to all logs in the current request.

    Args:
        request_id: Unique request identifier (generated if not provided)
        tenant_id: Tenant identifier
        user_id: User identifier
        trace_id: Distributed trace ID
        span_id: Distributed span ID

    Returns:
        The request_id (generated or provided)
    """
    req_id = request_id or generate_request_id()

    context = {}
    if settings.LOG_CONTEXT_REQUEST_ID:
        context["request_id"] = req_id
    if settings.LOG_CONTEXT_TENANT_ID and tenant_id:
        context["tenant_id"] = tenant_id
    if settings.LOG_CONTEXT_USER_ID and user_id:
        context["user_id"] = user_id
    if settings.LOG_CONTEXT_TRACE_ID and trace_id:
        context["trace_id"] = trace_id
    if settings.LOG_CONTEXT_TRACE_ID and span_id:
        context["span_id"] = span_id

    bind_context(**context)
    return req_id
