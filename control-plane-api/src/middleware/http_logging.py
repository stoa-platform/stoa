# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""HTTP Request/Response Logging Middleware.

CAB-330: Middleware for detailed HTTP logging to support troubleshooting.

Logs incoming requests and outgoing responses with configurable detail levels.
Integrates with Loki via structlog for centralized log aggregation.

Performance optimized: Uses pure ASGI middleware instead of BaseHTTPMiddleware
to avoid response buffering and reduce latency.
"""

import random
import time
import uuid
from typing import Callable

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ..config import settings
from ..logging_config import bind_request_context, clear_context, get_logger

logger = get_logger(__name__)


class HTTPLoggingMiddleware:
    """Pure ASGI middleware for HTTP request/response logging.

    Performance optimized:
    - No response buffering (unlike BaseHTTPMiddleware)
    - Streaming-friendly
    - Minimal overhead for excluded paths

    Features:
    - Request/response logging with timing
    - Configurable detail levels (headers, body)
    - Path exclusion for health checks
    - Sampling for high-traffic endpoints
    - Slow request detection and alerting
    """

    def __init__(self, app: ASGIApp):
        self.app = app
        self.exclude_paths = frozenset(settings.log_exclude_paths_list)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI interface."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # Fast path: skip excluded paths with no overhead
        if path in self.exclude_paths:
            await self.app(scope, receive, send)
            return

        # Apply sampling
        if random.random() > settings.LOG_ACCESS_SAMPLE_RATE:
            await self.app(scope, receive, send)
            return

        # Extract headers for request ID
        headers = dict(scope.get("headers", []))
        request_id = headers.get(b"x-request-id", b"").decode("utf-8") or str(uuid.uuid4())

        # Extract trace ID
        trace_id = None
        traceparent = headers.get(b"traceparent", b"").decode("utf-8")
        if traceparent and "-" in traceparent:
            parts = traceparent.split("-")
            if len(parts) > 1:
                trace_id = parts[1]
        if not trace_id:
            trace_id = headers.get(b"x-trace-id", b"").decode("utf-8") or None

        # Bind request context
        request_id = bind_request_context(request_id=request_id, trace_id=trace_id)

        # Record start time
        start_time = time.perf_counter()

        # Extract request info
        method = scope.get("method", "GET")
        client_ip = self._get_client_ip_from_scope(scope, headers)

        # Log request start
        if settings.LOG_DEBUG_HTTP_REQUESTS:
            logger.debug(
                "http_request_start",
                request_id=request_id,
                method=method,
                path=path,
                client_ip=client_ip,
            )
        else:
            logger.info("http_request", method=method, path=path, client_ip=client_ip)

        # Track response status
        response_status = 200
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_status, response_started

            if message["type"] == "http.response.start":
                response_status = message.get("status", 200)
                response_started = True

                # Add request ID to response headers
                headers_list = list(message.get("headers", []))
                headers_list.append((b"x-request-id", request_id.encode("utf-8")))
                message = {**message, "headers": headers_list}

            await send(message)

            # Log on response body completion
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                duration_ms = (time.perf_counter() - start_time) * 1000
                self._log_response(method, path, response_status, request_id, duration_ms)
                clear_context()

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "Request failed with exception",
                request_id=request_id,
                method=method,
                path=path,
                duration_ms=round(duration_ms, 2),
                error=str(e),
                error_type=type(e).__name__,
            )
            clear_context()
            raise

    def _log_response(
        self, method: str, path: str, status_code: int, request_id: str, duration_ms: float
    ) -> None:
        """Log response details."""
        is_slow = duration_ms > settings.LOG_SLOW_REQUEST_THRESHOLD_MS
        is_error = status_code >= 400

        log_data = {
            "request_id": request_id,
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": round(duration_ms, 2),
        }

        if is_slow:
            log_data["slow_request"] = True

        if is_error and status_code >= 500:
            logger.error("HTTP request completed with server error", **log_data)
        elif is_error:
            logger.warning("HTTP request completed with client error", **log_data)
        elif is_slow:
            logger.warning("Slow HTTP request detected", **log_data)
        elif settings.LOG_DEBUG_HTTP_RESPONSES:
            logger.debug("HTTP request completed", **log_data)
        else:
            logger.info(
                "HTTP response",
                method=method,
                path=path,
                status=status_code,
                duration_ms=round(duration_ms, 2),
            )

    def _get_client_ip_from_scope(self, scope: Scope, headers: dict) -> str:
        """Extract client IP from scope and headers."""
        # Check X-Forwarded-For header
        forwarded_for = headers.get(b"x-forwarded-for", b"").decode("utf-8")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        # Check X-Real-IP header
        real_ip = headers.get(b"x-real-ip", b"").decode("utf-8")
        if real_ip:
            return real_ip

        # Fall back to client from scope
        client = scope.get("client")
        if client:
            return client[0]

        return "unknown"
