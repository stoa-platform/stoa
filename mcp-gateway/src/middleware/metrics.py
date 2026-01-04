"""Prometheus Metrics Middleware.

Collects and exposes metrics for the MCP Gateway.
"""

import time
from typing import Callable

from fastapi import Request, Response
from prometheus_client import Counter, Histogram, Gauge, Info
from starlette.middleware.base import BaseHTTPMiddleware

from ..config import get_settings

settings = get_settings()
prefix = settings.metrics_prefix


# =============================================================================
# Metrics Definitions
# =============================================================================

# HTTP Metrics
HTTP_REQUESTS_TOTAL = Counter(
    f"{prefix}_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    f"{prefix}_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

HTTP_REQUESTS_IN_PROGRESS = Gauge(
    f"{prefix}_http_requests_in_progress",
    "Number of HTTP requests in progress",
    ["method", "endpoint"],
)

# MCP Tool Metrics
MCP_TOOL_INVOCATIONS_TOTAL = Counter(
    f"{prefix}_mcp_tool_invocations_total",
    "Total MCP tool invocations",
    ["tool_name", "status"],
)

MCP_TOOL_INVOCATION_DURATION_SECONDS = Histogram(
    f"{prefix}_mcp_tool_invocation_duration_seconds",
    "MCP tool invocation duration in seconds",
    ["tool_name"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

MCP_TOOLS_REGISTERED = Gauge(
    f"{prefix}_mcp_tools_registered",
    "Number of registered MCP tools",
)

# Authentication Metrics
AUTH_REQUESTS_TOTAL = Counter(
    f"{prefix}_auth_requests_total",
    "Total authentication attempts",
    ["status", "reason"],
)

AUTH_TOKEN_VALIDATION_DURATION_SECONDS = Histogram(
    f"{prefix}_auth_token_validation_duration_seconds",
    "JWT token validation duration in seconds",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25),
)

# Backend Metrics
BACKEND_REQUESTS_TOTAL = Counter(
    f"{prefix}_backend_requests_total",
    "Total backend API requests",
    ["backend", "method", "status_code"],
)

BACKEND_REQUEST_DURATION_SECONDS = Histogram(
    f"{prefix}_backend_request_duration_seconds",
    "Backend API request duration in seconds",
    ["backend", "method"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Service Info
SERVICE_INFO = Info(
    f"{prefix}_service",
    "Service information",
)

# Initialize service info
SERVICE_INFO.info({
    "name": "stoa-mcp-gateway",
    "version": settings.app_version,
    "environment": settings.environment,
})


# =============================================================================
# Middleware
# =============================================================================


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware for collecting HTTP metrics."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """Process request and collect metrics."""
        method = request.method
        # Normalize endpoint for metrics (remove IDs, etc.)
        endpoint = self._normalize_path(request.url.path)

        # Track in-progress requests
        HTTP_REQUESTS_IN_PROGRESS.labels(
            method=method,
            endpoint=endpoint,
        ).inc()

        start_time = time.time()

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            status_code = 500
            raise
        finally:
            # Record duration
            duration = time.time() - start_time
            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method,
                endpoint=endpoint,
            ).observe(duration)

            # Record request count
            HTTP_REQUESTS_TOTAL.labels(
                method=method,
                endpoint=endpoint,
                status_code=str(status_code),
            ).inc()

            # Decrease in-progress counter
            HTTP_REQUESTS_IN_PROGRESS.labels(
                method=method,
                endpoint=endpoint,
            ).dec()

        return response

    def _normalize_path(self, path: str) -> str:
        """Normalize path for metrics labels.

        Replaces dynamic segments (UUIDs, IDs) with placeholders
        to prevent high cardinality.
        """
        import re

        # Replace UUIDs
        path = re.sub(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "{id}",
            path,
            flags=re.IGNORECASE,
        )

        # Replace numeric IDs
        path = re.sub(r"/\d+(?=/|$)", "/{id}", path)

        return path


# =============================================================================
# Metric Recording Functions
# =============================================================================


def record_tool_invocation(
    tool_name: str,
    duration_seconds: float,
    success: bool,
) -> None:
    """Record metrics for a tool invocation."""
    status = "success" if success else "error"
    MCP_TOOL_INVOCATIONS_TOTAL.labels(
        tool_name=tool_name,
        status=status,
    ).inc()
    MCP_TOOL_INVOCATION_DURATION_SECONDS.labels(
        tool_name=tool_name,
    ).observe(duration_seconds)


def record_auth_attempt(
    success: bool,
    reason: str = "",
) -> None:
    """Record metrics for an authentication attempt."""
    status = "success" if success else "failure"
    AUTH_REQUESTS_TOTAL.labels(
        status=status,
        reason=reason,
    ).inc()


def record_backend_request(
    backend: str,
    method: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    """Record metrics for a backend API request."""
    BACKEND_REQUESTS_TOTAL.labels(
        backend=backend,
        method=method,
        status_code=str(status_code),
    ).inc()
    BACKEND_REQUEST_DURATION_SECONDS.labels(
        backend=backend,
        method=method,
    ).observe(duration_seconds)


def update_tools_registered(count: int) -> None:
    """Update the count of registered tools."""
    MCP_TOOLS_REGISTERED.set(count)
