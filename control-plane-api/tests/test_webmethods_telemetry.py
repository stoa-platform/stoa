"""Tests for webMethods telemetry adapter (CAB-1683)."""

from datetime import UTC, datetime, timedelta

import pytest

from src.adapters.webmethods.telemetry import WebMethodsTelemetryAdapter, _normalize_wm_event


class TestWebMethodsTelemetryAdapter:
    @pytest.mark.asyncio
    async def test_get_access_logs_success(self, httpx_mock):
        adapter = WebMethodsTelemetryAdapter({"base_url": "http://wm:5555", "auth_config": {"username": "u", "password": "p"}})
        httpx_mock.add_response(
            json={
                "transactionalEvents": [
                    {
                        "creationDate": "2026-03-05T10:00:00",
                        "httpMethod": "POST",
                        "apiName": "/api/orders",
                        "responseCode": 200,
                        "totalTime": 42,
                        "tenantId": "acme",
                        "correlationID": "corr-1",
                    }
                ]
            },
        )
        logs = await adapter.get_access_logs(since=datetime.now(UTC) - timedelta(minutes=5))
        assert len(logs) == 1
        assert logs[0]["gateway_type"] == "webmethods"
        assert logs[0]["method"] == "POST"
        assert logs[0]["status"] == 200
        assert logs[0]["latency_ms"] == 42

    @pytest.mark.asyncio
    async def test_get_access_logs_empty(self, httpx_mock):
        adapter = WebMethodsTelemetryAdapter({"base_url": "http://wm:5555", "auth_config": {"username": "u", "password": "p"}})
        httpx_mock.add_response(json={"transactionalEvents": []})
        logs = await adapter.get_access_logs(since=datetime.now(UTC) - timedelta(minutes=5))
        assert logs == []

    @pytest.mark.asyncio
    async def test_get_access_logs_http_error(self, httpx_mock):
        adapter = WebMethodsTelemetryAdapter({"base_url": "http://wm:5555", "auth_config": {"username": "u", "password": "p"}})
        httpx_mock.add_response(status_code=401)
        logs = await adapter.get_access_logs(since=datetime.now(UTC) - timedelta(minutes=5))
        assert logs == []

    @pytest.mark.asyncio
    async def test_get_metrics_snapshot_success(self, httpx_mock):
        adapter = WebMethodsTelemetryAdapter({"base_url": "http://wm:5555", "auth_config": {"username": "u", "password": "p"}})
        httpx_mock.add_response(
            json={"status": "ok", "uptime": 3600},
        )
        metrics = await adapter.get_metrics_snapshot()
        assert metrics["status"] == "ok"

    @pytest.mark.asyncio
    async def test_get_metrics_snapshot_error(self, httpx_mock):
        adapter = WebMethodsTelemetryAdapter({"base_url": "http://wm:5555", "auth_config": {"username": "u", "password": "p"}})
        httpx_mock.add_response(status_code=500)
        metrics = await adapter.get_metrics_snapshot()
        assert "error" in metrics

    @pytest.mark.asyncio
    async def test_setup_push_subscription_success(self, httpx_mock):
        adapter = WebMethodsTelemetryAdapter({"base_url": "http://wm:5555", "auth_config": {"username": "u", "password": "p"}})
        httpx_mock.add_response(
            json={"id": "sub-123"},
            status_code=201,
        )
        result = await adapter.setup_push_subscription("https://api.example.com/ingest")
        assert result.success is True
        assert result.data["subscription_id"] == "sub-123"
        assert result.data["webhook_url"] == "https://api.example.com/ingest"

    @pytest.mark.asyncio
    async def test_setup_push_subscription_failure(self, httpx_mock):
        adapter = WebMethodsTelemetryAdapter({"base_url": "http://wm:5555", "auth_config": {"username": "u", "password": "p"}})
        httpx_mock.add_response(status_code=403)
        result = await adapter.setup_push_subscription("https://api.example.com/ingest")
        assert result.success is False
        assert "403" in result.error

    @pytest.mark.asyncio
    async def test_missing_auth_raises(self):
        with pytest.raises(ValueError, match="auth_config"):
            WebMethodsTelemetryAdapter()
        with pytest.raises(ValueError, match="auth_config"):
            WebMethodsTelemetryAdapter({"base_url": "http://wm:5555"})

    @pytest.mark.asyncio
    async def test_custom_auth(self):
        adapter = WebMethodsTelemetryAdapter({"auth_config": {"username": "admin", "password": "secret"}})
        assert adapter._username == "admin"
        assert adapter._password == "secret"


class TestNormalizeWmEvent:
    def test_normalize_full_event(self):
        result = _normalize_wm_event(
            {
                "creationDate": "2026-03-05T10:00:00",
                "httpMethod": "PUT",
                "apiName": "/api/inventory",
                "responseCode": 204,
                "totalTime": 18,
                "tenantId": "acme",
                "correlationID": "corr-42",
            }
        )
        assert result["gateway_type"] == "webmethods"
        assert result["method"] == "PUT"
        assert result["path"] == "/api/inventory"
        assert result["status"] == 204
        assert result["latency_ms"] == 18
        assert result["request_id"] == "corr-42"

    def test_normalize_alternative_keys(self):
        result = _normalize_wm_event(
            {
                "eventTimestamp": "2026-03-05",
                "operationName": "getUsers",
                "nativeEndpoint": "/users",
                "statusCode": 500,
                "providerTime": 200,
            }
        )
        assert result["method"] == "getUsers"
        assert result["status"] == 500
        assert result["latency_ms"] == 200

    def test_normalize_minimal(self):
        result = _normalize_wm_event({})
        assert result["gateway_type"] == "webmethods"
        assert result["method"] == "UNKNOWN"
        assert result["tenant_id"] == "platform"
