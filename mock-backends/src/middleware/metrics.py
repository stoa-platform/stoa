# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Prometheus metrics middleware.

CAB-1018: Mock APIs for Central Bank Demo
Exposes HTTP request metrics for observability.
"""

import time
import re
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

from src.config import settings

# Metrics prefix
PREFIX = settings.metrics_prefix

# HTTP Request metrics
HTTP_REQUESTS_TOTAL = Counter(
    f"{PREFIX}_mock_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    f"{PREFIX}_mock_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
)

HTTP_REQUESTS_IN_PROGRESS = Gauge(
    f"{PREFIX}_mock_http_requests_in_progress",
    "HTTP requests currently in progress",
    ["method", "endpoint"],
)

# Service info gauge
SERVICE_INFO = Gauge(
    f"{PREFIX}_mock_service_info",
    "Service information",
    ["version", "environment"],
)
SERVICE_INFO.labels(version=settings.app_version, environment=settings.environment).set(1)

# Path normalization patterns (prevent high cardinality)
PATH_PATTERNS = [
    (re.compile(r"/v1/settlements/[^/]+"), "/v1/settlements/{id}"),
    (re.compile(r"/v1/screening/[^/]+"), "/v1/screening/{id}"),
    (re.compile(r"/demo/trigger/[^/]+"), "/demo/trigger/{scenario}"),
]


def normalize_path(path: str) -> str:
    """Normalize path to prevent high cardinality in metrics."""
    for pattern, replacement in PATH_PATTERNS:
        if pattern.match(path):
            return replacement
    return path


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to collect Prometheus metrics for HTTP requests."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip metrics for /metrics and /health endpoints
        if request.url.path in ("/metrics", "/health", "/health/live", "/health/ready"):
            return await call_next(request)

        method = request.method
        endpoint = normalize_path(request.url.path)

        # Track in-progress requests
        HTTP_REQUESTS_IN_PROGRESS.labels(method=method, endpoint=endpoint).inc()

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            status_code = 500
            raise
        finally:
            # Record metrics
            duration = time.perf_counter() - start_time

            HTTP_REQUESTS_TOTAL.labels(
                method=method, endpoint=endpoint, status_code=status_code
            ).inc()

            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method, endpoint=endpoint
            ).observe(duration)

            HTTP_REQUESTS_IN_PROGRESS.labels(method=method, endpoint=endpoint).dec()

        return response


def get_metrics() -> bytes:
    """Generate Prometheus metrics in text format."""
    return generate_latest()


def get_metrics_content_type() -> str:
    """Get the content type for Prometheus metrics."""
    return CONTENT_TYPE_LATEST
