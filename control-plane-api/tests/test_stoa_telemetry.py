"""Tests for STOA Gateway telemetry adapter and registry (CAB-1683)."""

from datetime import UTC, datetime, timedelta

import pytest

from src.adapters.stoa.telemetry import StoaTelemetryAdapter, _parse_prometheus_text
from src.adapters.telemetry_registry import TelemetryAdapterRegistry, register_default_adapters


class TestStoaTelemetryAdapter:
    @pytest.mark.asyncio
    async def test_get_access_logs_returns_empty(self):
        """STOA logs are collected by Fluent-Bit, not pulled."""
        adapter = StoaTelemetryAdapter()
        logs = await adapter.get_access_logs(since=datetime.now(UTC) - timedelta(minutes=5))
        assert logs == []

    @pytest.mark.asyncio
    async def test_get_metrics_snapshot_success(self, httpx_mock):
        adapter = StoaTelemetryAdapter({"base_url": "http://stoa:8080"})
        httpx_mock.add_response(
            url="http://stoa:8080/metrics",
            text="# HELP requests_total\nrequests_total 42\nerrors_total 2\n",
        )
        metrics = await adapter.get_metrics_snapshot()
        assert metrics["requests_total"] == 42.0
        assert metrics["errors_total"] == 2.0

    @pytest.mark.asyncio
    async def test_get_metrics_snapshot_error(self, httpx_mock):
        adapter = StoaTelemetryAdapter({"base_url": "http://stoa:8080"})
        httpx_mock.add_response(url="http://stoa:8080/metrics", status_code=500)
        metrics = await adapter.get_metrics_snapshot()
        assert "error" in metrics

    @pytest.mark.asyncio
    async def test_setup_push_subscription_noop(self):
        adapter = StoaTelemetryAdapter()
        result = await adapter.setup_push_subscription("https://example.com/ingest")
        assert result.success is True
        assert "OTLP" in result.data["message"]


class TestParsePrometheusText:
    def test_parse_counters(self):
        text = "# HELP foo\n# TYPE foo counter\nfoo 123\nbar 456.7\n"
        result = _parse_prometheus_text(text)
        assert result["foo"] == 123.0
        assert result["bar"] == 456.7

    def test_parse_empty(self):
        assert _parse_prometheus_text("") == {}

    def test_parse_comments_only(self):
        assert _parse_prometheus_text("# HELP\n# TYPE\n") == {}

    def test_parse_invalid_value(self):
        result = _parse_prometheus_text("metric_name not_a_number\n")
        assert "metric_name" not in result


class TestTelemetryAdapterRegistry:
    def test_register_default_adapters(self):
        # Clear any existing registrations
        TelemetryAdapterRegistry._adapters = {}
        register_default_adapters()

        assert TelemetryAdapterRegistry.has_type("stoa")
        assert TelemetryAdapterRegistry.has_type("kong")
        assert TelemetryAdapterRegistry.has_type("gravitee")
        assert TelemetryAdapterRegistry.has_type("webmethods")
        assert len(TelemetryAdapterRegistry.list_types()) == 4

    def test_create_adapter(self):
        TelemetryAdapterRegistry._adapters = {}
        register_default_adapters()

        adapter = TelemetryAdapterRegistry.create("kong", {"base_url": "http://kong:8001"})
        from src.adapters.kong.telemetry import KongTelemetryAdapter

        assert isinstance(adapter, KongTelemetryAdapter)

    def test_create_unknown_raises(self):
        TelemetryAdapterRegistry._adapters = {}
        register_default_adapters()

        with pytest.raises(ValueError, match="No telemetry adapter for 'unknown'"):
            TelemetryAdapterRegistry.create("unknown")
