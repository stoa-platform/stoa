"""Tests for PrometheusClient helper methods (CAB-1291)"""
from unittest.mock import patch

import pytest

from src.services.prometheus_client import PrometheusClient


@pytest.fixture
def client():
    with patch.dict("os.environ", {}, clear=True):
        with patch("src.services.prometheus_client.settings") as mock_settings:
            mock_settings.PROMETHEUS_INTERNAL_URL = "http://prom:9090"
            mock_settings.PROMETHEUS_TIMEOUT_SECONDS = 10
            mock_settings.PROMETHEUS_ENABLED = True
            return PrometheusClient()


@pytest.fixture
def disabled_client():
    with patch.dict("os.environ", {}, clear=True):
        with patch("src.services.prometheus_client.settings") as mock_settings:
            mock_settings.PROMETHEUS_INTERNAL_URL = "http://prom:9090"
            mock_settings.PROMETHEUS_TIMEOUT_SECONDS = 10
            mock_settings.PROMETHEUS_ENABLED = False
            return PrometheusClient()


class TestInit:
    def test_enabled(self, client):
        assert client.is_enabled is True
        assert client._base_url == "http://prom:9090"

    def test_disabled(self, disabled_client):
        assert disabled_client.is_enabled is False


class TestBuildLabels:
    def test_empty(self, client):
        assert client._build_labels() == ""

    def test_subscription_only(self, client):
        result = client._build_labels(subscription_id="sub-1")
        assert result == 'subscription_id="sub-1"'

    def test_all_labels(self, client):
        result = client._build_labels(subscription_id="s", user_id="u", tenant_id="t")
        assert 'subscription_id="s"' in result
        assert 'user_id="u"' in result
        assert 'tenant_id="t"' in result
        assert result.count(",") == 2

    def test_user_and_tenant(self, client):
        result = client._build_labels(user_id="u", tenant_id="t")
        assert 'user_id="u"' in result
        assert 'tenant_id="t"' in result


class TestExtractScalar:
    def test_none_result(self, client):
        assert client._extract_scalar(None) == 0

    def test_empty_vector(self, client):
        result = {"resultType": "vector", "result": []}
        assert client._extract_scalar(result) == 0

    def test_valid_vector(self, client):
        result = {"resultType": "vector", "result": [{"value": [1234567890, "42.7"]}]}
        assert client._extract_scalar(result) == 42

    def test_nan_value(self, client):
        result = {"resultType": "vector", "result": [{"value": [0, "NaN"]}]}
        assert client._extract_scalar(result) == 0

    def test_inf_value(self, client):
        result = {"resultType": "vector", "result": [{"value": [0, "Inf"]}]}
        assert client._extract_scalar(result) == 0

    def test_custom_default(self, client):
        assert client._extract_scalar(None, default=99) == 99

    def test_non_vector_type(self, client):
        result = {"resultType": "matrix", "result": []}
        assert client._extract_scalar(result) == 0


class TestExtractScalarFloat:
    def test_none_result(self, client):
        assert client._extract_scalar_float(None) == 0.0

    def test_valid_vector(self, client):
        result = {"resultType": "vector", "result": [{"value": [0, "95.5"]}]}
        assert client._extract_scalar_float(result) == 95.5

    def test_nan(self, client):
        result = {"resultType": "vector", "result": [{"value": [0, "NaN"]}]}
        assert client._extract_scalar_float(result) == 0.0

    def test_custom_default(self, client):
        assert client._extract_scalar_float(None, default=100.0) == 100.0


class TestExtractToolStats:
    def test_none_result(self, client):
        assert client._extract_tool_stats(None) == []

    def test_valid_tools(self, client):
        result = {
            "result": [
                {"metric": {"tool_id": "t1", "tool_name": "Tool 1"}, "value": [0, "15"]},
                {"metric": {"tool_id": "t2", "tool_name": "Tool 2"}, "value": [0, "8"]},
            ]
        }
        tools = client._extract_tool_stats(result)
        assert len(tools) == 2
        assert tools[0]["tool_id"] == "t1"
        assert tools[0]["call_count"] == 15

    def test_nan_value(self, client):
        result = {
            "result": [{"metric": {"tool_id": "t1"}, "value": [0, "NaN"]}]
        }
        tools = client._extract_tool_stats(result)
        assert tools[0]["call_count"] == 0

    def test_missing_metric_fields(self, client):
        result = {"result": [{"metric": {}, "value": [0, "5"]}]}
        tools = client._extract_tool_stats(result)
        assert tools[0]["tool_id"] == "unknown"
        assert tools[0]["tool_name"] == "Unknown Tool"


class TestExtractDailyStats:
    def test_none_result(self, client):
        assert client._extract_daily_stats(None) == []

    def test_valid_daily(self, client):
        result = {
            "result": [{
                "values": [
                    [1708041600, "10"],  # 2024-02-16
                    [1708128000, "20"],  # 2024-02-17
                ]
            }]
        }
        daily = client._extract_daily_stats(result)
        assert len(daily) == 2
        assert daily[0]["calls"] == 10
        assert daily[1]["calls"] == 20

    def test_nan_daily_value(self, client):
        result = {"result": [{"values": [[1708041600, "NaN"]]}]}
        daily = client._extract_daily_stats(result)
        assert daily[0]["calls"] == 0


class TestDisabledClient:
    async def test_query_returns_none(self, disabled_client):
        result = await disabled_client.query("up")
        assert result is None

    async def test_query_range_returns_none(self, disabled_client):
        from datetime import datetime
        result = await disabled_client.query_range("up", datetime(2026, 1, 1), datetime(2026, 1, 2))
        assert result is None
