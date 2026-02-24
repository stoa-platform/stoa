"""Tests for Prometheus Metrics Middleware — Wave 2

Covers MetricsMiddleware + get_metrics():
- Non-HTTP scope passthrough
- /metrics endpoint skipped (no recursion)
- Path normalization (UUID + numeric ID replacement)
- Request counter incremented
- Duration histogram observed (with and without trace_id exemplar)
- In-progress gauge incremented/decremented
- Status code tracking
- Default status 500 on exception
- get_metrics() returns valid OpenMetrics response
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest


# ── Helpers ────────────────────────────────────────────────────────────


def _make_scope(
    path: str = "/v1/apis",
    method: str = "GET",
    scope_type: str = "http",
) -> dict:
    return {
        "type": scope_type,
        "path": path,
        "method": method,
        "headers": [],
        "client": ("127.0.0.1", 8000),
        "query_string": b"",
    }


def _make_responding_app(*, status: int = 200):
    """Create an ASGI app that sends a complete HTTP response."""

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": status, "headers": []})
        await send({"type": "http.response.body", "body": b"ok", "more_body": False})

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


# ── Path Normalization Tests ───────────────────────────────────────────


class TestPathNormalization:
    """MetricsMiddleware._normalize_path replaces dynamic segments."""

    def test_replaces_uuid(self):
        from src.middleware.metrics import MetricsMiddleware

        mw = MetricsMiddleware(AsyncMock())
        result = mw._normalize_path("/v1/apis/550e8400-e29b-41d4-a716-446655440000")
        assert result == "/v1/apis/{id}"

    def test_replaces_multiple_uuids(self):
        from src.middleware.metrics import MetricsMiddleware

        mw = MetricsMiddleware(AsyncMock())
        result = mw._normalize_path(
            "/v1/tenants/550e8400-e29b-41d4-a716-446655440000"
            "/apis/660e8400-e29b-41d4-a716-446655440001"
        )
        assert result == "/v1/tenants/{id}/apis/{id}"

    def test_replaces_numeric_id(self):
        from src.middleware.metrics import MetricsMiddleware

        mw = MetricsMiddleware(AsyncMock())
        result = mw._normalize_path("/v1/subscriptions/12345")
        assert result == "/v1/subscriptions/{id}"

    def test_preserves_non_dynamic_path(self):
        from src.middleware.metrics import MetricsMiddleware

        mw = MetricsMiddleware(AsyncMock())
        result = mw._normalize_path("/v1/admin/governance/matrix")
        assert result == "/v1/admin/governance/matrix"

    def test_replaces_uuid_case_insensitive(self):
        from src.middleware.metrics import MetricsMiddleware

        mw = MetricsMiddleware(AsyncMock())
        result = mw._normalize_path("/v1/apis/550E8400-E29B-41D4-A716-446655440000")
        assert result == "/v1/apis/{id}"


# ── Middleware Passthrough Tests ───────────────────────────────────────


class TestMetricsMiddlewarePassthrough:
    """Non-HTTP scopes and /metrics path bypass metrics collection."""

    def test_non_http_scope_passes_through(self):
        from src.middleware.metrics import MetricsMiddleware

        inner = AsyncMock()
        mw = MetricsMiddleware(inner)

        asyncio.get_event_loop().run_until_complete(
            mw(_make_scope(scope_type="websocket"), AsyncMock(), AsyncMock())
        )
        inner.assert_called_once()

    def test_metrics_endpoint_skipped(self):
        from src.middleware.metrics import MetricsMiddleware

        inner = AsyncMock()
        mw = MetricsMiddleware(inner)

        asyncio.get_event_loop().run_until_complete(
            mw(_make_scope(path="/metrics"), AsyncMock(), AsyncMock())
        )
        inner.assert_called_once()


# ── Metrics Collection Tests ───────────────────────────────────────────


class TestMetricsCollection:
    """Verify metrics counters, histograms, and gauges are updated."""

    @patch("src.middleware.metrics.get_current_trace_id", return_value=None)
    @patch("src.middleware.metrics.HTTP_REQUESTS_IN_PROGRESS")
    @patch("src.middleware.metrics.HTTP_REQUEST_DURATION_SECONDS")
    @patch("src.middleware.metrics.HTTP_REQUESTS_TOTAL")
    def test_request_counter_incremented(
        self, mock_total, mock_duration, mock_in_progress, _trace
    ):
        from src.middleware.metrics import MetricsMiddleware

        mw = MetricsMiddleware(_make_responding_app(status=201))
        asyncio.get_event_loop().run_until_complete(
            _invoke(mw, _make_scope(method="POST", path="/v1/apis"))
        )

        mock_total.labels.assert_called_with(
            method="POST", endpoint="/v1/apis", status_code="201"
        )
        mock_total.labels().inc.assert_called_once()

    @patch("src.middleware.metrics.get_current_trace_id", return_value=None)
    @patch("src.middleware.metrics.HTTP_REQUESTS_IN_PROGRESS")
    @patch("src.middleware.metrics.HTTP_REQUEST_DURATION_SECONDS")
    @patch("src.middleware.metrics.HTTP_REQUESTS_TOTAL")
    def test_duration_histogram_observed(
        self, _total, mock_duration, _in_progress, _trace
    ):
        from src.middleware.metrics import MetricsMiddleware

        mw = MetricsMiddleware(_make_responding_app())
        asyncio.get_event_loop().run_until_complete(
            _invoke(mw, _make_scope())
        )

        mock_duration.labels.assert_called_with(method="GET", endpoint="/v1/apis")
        mock_duration.labels().observe.assert_called_once()
        duration_arg = mock_duration.labels().observe.call_args[0][0]
        assert duration_arg >= 0

    @patch("src.middleware.metrics.get_current_trace_id", return_value="abc123trace")
    @patch("src.middleware.metrics.HTTP_REQUESTS_IN_PROGRESS")
    @patch("src.middleware.metrics.HTTP_REQUEST_DURATION_SECONDS")
    @patch("src.middleware.metrics.HTTP_REQUESTS_TOTAL")
    def test_trace_id_exemplar_attached(
        self, _total, mock_duration, _in_progress, _trace
    ):
        from src.middleware.metrics import MetricsMiddleware

        mw = MetricsMiddleware(_make_responding_app())
        asyncio.get_event_loop().run_until_complete(
            _invoke(mw, _make_scope())
        )

        call_kwargs = mock_duration.labels().observe.call_args[1]
        assert "exemplar" in call_kwargs
        assert call_kwargs["exemplar"]["trace_id"] == "abc123trace"

    @patch("src.middleware.metrics.get_current_trace_id", return_value=None)
    @patch("src.middleware.metrics.HTTP_REQUESTS_IN_PROGRESS")
    @patch("src.middleware.metrics.HTTP_REQUEST_DURATION_SECONDS")
    @patch("src.middleware.metrics.HTTP_REQUESTS_TOTAL")
    def test_in_progress_gauge_incremented_and_decremented(
        self, _total, _duration, mock_in_progress, _trace
    ):
        from src.middleware.metrics import MetricsMiddleware

        mw = MetricsMiddleware(_make_responding_app())
        asyncio.get_event_loop().run_until_complete(
            _invoke(mw, _make_scope())
        )

        mock_in_progress.labels.assert_called_with(method="GET", endpoint="/v1/apis")
        mock_in_progress.labels().inc.assert_called_once()
        mock_in_progress.labels().dec.assert_called_once()

    @patch("src.middleware.metrics.get_current_trace_id", return_value=None)
    @patch("src.middleware.metrics.HTTP_REQUESTS_IN_PROGRESS")
    @patch("src.middleware.metrics.HTTP_REQUEST_DURATION_SECONDS")
    @patch("src.middleware.metrics.HTTP_REQUESTS_TOTAL")
    def test_status_code_500_default_on_exception(
        self, mock_total, _duration, _in_progress, _trace
    ):
        from src.middleware.metrics import MetricsMiddleware

        async def failing_app(scope, receive, send):
            raise RuntimeError("kaboom")

        mw = MetricsMiddleware(failing_app)

        with pytest.raises(RuntimeError, match="kaboom"):
            asyncio.get_event_loop().run_until_complete(
                mw(_make_scope(), AsyncMock(), AsyncMock())
            )

        mock_total.labels.assert_called_with(
            method="GET", endpoint="/v1/apis", status_code="500"
        )

    @patch("src.middleware.metrics.get_current_trace_id", return_value=None)
    @patch("src.middleware.metrics.HTTP_REQUESTS_IN_PROGRESS")
    @patch("src.middleware.metrics.HTTP_REQUEST_DURATION_SECONDS")
    @patch("src.middleware.metrics.HTTP_REQUESTS_TOTAL")
    def test_path_normalized_in_labels(
        self, mock_total, _duration, _in_progress, _trace
    ):
        from src.middleware.metrics import MetricsMiddleware

        mw = MetricsMiddleware(_make_responding_app())
        scope = _make_scope(path="/v1/apis/550e8400-e29b-41d4-a716-446655440000")
        asyncio.get_event_loop().run_until_complete(_invoke(mw, scope))

        mock_total.labels.assert_called_with(
            method="GET", endpoint="/v1/apis/{id}", status_code="200"
        )


# ── get_metrics() Endpoint Test ────────────────────────────────────────


class TestGetMetricsEndpoint:
    """get_metrics() returns a Starlette Response with OpenMetrics content."""

    def test_get_metrics_returns_response(self):
        from src.middleware.metrics import get_metrics

        response = get_metrics()
        assert response.status_code == 200
        assert "openmetrics" in response.media_type or "text" in response.media_type
        assert len(response.body) > 0
