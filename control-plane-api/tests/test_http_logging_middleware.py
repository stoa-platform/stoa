"""Tests for HTTP Logging Middleware — Wave 2

Covers HTTPLoggingMiddleware:
- Non-HTTP scope passthrough
- Path exclusion
- Sampling logic
- Request ID extraction/generation
- Trace ID extraction (traceparent + x-trace-id)
- Client IP extraction (x-forwarded-for, x-real-ip, scope client, unknown)
- Response status tracking + header injection
- Slow request detection
- Error response logging (4xx, 5xx)
- Exception handling with logging
- Debug logging mode
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest


# ── Helpers ────────────────────────────────────────────────────────────


def _make_scope(
    path: str = "/v1/apis",
    method: str = "GET",
    headers: list[tuple[bytes, bytes]] | None = None,
    client: tuple[str, int] | None = ("127.0.0.1", 8000),
    scope_type: str = "http",
) -> dict:
    return {
        "type": scope_type,
        "path": path,
        "method": method,
        "headers": headers or [],
        "client": client,
        "query_string": b"",
    }


def _make_responding_app(*, status: int = 200, body: bytes = b"ok"):
    """Create an ASGI app that sends a complete HTTP response."""

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": status, "headers": []})
        await send({"type": "http.response.body", "body": body, "more_body": False})

    return app


def _make_failing_app(exc):
    """Create an ASGI app that raises an exception."""

    async def app(scope, receive, send):
        raise exc

    return app


async def _invoke(mw, scope):
    """Invoke middleware, collecting sent messages."""
    messages: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        messages.append(message)

    await mw(scope, receive, send)
    return messages


# ── Tests ──────────────────────────────────────────────────────────────


class TestHTTPLoggingMiddlewarePassthrough:
    """Non-HTTP scopes and excluded paths should bypass logging."""

    @patch("src.middleware.http_logging.settings")
    @patch("src.middleware.http_logging.clear_context")
    @patch("src.middleware.http_logging.bind_request_context", return_value="req-123")
    @patch("src.middleware.http_logging.logger")
    def test_non_http_scope_passes_through(self, _log, mock_bind, _clear, _settings):
        from src.middleware.http_logging import HTTPLoggingMiddleware

        inner = AsyncMock()
        mw = HTTPLoggingMiddleware(inner)
        scope = _make_scope(scope_type="websocket")

        asyncio.get_event_loop().run_until_complete(mw(scope, AsyncMock(), AsyncMock()))
        inner.assert_called_once()
        mock_bind.assert_not_called()

    @patch("src.middleware.http_logging.settings")
    @patch("src.middleware.http_logging.clear_context")
    @patch("src.middleware.http_logging.bind_request_context", return_value="req-123")
    @patch("src.middleware.http_logging.logger")
    def test_excluded_path_skips_logging(self, _log, mock_bind, _clear, mock_settings):
        from src.middleware.http_logging import HTTPLoggingMiddleware

        mock_settings.log_exclude_paths_list = ["/health", "/ready"]
        inner = AsyncMock()
        mw = HTTPLoggingMiddleware(inner)

        asyncio.get_event_loop().run_until_complete(
            mw(_make_scope(path="/health"), AsyncMock(), AsyncMock())
        )
        inner.assert_called_once()
        mock_bind.assert_not_called()


class TestHTTPLoggingMiddlewareSampling:
    """Sampling should skip requests based on LOG_ACCESS_SAMPLE_RATE."""

    @patch("src.middleware.http_logging.random")
    @patch("src.middleware.http_logging.settings")
    @patch("src.middleware.http_logging.clear_context")
    @patch("src.middleware.http_logging.bind_request_context", return_value="req-123")
    @patch("src.middleware.http_logging.logger")
    def test_sampling_skips_when_random_exceeds_rate(
        self, _log, mock_bind, _clear, mock_settings, mock_random
    ):
        from src.middleware.http_logging import HTTPLoggingMiddleware

        mock_settings.log_exclude_paths_list = []
        mock_settings.LOG_ACCESS_SAMPLE_RATE = 0.5
        mock_random.random.return_value = 0.8

        inner = AsyncMock()
        mw = HTTPLoggingMiddleware(inner)

        asyncio.get_event_loop().run_until_complete(
            mw(_make_scope(), AsyncMock(), AsyncMock())
        )
        inner.assert_called_once()
        mock_bind.assert_not_called()

    @patch("src.middleware.http_logging.random")
    @patch("src.middleware.http_logging.settings")
    @patch("src.middleware.http_logging.clear_context")
    @patch("src.middleware.http_logging.bind_request_context", return_value="req-123")
    @patch("src.middleware.http_logging.logger")
    def test_sampling_proceeds_when_random_below_rate(
        self, _log, mock_bind, _clear, mock_settings, mock_random
    ):
        from src.middleware.http_logging import HTTPLoggingMiddleware

        mock_settings.log_exclude_paths_list = []
        mock_settings.LOG_ACCESS_SAMPLE_RATE = 0.5
        mock_settings.LOG_DEBUG_HTTP_REQUESTS = False
        mock_settings.LOG_DEBUG_HTTP_RESPONSES = False
        mock_settings.LOG_SLOW_REQUEST_THRESHOLD_MS = 1000
        mock_random.random.return_value = 0.3

        mw = HTTPLoggingMiddleware(_make_responding_app())

        asyncio.get_event_loop().run_until_complete(_invoke(mw, _make_scope()))
        mock_bind.assert_called_once()


class TestHTTPLoggingMiddlewareRequestId:
    """Request ID extraction and generation."""

    @patch("src.middleware.http_logging.random")
    @patch("src.middleware.http_logging.settings")
    @patch("src.middleware.http_logging.clear_context")
    @patch("src.middleware.http_logging.bind_request_context", return_value="from-header")
    @patch("src.middleware.http_logging.logger")
    def test_uses_x_request_id_from_header(
        self, _log, mock_bind, _clear, mock_settings, mock_random
    ):
        from src.middleware.http_logging import HTTPLoggingMiddleware

        mock_settings.log_exclude_paths_list = []
        mock_settings.LOG_ACCESS_SAMPLE_RATE = 1.0
        mock_settings.LOG_DEBUG_HTTP_REQUESTS = False
        mock_settings.LOG_DEBUG_HTTP_RESPONSES = False
        mock_settings.LOG_SLOW_REQUEST_THRESHOLD_MS = 1000
        mock_random.random.return_value = 0.1

        mw = HTTPLoggingMiddleware(_make_responding_app())
        scope = _make_scope(headers=[(b"x-request-id", b"my-custom-id")])

        asyncio.get_event_loop().run_until_complete(_invoke(mw, scope))
        mock_bind.assert_called_once()
        call_kwargs = mock_bind.call_args[1]
        assert call_kwargs["request_id"] == "my-custom-id"

    @patch("src.middleware.http_logging.uuid")
    @patch("src.middleware.http_logging.random")
    @patch("src.middleware.http_logging.settings")
    @patch("src.middleware.http_logging.clear_context")
    @patch("src.middleware.http_logging.bind_request_context", return_value="gen-uuid")
    @patch("src.middleware.http_logging.logger")
    def test_generates_uuid_when_no_request_id_header(
        self, _log, mock_bind, _clear, mock_settings, mock_random, mock_uuid
    ):
        from src.middleware.http_logging import HTTPLoggingMiddleware

        mock_settings.log_exclude_paths_list = []
        mock_settings.LOG_ACCESS_SAMPLE_RATE = 1.0
        mock_settings.LOG_DEBUG_HTTP_REQUESTS = False
        mock_settings.LOG_DEBUG_HTTP_RESPONSES = False
        mock_settings.LOG_SLOW_REQUEST_THRESHOLD_MS = 1000
        mock_random.random.return_value = 0.1
        mock_uuid.uuid4.return_value = "generated-uuid"

        mw = HTTPLoggingMiddleware(_make_responding_app())

        asyncio.get_event_loop().run_until_complete(_invoke(mw, _make_scope()))
        mock_uuid.uuid4.assert_called_once()


class TestHTTPLoggingMiddlewareTraceId:
    """Trace ID extraction from traceparent and x-trace-id headers."""

    @patch("src.middleware.http_logging.random")
    @patch("src.middleware.http_logging.settings")
    @patch("src.middleware.http_logging.clear_context")
    @patch("src.middleware.http_logging.bind_request_context", return_value="req-1")
    @patch("src.middleware.http_logging.logger")
    def test_extracts_trace_id_from_traceparent(
        self, _log, mock_bind, _clear, mock_settings, mock_random
    ):
        from src.middleware.http_logging import HTTPLoggingMiddleware

        mock_settings.log_exclude_paths_list = []
        mock_settings.LOG_ACCESS_SAMPLE_RATE = 1.0
        mock_settings.LOG_DEBUG_HTTP_REQUESTS = False
        mock_settings.LOG_DEBUG_HTTP_RESPONSES = False
        mock_settings.LOG_SLOW_REQUEST_THRESHOLD_MS = 1000
        mock_random.random.return_value = 0.1

        traceparent = b"00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"

        mw = HTTPLoggingMiddleware(_make_responding_app())
        scope = _make_scope(headers=[(b"traceparent", traceparent)])

        asyncio.get_event_loop().run_until_complete(_invoke(mw, scope))
        assert mock_bind.call_args[1]["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"

    @patch("src.middleware.http_logging.random")
    @patch("src.middleware.http_logging.settings")
    @patch("src.middleware.http_logging.clear_context")
    @patch("src.middleware.http_logging.bind_request_context", return_value="req-1")
    @patch("src.middleware.http_logging.logger")
    def test_falls_back_to_x_trace_id(
        self, _log, mock_bind, _clear, mock_settings, mock_random
    ):
        from src.middleware.http_logging import HTTPLoggingMiddleware

        mock_settings.log_exclude_paths_list = []
        mock_settings.LOG_ACCESS_SAMPLE_RATE = 1.0
        mock_settings.LOG_DEBUG_HTTP_REQUESTS = False
        mock_settings.LOG_DEBUG_HTTP_RESPONSES = False
        mock_settings.LOG_SLOW_REQUEST_THRESHOLD_MS = 1000
        mock_random.random.return_value = 0.1

        mw = HTTPLoggingMiddleware(_make_responding_app())
        scope = _make_scope(headers=[(b"x-trace-id", b"my-trace-abc")])

        asyncio.get_event_loop().run_until_complete(_invoke(mw, scope))
        assert mock_bind.call_args[1]["trace_id"] == "my-trace-abc"


class TestHTTPLoggingMiddlewareClientIp:
    """Client IP extraction from various sources."""

    def _extract_ip(self, scope):
        from src.middleware.http_logging import HTTPLoggingMiddleware

        mw = HTTPLoggingMiddleware(AsyncMock())
        headers = dict(scope.get("headers", []))
        return mw._get_client_ip_from_scope(scope, headers)

    def test_client_ip_from_x_forwarded_for(self):
        scope = _make_scope(headers=[(b"x-forwarded-for", b"10.0.0.1, 10.0.0.2")])
        assert self._extract_ip(scope) == "10.0.0.1"

    def test_client_ip_from_x_real_ip(self):
        scope = _make_scope(headers=[(b"x-real-ip", b"172.16.0.1")])
        assert self._extract_ip(scope) == "172.16.0.1"

    def test_client_ip_from_scope_client(self):
        scope = _make_scope(client=("192.168.1.100", 5000))
        assert self._extract_ip(scope) == "192.168.1.100"

    def test_client_ip_unknown_when_no_source(self):
        scope = _make_scope(client=None)
        assert self._extract_ip(scope) == "unknown"

    def test_x_forwarded_for_takes_priority_over_x_real_ip(self):
        scope = _make_scope(
            headers=[
                (b"x-forwarded-for", b"10.10.10.10"),
                (b"x-real-ip", b"20.20.20.20"),
            ]
        )
        assert self._extract_ip(scope) == "10.10.10.10"


class TestHTTPLoggingMiddlewareResponseTracking:
    """Response status tracking, header injection, and logging."""

    @patch("src.middleware.http_logging.random")
    @patch("src.middleware.http_logging.settings")
    @patch("src.middleware.http_logging.clear_context")
    @patch("src.middleware.http_logging.bind_request_context", return_value="req-resp")
    @patch("src.middleware.http_logging.logger")
    def test_x_request_id_added_to_response_headers(
        self, _log, _bind, _clear, mock_settings, mock_random
    ):
        from src.middleware.http_logging import HTTPLoggingMiddleware

        mock_settings.log_exclude_paths_list = []
        mock_settings.LOG_ACCESS_SAMPLE_RATE = 1.0
        mock_settings.LOG_DEBUG_HTTP_REQUESTS = False
        mock_settings.LOG_DEBUG_HTTP_RESPONSES = False
        mock_settings.LOG_SLOW_REQUEST_THRESHOLD_MS = 5000
        mock_random.random.return_value = 0.1

        mw = HTTPLoggingMiddleware(_make_responding_app())
        messages = asyncio.get_event_loop().run_until_complete(
            _invoke(mw, _make_scope())
        )

        start_msg = messages[0]
        assert start_msg["type"] == "http.response.start"
        header_names = [h[0] for h in start_msg["headers"]]
        assert b"x-request-id" in header_names

    @patch("src.middleware.http_logging.random")
    @patch("src.middleware.http_logging.settings")
    @patch("src.middleware.http_logging.clear_context")
    @patch("src.middleware.http_logging.bind_request_context", return_value="req-slow")
    @patch("src.middleware.http_logging.logger")
    def test_slow_request_logged_as_warning(
        self, mock_logger, _bind, _clear, mock_settings, mock_random
    ):
        from src.middleware.http_logging import HTTPLoggingMiddleware

        mock_settings.log_exclude_paths_list = []
        mock_settings.LOG_ACCESS_SAMPLE_RATE = 1.0
        mock_settings.LOG_DEBUG_HTTP_REQUESTS = False
        mock_settings.LOG_DEBUG_HTTP_RESPONSES = False
        mock_settings.LOG_SLOW_REQUEST_THRESHOLD_MS = 0  # Everything is "slow"
        mock_random.random.return_value = 0.1

        mw = HTTPLoggingMiddleware(_make_responding_app())
        asyncio.get_event_loop().run_until_complete(_invoke(mw, _make_scope()))

        mock_logger.warning.assert_called()

    @patch("src.middleware.http_logging.random")
    @patch("src.middleware.http_logging.settings")
    @patch("src.middleware.http_logging.clear_context")
    @patch("src.middleware.http_logging.bind_request_context", return_value="req-5xx")
    @patch("src.middleware.http_logging.logger")
    def test_5xx_logged_as_error(
        self, mock_logger, _bind, _clear, mock_settings, mock_random
    ):
        from src.middleware.http_logging import HTTPLoggingMiddleware

        mock_settings.log_exclude_paths_list = []
        mock_settings.LOG_ACCESS_SAMPLE_RATE = 1.0
        mock_settings.LOG_DEBUG_HTTP_REQUESTS = False
        mock_settings.LOG_DEBUG_HTTP_RESPONSES = False
        mock_settings.LOG_SLOW_REQUEST_THRESHOLD_MS = 99999
        mock_random.random.return_value = 0.1

        mw = HTTPLoggingMiddleware(_make_responding_app(status=500))
        asyncio.get_event_loop().run_until_complete(_invoke(mw, _make_scope()))

        mock_logger.error.assert_called()

    @patch("src.middleware.http_logging.random")
    @patch("src.middleware.http_logging.settings")
    @patch("src.middleware.http_logging.clear_context")
    @patch("src.middleware.http_logging.bind_request_context", return_value="req-4xx")
    @patch("src.middleware.http_logging.logger")
    def test_4xx_logged_as_warning(
        self, mock_logger, _bind, _clear, mock_settings, mock_random
    ):
        from src.middleware.http_logging import HTTPLoggingMiddleware

        mock_settings.log_exclude_paths_list = []
        mock_settings.LOG_ACCESS_SAMPLE_RATE = 1.0
        mock_settings.LOG_DEBUG_HTTP_REQUESTS = False
        mock_settings.LOG_DEBUG_HTTP_RESPONSES = False
        mock_settings.LOG_SLOW_REQUEST_THRESHOLD_MS = 99999
        mock_random.random.return_value = 0.1

        mw = HTTPLoggingMiddleware(_make_responding_app(status=404))
        asyncio.get_event_loop().run_until_complete(_invoke(mw, _make_scope()))

        mock_logger.warning.assert_called()


class TestHTTPLoggingMiddlewareExceptionHandling:
    """Exception propagation with logging."""

    @patch("src.middleware.http_logging.random")
    @patch("src.middleware.http_logging.settings")
    @patch("src.middleware.http_logging.clear_context")
    @patch("src.middleware.http_logging.bind_request_context", return_value="req-exc")
    @patch("src.middleware.http_logging.logger")
    def test_exception_logged_and_reraised(
        self, mock_logger, _bind, mock_clear, mock_settings, mock_random
    ):
        from src.middleware.http_logging import HTTPLoggingMiddleware

        mock_settings.log_exclude_paths_list = []
        mock_settings.LOG_ACCESS_SAMPLE_RATE = 1.0
        mock_settings.LOG_DEBUG_HTTP_REQUESTS = False
        mock_random.random.return_value = 0.1

        mw = HTTPLoggingMiddleware(_make_failing_app(ValueError("boom")))

        with pytest.raises(ValueError, match="boom"):
            asyncio.get_event_loop().run_until_complete(
                mw(_make_scope(), AsyncMock(), AsyncMock())
            )

        mock_logger.error.assert_called()
        mock_clear.assert_called()


class TestHTTPLoggingMiddlewareDebugMode:
    """Debug logging mode."""

    @patch("src.middleware.http_logging.random")
    @patch("src.middleware.http_logging.settings")
    @patch("src.middleware.http_logging.clear_context")
    @patch("src.middleware.http_logging.bind_request_context", return_value="req-dbg")
    @patch("src.middleware.http_logging.logger")
    def test_debug_mode_logs_request_start_as_debug(
        self, mock_logger, _bind, _clear, mock_settings, mock_random
    ):
        from src.middleware.http_logging import HTTPLoggingMiddleware

        mock_settings.log_exclude_paths_list = []
        mock_settings.LOG_ACCESS_SAMPLE_RATE = 1.0
        mock_settings.LOG_DEBUG_HTTP_REQUESTS = True
        mock_settings.LOG_DEBUG_HTTP_RESPONSES = True
        mock_settings.LOG_SLOW_REQUEST_THRESHOLD_MS = 99999
        mock_random.random.return_value = 0.1

        mw = HTTPLoggingMiddleware(_make_responding_app())
        asyncio.get_event_loop().run_until_complete(_invoke(mw, _make_scope()))

        mock_logger.debug.assert_called()
