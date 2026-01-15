"""FastAPI middleware for automatic error snapshot capture.

CAB-397: Intercepts HTTP responses and captures snapshots on errors.
Designed to be non-blocking and failure-tolerant.
"""

import asyncio
import logging
import time
from typing import Any, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import SnapshotSettings
from .models import SnapshotTrigger
from .service import SnapshotService

logger = logging.getLogger(__name__)


class ErrorSnapshotMiddleware:
    """ASGI middleware for automatic error snapshot capture.

    Features:
    - Captures request/response on 4xx/5xx errors (configurable)
    - Non-blocking async capture via background tasks
    - Path exclusion for health checks, metrics, etc.
    - Failure-tolerant (never crashes the main app)
    - Extracts tenant_id from JWT or headers
    """

    def __init__(self, app: ASGIApp, service: SnapshotService):
        self.app = app
        self.service = service
        self.settings = service.settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Skip excluded paths
        path = scope.get("path", "")
        if self._should_skip_path(path):
            await self.app(scope, receive, send)
            return

        # Capture request body (need to buffer it)
        request_body_chunks: list[bytes] = []
        request_complete = False

        async def receive_wrapper() -> Message:
            nonlocal request_complete
            message = await receive()

            if message["type"] == "http.request":
                body = message.get("body", b"")
                if body:
                    # Limit captured body size
                    if sum(len(c) for c in request_body_chunks) < self.settings.max_body_size:
                        request_body_chunks.append(body)

                if not message.get("more_body", False):
                    request_complete = True

            return message

        # Track response
        response_status = 200
        response_headers: dict[str, str] = {}
        response_body_chunks: list[bytes] = []
        start_time = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal response_status, response_headers

            if message["type"] == "http.response.start":
                response_status = message["status"]
                # Parse headers from list of tuples
                headers = message.get("headers", [])
                response_headers = {
                    k.decode("utf-8") if isinstance(k, bytes) else k:
                    v.decode("utf-8") if isinstance(v, bytes) else v
                    for k, v in headers
                }

            elif message["type"] == "http.response.body":
                body = message.get("body", b"")
                if body:
                    # Limit captured body size
                    if sum(len(c) for c in response_body_chunks) < self.settings.max_body_size:
                        response_body_chunks.append(body)

            await send(message)

        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        except Exception as e:
            # Re-raise but still try to capture
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            await self._safe_capture(
                scope=scope,
                request_body=b"".join(request_body_chunks),
                response_status=500,
                response_headers={},
                response_body=str(e).encode("utf-8"),
                duration_ms=duration_ms,
            )
            raise
        else:
            # Check if we should capture
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            if self._should_capture(response_status, duration_ms):
                # Capture in background to not block response
                if self.settings.async_capture:
                    asyncio.create_task(
                        self._safe_capture(
                            scope=scope,
                            request_body=b"".join(request_body_chunks),
                            response_status=response_status,
                            response_headers=response_headers,
                            response_body=b"".join(response_body_chunks),
                            duration_ms=duration_ms,
                        )
                    )
                else:
                    await self._safe_capture(
                        scope=scope,
                        request_body=b"".join(request_body_chunks),
                        response_status=response_status,
                        response_headers=response_headers,
                        response_body=b"".join(response_body_chunks),
                        duration_ms=duration_ms,
                    )

    def _should_skip_path(self, path: str) -> bool:
        """Check if path should be excluded from capture."""
        for excluded in self.settings.exclude_paths_list:
            if path.startswith(excluded):
                return True
        return False

    def _should_capture(self, status: int, duration_ms: int) -> bool:
        """Determine if snapshot should be captured based on config."""
        # Check for timeout
        if duration_ms >= self.settings.timeout_threshold_ms:
            return self.settings.capture_on_timeout

        # Check for 4xx errors
        if 400 <= status < 500:
            return self.settings.capture_on_4xx

        # Check for 5xx errors
        if status >= 500:
            return self.settings.capture_on_5xx

        return False

    def _determine_trigger(self, status: int, duration_ms: int) -> SnapshotTrigger:
        """Determine what triggered the capture."""
        if duration_ms >= self.settings.timeout_threshold_ms:
            return SnapshotTrigger.TIMEOUT
        if status >= 500:
            return SnapshotTrigger.ERROR_5XX
        if 400 <= status < 500:
            return SnapshotTrigger.ERROR_4XX
        return SnapshotTrigger.MANUAL

    def _extract_tenant_id(self, scope: Scope) -> str:
        """Extract tenant_id from request scope.

        Checks (in order):
        1. X-Tenant-ID header
        2. JWT claims (if available in scope state)
        3. Default to "unknown"
        """
        headers = dict(scope.get("headers", []))

        # Check X-Tenant-ID header
        tenant_header = headers.get(b"x-tenant-id")
        if tenant_header:
            return tenant_header.decode("utf-8")

        # Check scope state for user info (set by auth middleware)
        state = scope.get("state", {})
        user = state.get("user")
        if user and hasattr(user, "tenant_id"):
            return user.tenant_id

        return "unknown"

    def _extract_trace_id(self, scope: Scope) -> str | None:
        """Extract trace ID from request headers."""
        headers = dict(scope.get("headers", []))

        # Common trace ID headers
        for header_name in [
            b"x-trace-id",
            b"x-request-id",
            b"traceparent",
            b"x-correlation-id",
        ]:
            value = headers.get(header_name)
            if value:
                return value.decode("utf-8")

        return None

    async def _safe_capture(
        self,
        scope: Scope,
        request_body: bytes,
        response_status: int,
        response_headers: dict[str, str],
        response_body: bytes,
        duration_ms: int,
    ) -> None:
        """Capture snapshot with error handling.

        Never raises exceptions - logs warnings on failure.
        """
        try:
            # Build a minimal Request object for the service
            request = Request(scope)

            tenant_id = self._extract_tenant_id(scope)
            trace_id = self._extract_trace_id(scope)
            trigger = self._determine_trigger(response_status, duration_ms)

            await self.service.capture_error(
                request=request,
                response_status=response_status,
                response_headers=response_headers,
                request_body=request_body,
                response_body=response_body,
                duration_ms=duration_ms,
                tenant_id=tenant_id,
                trigger=trigger,
                trace_id=trace_id,
            )

        except Exception as e:
            # Log but never crash
            logger.warning(
                f"snapshot_capture_failed: {e} path={scope.get('path')} status={response_status}"
            )


