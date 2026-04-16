"""Tests for Gravitee telemetry adapter (CAB-1683)."""

from datetime import UTC, datetime, timedelta

import pytest

from src.adapters.gravitee.telemetry import GraviteeTelemetryAdapter, _normalize_gravitee_log


class TestGraviteeTelemetryAdapter:
    @pytest.mark.asyncio
    async def test_get_access_logs_success(self, httpx_mock):
        adapter = GraviteeTelemetryAdapter({"base_url": "http://gravitee:8083", "auth_config": {"username": "u", "password": "p"}})
        httpx_mock.add_response(
            json={
                "logs": [
                    {
                        "timestamp": 1709636400000,
                        "method": "GET",
                        "path": "/api/test",
                        "status": 200,
                        "response-time": 35,
                        "tenant": "acme",
                        "requestId": "req-1",
                    }
                ]
            },
        )
        logs = await adapter.get_access_logs(since=datetime.now(UTC) - timedelta(minutes=5))
        assert len(logs) == 1
        assert logs[0]["gateway_type"] == "gravitee"
        assert logs[0]["method"] == "GET"
        assert logs[0]["status"] == 200

    @pytest.mark.asyncio
    async def test_get_access_logs_empty(self, httpx_mock):
        adapter = GraviteeTelemetryAdapter({"base_url": "http://gravitee:8083", "auth_config": {"username": "u", "password": "p"}})
        httpx_mock.add_response(json={"logs": []})
        logs = await adapter.get_access_logs(since=datetime.now(UTC) - timedelta(minutes=5))
        assert logs == []

    @pytest.mark.asyncio
    async def test_get_access_logs_http_error(self, httpx_mock):
        adapter = GraviteeTelemetryAdapter({"base_url": "http://gravitee:8083", "auth_config": {"username": "u", "password": "p"}})
        httpx_mock.add_response(status_code=500)
        logs = await adapter.get_access_logs(since=datetime.now(UTC) - timedelta(minutes=5))
        assert logs == []

    @pytest.mark.asyncio
    async def test_get_metrics_snapshot_success(self, httpx_mock):
        adapter = GraviteeTelemetryAdapter({"base_url": "http://gravitee:8083", "auth_config": {"username": "u", "password": "p"}})
        httpx_mock.add_response(json={"count": 42, "hits": {"total": 100}})
        metrics = await adapter.get_metrics_snapshot()
        assert metrics["count"] == 42

    @pytest.mark.asyncio
    async def test_get_metrics_snapshot_error(self, httpx_mock):
        adapter = GraviteeTelemetryAdapter({"base_url": "http://gravitee:8083", "auth_config": {"username": "u", "password": "p"}})
        httpx_mock.add_response(status_code=403)
        metrics = await adapter.get_metrics_snapshot()
        assert "error" in metrics

    @pytest.mark.asyncio
    async def test_setup_push_not_supported(self):
        adapter = GraviteeTelemetryAdapter({"auth_config": {"username": "u", "password": "p"}})
        result = await adapter.setup_push_subscription("https://example.com/ingest")
        assert result.success is False
        assert "TCP Reporter" in result.error

    @pytest.mark.asyncio
    async def test_auth_headers(self):
        adapter = GraviteeTelemetryAdapter({"auth_config": {"username": "admin", "password": "secret"}})
        headers = adapter._auth_headers()
        assert headers["Authorization"].startswith("Basic ")

    @pytest.mark.asyncio
    async def test_missing_auth_raises(self):
        with pytest.raises(ValueError, match="auth_config"):
            GraviteeTelemetryAdapter()
        with pytest.raises(ValueError, match="auth_config"):
            GraviteeTelemetryAdapter({"base_url": "http://gravitee:8083"})


class TestNormalizeGraviteeLog:
    def test_normalize_with_timestamp_ms(self):
        result = _normalize_gravitee_log(
            {
                "timestamp": 1709636400000,
                "method": "POST",
                "path": "/api/v1/users",
                "status": 201,
                "response-time": 55,
                "tenant": "acme",
                "requestId": "req-42",
            }
        )
        assert result["gateway_type"] == "gravitee"
        assert result["method"] == "POST"
        assert result["status"] == 201
        assert result["latency_ms"] == 55
        assert result["tenant_id"] == "acme"

    def test_normalize_with_alternative_keys(self):
        result = _normalize_gravitee_log(
            {
                "@timestamp": "2026-03-05T10:00:00",
                "http-method": "GET",
                "uri": "/test",
                "response-status": 404,
                "responseTime": 12,
            }
        )
        assert result["method"] == "GET"
        assert result["path"] == "/test"
        assert result["status"] == 404

    def test_normalize_minimal(self):
        result = _normalize_gravitee_log({})
        assert result["gateway_type"] == "gravitee"
        assert result["method"] == "UNKNOWN"
        assert result["tenant_id"] == "platform"
