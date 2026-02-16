"""Tests for PrometheusClient (CAB-1291)"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.services.prometheus_client import PrometheusClient


def _make_client(**overrides):
    """Create PrometheusClient with mocked settings."""
    defaults = {
        "PROMETHEUS_INTERNAL_URL": "http://prometheus:9090",
        "PROMETHEUS_TIMEOUT_SECONDS": 10,
        "PROMETHEUS_ENABLED": True,
    }
    defaults.update(overrides)
    with patch("src.services.prometheus_client.settings") as mock_settings:
        for k, v in defaults.items():
            setattr(mock_settings, k, v)
        return PrometheusClient()


# ── Init + Properties ──


class TestInit:
    def test_defaults(self):
        client = _make_client()
        assert client._base_url == "http://prometheus:9090"
        assert client._timeout == 10.0
        assert client._enabled is True

    def test_disabled(self):
        client = _make_client(PROMETHEUS_ENABLED=False)
        assert client.is_enabled is False

    def test_trailing_slash_stripped(self):
        client = _make_client(PROMETHEUS_INTERNAL_URL="http://prom:9090/")
        assert client._base_url == "http://prom:9090"


# ── Connect ──


class TestConnect:
    async def test_disabled_noop(self):
        client = _make_client(PROMETHEUS_ENABLED=False)
        await client.connect()  # should not raise

    async def test_success(self):
        client = _make_client()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        with patch("src.services.prometheus_client.httpx.AsyncClient", return_value=mock_http):
            await client.connect()

    async def test_unhealthy(self):
        client = _make_client()
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        with patch("src.services.prometheus_client.httpx.AsyncClient", return_value=mock_http):
            await client.connect()  # warns but doesn't raise

    async def test_connection_error(self):
        client = _make_client()
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=Exception("refused"))
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        with patch("src.services.prometheus_client.httpx.AsyncClient", return_value=mock_http):
            await client.connect()  # warns but doesn't raise


# ── Disconnect ──


class TestDisconnect:
    async def test_noop(self):
        client = _make_client()
        await client.disconnect()


# ── query ──


class TestQuery:
    async def test_disabled_returns_none(self):
        client = _make_client(PROMETHEUS_ENABLED=False)
        result = await client.query("up")
        assert result is None

    async def test_success(self):
        client = _make_client()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {"resultType": "vector", "result": []},
        }
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        with patch("src.services.prometheus_client.httpx.AsyncClient", return_value=mock_http):
            result = await client.query("up")
        assert result == {"resultType": "vector", "result": []}

    async def test_non_success_status(self):
        client = _make_client()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"status": "error", "errorType": "bad_data"}
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        with patch("src.services.prometheus_client.httpx.AsyncClient", return_value=mock_http):
            result = await client.query("invalid{")
        assert result is None

    async def test_timeout(self):
        client = _make_client()
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        with patch("src.services.prometheus_client.httpx.AsyncClient", return_value=mock_http):
            result = await client.query("slow_query")
        assert result is None

    async def test_exception(self):
        client = _make_client()
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=Exception("network"))
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        with patch("src.services.prometheus_client.httpx.AsyncClient", return_value=mock_http):
            result = await client.query("up")
        assert result is None


# ── query_range ──


class TestQueryRange:
    async def test_disabled_returns_none(self):
        client = _make_client(PROMETHEUS_ENABLED=False)
        result = await client.query_range("up", datetime(2026, 2, 16), datetime(2026, 2, 17))
        assert result is None

    async def test_success(self):
        client = _make_client()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {"resultType": "matrix", "result": []},
        }
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        with patch("src.services.prometheus_client.httpx.AsyncClient", return_value=mock_http):
            result = await client.query_range("up", datetime(2026, 2, 16), datetime(2026, 2, 17))
        assert result == {"resultType": "matrix", "result": []}

    async def test_non_success(self):
        client = _make_client()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"status": "error"}
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        with patch("src.services.prometheus_client.httpx.AsyncClient", return_value=mock_http):
            result = await client.query_range("up", datetime(2026, 2, 16), datetime(2026, 2, 17))
        assert result is None

    async def test_exception(self):
        client = _make_client()
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=Exception("fail"))
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        with patch("src.services.prometheus_client.httpx.AsyncClient", return_value=mock_http):
            result = await client.query_range("up", datetime(2026, 2, 16), datetime(2026, 2, 17))
        assert result is None


# ── Specific query methods ──


class TestSpecificQueries:
    async def test_get_request_count(self):
        client = _make_client()
        client.query = AsyncMock(return_value={
            "resultType": "vector",
            "result": [{"value": [1708099200, "42"]}],
        })
        count = await client.get_request_count("sub1", "user1", "acme")
        assert count == 42
        client.query.assert_awaited_once()

    async def test_get_request_count_none(self):
        client = _make_client()
        client.query = AsyncMock(return_value=None)
        count = await client.get_request_count()
        assert count == 0

    async def test_get_success_count(self):
        client = _make_client()
        client.query = AsyncMock(return_value={
            "resultType": "vector",
            "result": [{"value": [0, "10"]}],
        })
        count = await client.get_success_count("sub1", "user1", "acme")
        assert count == 10

    async def test_get_success_count_no_labels(self):
        client = _make_client()
        client.query = AsyncMock(return_value=None)
        count = await client.get_success_count()
        assert count == 0

    async def test_get_error_count(self):
        client = _make_client()
        client.query = AsyncMock(return_value={
            "resultType": "vector",
            "result": [{"value": [0, "5"]}],
        })
        count = await client.get_error_count("sub1", "user1", "acme")
        assert count == 5

    async def test_get_error_count_no_labels(self):
        client = _make_client()
        client.query = AsyncMock(return_value=None)
        count = await client.get_error_count()
        assert count == 0

    async def test_get_avg_latency_ms(self):
        client = _make_client()
        client.query = AsyncMock(return_value={
            "resultType": "vector",
            "result": [{"value": [0, "250"]}],
        })
        latency = await client.get_avg_latency_ms("sub1", "user1", "acme")
        assert latency == 250

    async def test_get_avg_latency_nan(self):
        client = _make_client()
        client.query = AsyncMock(return_value={
            "resultType": "vector",
            "result": [{"value": [0, "NaN"]}],
        })
        latency = await client.get_avg_latency_ms()
        assert latency == 0

    async def test_get_top_tools(self):
        client = _make_client()
        client.query = AsyncMock(return_value={
            "resultType": "vector",
            "result": [
                {"metric": {"tool_id": "t1", "tool_name": "Search"}, "value": [0, "100"]},
                {"metric": {"tool_id": "t2", "tool_name": "Calc"}, "value": [0, "50"]},
            ],
        })
        tools = await client.get_top_tools("user1", "acme")
        assert len(tools) == 2
        assert tools[0]["tool_id"] == "t1"
        assert tools[0]["call_count"] == 100

    async def test_get_daily_calls(self):
        client = _make_client()
        client.query_range = AsyncMock(return_value={
            "resultType": "matrix",
            "result": [{
                "values": [
                    [1708099200, "10"],
                    [1708185600, "20"],
                ],
            }],
        })
        daily = await client.get_daily_calls("user1", "acme", days=2)
        assert len(daily) == 2
        assert daily[0]["calls"] == 10

    async def test_get_tool_success_rate(self):
        client = _make_client()
        client.query = AsyncMock(return_value={
            "resultType": "vector",
            "result": [{"value": [0, "95.5"]}],
        })
        rate = await client.get_tool_success_rate("t1", "user1", "acme")
        assert rate == 95.5

    async def test_get_tool_success_rate_nan(self):
        client = _make_client()
        client.query = AsyncMock(return_value={
            "resultType": "vector",
            "result": [{"value": [0, "NaN"]}],
        })
        rate = await client.get_tool_success_rate("t1", "user1", "acme")
        assert rate == 100.0

    async def test_get_tool_avg_latency(self):
        client = _make_client()
        client.query = AsyncMock(return_value={
            "resultType": "vector",
            "result": [{"value": [0, "150"]}],
        })
        latency = await client.get_tool_avg_latency("t1", "user1", "acme")
        assert latency == 150

    async def test_get_tool_avg_latency_nan(self):
        client = _make_client()
        client.query = AsyncMock(return_value={
            "resultType": "vector",
            "result": [{"value": [0, "NaN"]}],
        })
        latency = await client.get_tool_avg_latency("t1", "user1", "acme")
        assert latency == 0


# ── Helper methods ──


class TestBuildLabels:
    def test_empty(self):
        client = _make_client()
        assert client._build_labels() == ""

    def test_subscription_only(self):
        client = _make_client()
        result = client._build_labels(subscription_id="sub1")
        assert 'subscription_id="sub1"' in result

    def test_all_labels(self):
        client = _make_client()
        result = client._build_labels("sub1", "user1", "acme")
        assert "subscription_id" in result
        assert "user_id" in result
        assert "tenant_id" in result


class TestExtractScalar:
    def test_none_result(self):
        client = _make_client()
        assert client._extract_scalar(None) == 0

    def test_vector_result(self):
        client = _make_client()
        result = {"resultType": "vector", "result": [{"value": [0, "42"]}]}
        assert client._extract_scalar(result) == 42

    def test_empty_vector(self):
        client = _make_client()
        result = {"resultType": "vector", "result": []}
        assert client._extract_scalar(result) == 0

    def test_nan_value(self):
        client = _make_client()
        result = {"resultType": "vector", "result": [{"value": [0, "NaN"]}]}
        assert client._extract_scalar(result) == 0

    def test_inf_value(self):
        client = _make_client()
        result = {"resultType": "vector", "result": [{"value": [0, "Infinity"]}]}
        assert client._extract_scalar(result) == 0

    def test_non_vector_type(self):
        client = _make_client()
        result = {"resultType": "scalar", "result": [0, "5"]}
        assert client._extract_scalar(result) == 0

    def test_malformed(self):
        client = _make_client()
        result = {"resultType": "vector", "result": [{"value": "bad"}]}
        assert client._extract_scalar(result) == 0

    def test_custom_default(self):
        client = _make_client()
        assert client._extract_scalar(None, default=99) == 99


class TestExtractScalarFloat:
    def test_none_result(self):
        client = _make_client()
        assert client._extract_scalar_float(None) == 0.0

    def test_vector_result(self):
        client = _make_client()
        result = {"resultType": "vector", "result": [{"value": [0, "95.5"]}]}
        assert client._extract_scalar_float(result) == 95.5

    def test_nan_value(self):
        client = _make_client()
        result = {"resultType": "vector", "result": [{"value": [0, "NaN"]}]}
        assert client._extract_scalar_float(result) == 0.0

    def test_inf_value(self):
        client = _make_client()
        result = {"resultType": "vector", "result": [{"value": [0, "Infinity"]}]}
        assert client._extract_scalar_float(result) == 0.0


class TestExtractToolStats:
    def test_none(self):
        client = _make_client()
        assert client._extract_tool_stats(None) == []

    def test_with_data(self):
        client = _make_client()
        result = {
            "result": [
                {"metric": {"tool_id": "t1", "tool_name": "Search"}, "value": [0, "100"]},
            ]
        }
        tools = client._extract_tool_stats(result)
        assert len(tools) == 1
        assert tools[0]["tool_id"] == "t1"
        assert tools[0]["call_count"] == 100

    def test_nan_value(self):
        client = _make_client()
        result = {
            "result": [
                {"metric": {"tool_id": "t1", "tool_name": "X"}, "value": [0, "NaN"]},
            ]
        }
        tools = client._extract_tool_stats(result)
        assert tools[0]["call_count"] == 0

    def test_missing_metric(self):
        client = _make_client()
        result = {"result": [{"metric": {}, "value": [0, "5"]}]}
        tools = client._extract_tool_stats(result)
        assert tools[0]["tool_id"] == "unknown"


class TestExtractDailyStats:
    def test_none(self):
        client = _make_client()
        assert client._extract_daily_stats(None) == []

    def test_with_data(self):
        client = _make_client()
        result = {
            "result": [{
                "values": [
                    [1708099200, "10"],
                    [1708185600, "NaN"],
                ],
            }]
        }
        daily = client._extract_daily_stats(result)
        assert len(daily) == 2
        assert daily[0]["calls"] == 10
        assert daily[1]["calls"] == 0  # NaN → 0