class SimpleErrorSnapshotMiddleware(BaseHTTPMiddleware):
    """Simpler middleware using Starlette's BaseHTTPMiddleware.

    Alternative implementation that's easier to understand
    but may have slightly different behavior for streaming responses.
    """

    def __init__(self, app: ASGIApp, service: SnapshotService):
        super().__init__(app)
        self.service = service
        self.settings = service.settings

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip excluded paths
        if any(
            request.url.path.startswith(p) for p in self.settings.exclude_paths_list
        ):
            return await call_next(request)

        start_time = time.perf_counter()

        # Read request body
        request_body = await request.body()

        try:
            response = await call_next(request)
        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            await self._safe_capture(
                request=request,
                request_body=request_body,
                response_status=500,
                response_headers={},
                response_body=str(e).encode(),
                duration_ms=duration_ms,
            )
            raise

        duration_ms = int((time.perf_counter() - start_time) * 1000)

        # Check if should capture
        if self._should_capture(response.status_code, duration_ms):
            # Read response body (requires consuming the streaming response)
            response_body = b""
            async for chunk in response.body_iterator:
                response_body += chunk

            # Recreate response with body
            response = Response(
                content=response_body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

            if self.settings.async_capture:
                asyncio.create_task(
                    self._safe_capture(
                        request=request,
                        request_body=request_body,
                        response_status=response.status_code,
                        response_headers=dict(response.headers),
                        response_body=response_body,
                        duration_ms=duration_ms,
                    )
                )
            else:
                await self._safe_capture(
                    request=request,
                    request_body=request_body,
                    response_status=response.status_code,
                    response_headers=dict(response.headers),
                    response_body=response_body,
                    duration_ms=duration_ms,
                )

        return response

    def _should_capture(self, status: int, duration_ms: int) -> bool:
        if duration_ms >= self.settings.timeout_threshold_ms:
            return self.settings.capture_on_timeout
        if 400 <= status < 500:
            return self.settings.capture_on_4xx
        if status >= 500:
            return self.settings.capture_on_5xx
        return False

    def _determine_trigger(self, status: int, duration_ms: int) -> SnapshotTrigger:
        if duration_ms >= self.settings.timeout_threshold_ms:
            return SnapshotTrigger.TIMEOUT
        if status >= 500:
            return SnapshotTrigger.ERROR_5XX
        if 400 <= status < 500:
            return SnapshotTrigger.ERROR_4XX
        return SnapshotTrigger.MANUAL

    async def _safe_capture(
        self,
        request: Request,
        request_body: bytes,
        response_status: int,
        response_headers: dict[str, str],
        response_body: bytes,
        duration_ms: int,
    ) -> None:
        try:
            tenant_id = request.headers.get("x-tenant-id", "unknown")
            if hasattr(request.state, "user") and request.state.user:
                tenant_id = getattr(request.state.user, "tenant_id", tenant_id)

            trace_id = (
                request.headers.get("x-trace-id")
                or request.headers.get("x-request-id")
            )

            trigger = self._determine_trigger(response_status, duration_ms)

            await self.service.capture_error(
                request=request,
                response_status=response_status,
                response_headers=response_headers,
                request_body=request_body,
                response_body=response_body,
                duration_ms=duration_ms,
                tenant_id=tenant_id,
                trigger=trigger,
                trace_id=trace_id,
            )
        except Exception as e:
            logger.warning(
                f"snapshot_capture_failed: {e} path={request.url.path} status={response_status}"
            )
