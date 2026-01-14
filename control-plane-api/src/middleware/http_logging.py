"""HTTP Request/Response Logging Middleware.

CAB-330: Middleware for detailed HTTP logging to support troubleshooting.

Logs incoming requests and outgoing responses with configurable detail levels.
Integrates with Loki via structlog for centralized log aggregation.
"""

import time
import random
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ..config import settings
from ..logging_config import get_logger, bind_request_context, clear_context

logger = get_logger(__name__)


class HTTPLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware that logs HTTP requests and responses.

    Features:
    - Request/response logging with timing
    - Configurable detail levels (headers, body)
    - Path exclusion for health checks
    - Sampling for high-traffic endpoints
    - Slow request detection and alerting
    """

    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        self.exclude_paths = set(settings.log_exclude_paths_list)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and log details."""
        # Skip excluded paths (health checks, metrics)
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        # Apply sampling
        if random.random() > settings.LOG_ACCESS_SAMPLE_RATE:
            return await call_next(request)

        # Extract request ID from headers or generate new one
        request_id = request.headers.get("X-Request-ID")
        trace_id = request.headers.get("X-Trace-ID") or request.headers.get("traceparent", "").split("-")[1] if "-" in request.headers.get("traceparent", "") else None

        # Bind request context for all logs in this request
        request_id = bind_request_context(
            request_id=request_id,
            trace_id=trace_id,
        )

        # Record start time
        start_time = time.perf_counter()

        # Log incoming request
        await self._log_request(request, request_id)

        # Process request
        try:
            response = await call_next(request)
        except Exception as e:
            # Log error and re-raise
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "Request failed with exception",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                duration_ms=round(duration_ms, 2),
                error=str(e),
                error_type=type(e).__name__,
            )
            clear_context()
            raise

        # Calculate duration
        duration_ms = (time.perf_counter() - start_time) * 1000

        # Log response
        await self._log_response(request, response, request_id, duration_ms)

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id

        # Clear context for next request
        clear_context()

        return response

    async def _log_request(self, request: Request, request_id: str) -> None:
        """Log incoming request details."""
        log_data = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "query": str(request.query_params) if request.query_params else None,
            "client_ip": self._get_client_ip(request),
            "user_agent": request.headers.get("User-Agent"),
        }

        # Add headers if debug enabled
        if settings.LOG_DEBUG_HTTP_HEADERS:
            log_data["headers"] = self._sanitize_headers(dict(request.headers))

        # Add body if debug enabled (only for non-GET requests)
        if settings.LOG_DEBUG_HTTP_BODY and request.method not in ("GET", "HEAD", "OPTIONS"):
            try:
                body = await request.body()
                if body:
                    # Limit body size
                    body_str = body.decode("utf-8")[:1000]
                    log_data["body_preview"] = body_str
                    log_data["body_size"] = len(body)
            except Exception:
                pass

        if settings.LOG_DEBUG_HTTP_REQUESTS:
            logger.debug("http_request_start", **log_data)
        else:
            logger.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                client_ip=log_data["client_ip"],
            )

    async def _log_response(
        self, request: Request, response: Response, request_id: str, duration_ms: float
    ) -> None:
        """Log outgoing response details."""
        is_slow = duration_ms > settings.LOG_SLOW_REQUEST_THRESHOLD_MS
        is_error = response.status_code >= 400

        log_data = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
        }

        if is_slow:
            log_data["slow_request"] = True

        # Add headers if debug enabled
        if settings.LOG_DEBUG_HTTP_HEADERS:
            log_data["response_headers"] = self._sanitize_headers(dict(response.headers))

        # Choose log level based on status and duration
        # Remove 'event' key if present to avoid conflict with structlog's positional event
        log_data.pop("event", None)

        if is_error and response.status_code >= 500:
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
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=round(duration_ms, 2),
            )

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request, handling proxies."""
        # Check X-Forwarded-For header (from load balancer/proxy)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP (original client)
            return forwarded_for.split(",")[0].strip()

        # Check X-Real-IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # Fall back to direct client
        if request.client:
            return request.client.host

        return "unknown"

    def _sanitize_headers(self, headers: dict) -> dict:
        """Remove or mask sensitive headers."""
        sensitive_patterns = settings.log_masking_patterns_list
        result = {}

        for key, value in headers.items():
            key_lower = key.lower()
            if any(pattern.lower() in key_lower for pattern in sensitive_patterns):
                result[key] = "[REDACTED]"
            else:
                result[key] = value

        return result
