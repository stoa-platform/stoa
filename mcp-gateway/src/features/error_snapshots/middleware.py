"""
MCP Error Snapshot Middleware

FastAPI middleware for automatic error capture on MCP Gateway.
"""

import time
from typing import Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from .config import get_mcp_snapshot_settings
from .models import MCPErrorType, MCPServerContext
from .capture import capture_mcp_error

logger = structlog.get_logger(__name__)


class MCPErrorSnapshotMiddleware(BaseHTTPMiddleware):
    """
    Middleware for capturing error snapshots on MCP Gateway requests.

    Captures:
    - HTTP 4xx/5xx responses
    - Request timeouts
    - Unhandled exceptions

    Does NOT block the response - capture is async.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self._settings = get_mcp_snapshot_settings()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self._settings.enabled:
            return await call_next(request)

        # Skip excluded paths
        path = request.url.path
        if any(path.startswith(exclude) for exclude in self._settings.exclude_paths):
            return await call_next(request)

        start_time = time.perf_counter()
        error_type: MCPErrorType | None = None
        error_message: str | None = None
        exception_caught: Exception | None = None

        try:
            response = await call_next(request)
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            # Capture on error status codes
            if response.status_code >= 400:
                error_type = self._classify_http_error(response.status_code, path)
                error_message = f"HTTP {response.status_code} on {request.method} {path}"

                await capture_mcp_error(
                    request=request,
                    response_status=response.status_code,
                    error_type=error_type,
                    error_message=error_message,
                )

            return response

        except TimeoutError as e:
            exception_caught = e
            error_type = MCPErrorType.TOOL_TIMEOUT
            error_message = f"Timeout on {request.method} {path}: {str(e)}"
            raise

        except Exception as e:
            exception_caught = e
            error_type = MCPErrorType.SERVER_INTERNAL_ERROR
            error_message = f"Unhandled exception on {request.method} {path}: {str(e)}"
            raise

        finally:
            # Capture exceptions if they occurred
            if exception_caught and error_type:
                try:
                    await capture_mcp_error(
                        request=request,
                        response_status=500,
                        error_type=error_type,
                        error_message=error_message or str(exception_caught),
                        exception=exception_caught,
                    )
                except Exception as capture_error:
                    logger.warning(
                        "mcp_middleware_capture_failed",
                        error=str(capture_error),
                    )

    def _classify_http_error(self, status_code: int, path: str) -> MCPErrorType:
        """Classify HTTP error into MCPErrorType"""
        # Tool-specific paths
        if "/tools/" in path:
            if status_code == 404:
                return MCPErrorType.TOOL_NOT_FOUND
            if status_code == 422:
                return MCPErrorType.TOOL_VALIDATION_ERROR
            if status_code == 504:
                return MCPErrorType.TOOL_TIMEOUT

        # Server errors
        if status_code == 429:
            return MCPErrorType.SERVER_RATE_LIMITED
        if status_code == 401:
            return MCPErrorType.SERVER_AUTH_FAILURE
        if status_code == 403:
            return MCPErrorType.POLICY_DENIED
        if status_code == 503:
            return MCPErrorType.SERVER_UNAVAILABLE
        if status_code == 504:
            return MCPErrorType.SERVER_TIMEOUT

        # Generic
        if status_code >= 500:
            return MCPErrorType.SERVER_INTERNAL_ERROR

        return MCPErrorType.UNKNOWN


def add_error_snapshot_middleware(app: ASGIApp) -> None:
    """Add error snapshot middleware to FastAPI app"""
    settings = get_mcp_snapshot_settings()

    if not settings.enabled:
        logger.info("mcp_error_snapshot_middleware_disabled")
        return

    app.add_middleware(MCPErrorSnapshotMiddleware)
    logger.info("mcp_error_snapshot_middleware_enabled")
