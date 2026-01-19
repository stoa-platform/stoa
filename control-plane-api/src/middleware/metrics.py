"""Prometheus Metrics Middleware for Control-Plane API.

Collects and exposes HTTP metrics for monitoring.

Performance optimized: Uses pure ASGI middleware instead of BaseHTTPMiddleware
to avoid response buffering and reduce latency.
"""

import re
import time
from typing import Callable

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
)
from starlette.responses import Response as StarletteResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ..config import settings

# Metrics prefix
METRICS_PREFIX = "stoa_control_plane"


# =============================================================================
# Metrics Definitions
# =============================================================================

# HTTP Metrics
HTTP_REQUESTS_TOTAL = Counter(
    f"{METRICS_PREFIX}_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    f"{METRICS_PREFIX}_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

HTTP_REQUESTS_IN_PROGRESS = Gauge(
    f"{METRICS_PREFIX}_http_requests_in_progress",
    "Number of HTTP requests in progress",
    ["method", "endpoint"],
)

# Service Info
SERVICE_INFO = Info(
    f"{METRICS_PREFIX}_service",
    "Service information",
)

# Initialize service info
SERVICE_INFO.info({
    "name": "stoa-control-plane-api",
    "version": settings.VERSION,
})

# Pre-compiled regex patterns for path normalization
UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
NUMERIC_ID_PATTERN = re.compile(r"/\d+(?=/|$)")


# =============================================================================
# Middleware
# =============================================================================


class MetricsMiddleware:
    """Pure ASGI middleware for collecting HTTP metrics.

    Performance optimized:
    - No response buffering (unlike BaseHTTPMiddleware)
    - Pre-compiled regex patterns
    - Minimal overhead
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI interface."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # Skip metrics endpoint to avoid recursion
        if path == "/metrics":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        endpoint = self._normalize_path(path)

        # Track in-progress requests
        HTTP_REQUESTS_IN_PROGRESS.labels(method=method, endpoint=endpoint).inc()

        start_time = time.perf_counter()
        status_code = 500  # Default to 500 in case of unhandled exception

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 200)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            # Record metrics
            duration = time.perf_counter() - start_time

            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method,
                endpoint=endpoint,
            ).observe(duration)

            HTTP_REQUESTS_TOTAL.labels(
                method=method,
                endpoint=endpoint,
                status_code=str(status_code),
            ).inc()

            HTTP_REQUESTS_IN_PROGRESS.labels(method=method, endpoint=endpoint).dec()

    def _normalize_path(self, path: str) -> str:
        """Normalize path for metrics labels.

        Replaces dynamic segments (UUIDs, IDs) with placeholders
        to prevent high cardinality.
        """
        # Replace UUIDs
        path = UUID_PATTERN.sub("{id}", path)
        # Replace numeric IDs
        path = NUMERIC_ID_PATTERN.sub("/{id}", path)
        return path


# =============================================================================
# Metrics Endpoint
# =============================================================================


def get_metrics() -> StarletteResponse:
    """Generate Prometheus metrics response."""
    return StarletteResponse(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
