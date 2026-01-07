"""Prometheus Metrics Middleware for Control-Plane API.

Collects and exposes HTTP metrics for monitoring.
"""

import re
import time
from typing import Callable

from fastapi import Request, Response
from prometheus_client import Counter, Histogram, Gauge, Info, generate_latest, CONTENT_TYPE_LATEST
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

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
        # Skip metrics endpoint to avoid recursion
        if request.url.path == "/metrics":
            return await call_next(request)

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
# Metrics Endpoint
# =============================================================================


def get_metrics() -> StarletteResponse:
    """Generate Prometheus metrics response."""
    return StarletteResponse(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
