"""Tests for Kong telemetry adapter (CAB-1683)."""

from datetime import UTC, datetime, timedelta

import pytest

from src.adapters.kong.telemetry import KongTelemetryAdapter, normalize_kong_log


class TestKongTelemetryAdapter:
    @pytest.mark.asyncio
    async def test_get_access_logs_returns_empty(self):
        """Kong DB-less has no log query API."""
        adapter = KongTelemetryAdapter()
        logs = await adapter.get_access_logs(since=datetime.now(UTC) - timedelta(minutes=5))
        assert logs == []

    @pytest.mark.asyncio
    async def test_get_metrics_snapshot_success(self, httpx_mock):
        adapter = KongTelemetryAdapter({"base_url": "http://kong:8001"})
        httpx_mock.add_response(
            url="http://kong:8001/status",
            json={
                "server": {
                    "connections_active": 10,
                    "connections_accepted": 500,
                    "total_requests": 1000,
                },
                "database": {"reachable": False},
            },
        )
        metrics = await adapter.get_metrics_snapshot()
        assert metrics["connections_active"] == 10
        assert metrics["total_requests"] == 1000
        assert metrics["database_reachable"] is False

    @pytest.mark.asyncio
    async def test_get_metrics_snapshot_error(self, httpx_mock):
        adapter = KongTelemetryAdapter({"base_url": "http://kong:8001"})
        httpx_mock.add_response(url="http://kong:8001/status", status_code=500)
        metrics = await adapter.get_metrics_snapshot()
        assert "error" in metrics

    @pytest.mark.asyncio
    async def test_setup_push_subscription_success(self, httpx_mock):
        adapter = KongTelemetryAdapter({"base_url": "http://kong:8001"})
        # Mock GET /plugins
        httpx_mock.add_response(
            url="http://kong:8001/plugins",
            json={"data": []},
        )
        # Mock GET /services
        httpx_mock.add_response(
            url="http://kong:8001/services",
            json={"data": []},
        )
        # Mock POST /config
        httpx_mock.add_response(
            url="http://kong:8001/config",
            json={"message": "ok"},
            status_code=200,
        )
        result = await adapter.setup_push_subscription("https://api.example.com/telemetry/ingest")
        assert result.success is True
        assert result.data["webhook_url"] == "https://api.example.com/telemetry/ingest"

    @pytest.mark.asyncio
    async def test_setup_push_subscription_replaces_existing(self, httpx_mock):
        adapter = KongTelemetryAdapter({"base_url": "http://kong:8001"})
        # Existing http-log plugin with stoa-telemetry tag should be removed
        httpx_mock.add_response(
            url="http://kong:8001/plugins",
            json={
                "data": [
                    {"name": "http-log", "config": {"http_endpoint": "old"}, "tags": ["stoa-telemetry"]},
                    {"name": "rate-limiting", "config": {"minute": 100}, "tags": ["other"]},
                ]
            },
        )
        httpx_mock.add_response(url="http://kong:8001/services", json={"data": []})
        httpx_mock.add_response(url="http://kong:8001/config", json={}, status_code=200)

        result = await adapter.setup_push_subscription("https://new-endpoint.com/ingest")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_setup_push_subscription_config_reload_failure(self, httpx_mock):
        adapter = KongTelemetryAdapter({"base_url": "http://kong:8001"})
        httpx_mock.add_response(url="http://kong:8001/plugins", json={"data": []})
        httpx_mock.add_response(url="http://kong:8001/services", json={"data": []})
        httpx_mock.add_response(url="http://kong:8001/config", status_code=400)

        result = await adapter.setup_push_subscription("https://api.example.com/ingest")
        assert result.success is False
        assert "400" in result.error

    @pytest.mark.asyncio
    async def test_auth_headers_with_api_key(self):
        adapter = KongTelemetryAdapter({"auth_config": {"api_key": "my-token"}})
        headers = adapter._auth_headers()
        assert headers["Kong-Admin-Token"] == "my-token"

    @pytest.mark.asyncio
    async def test_auth_headers_without_api_key(self):
        adapter = KongTelemetryAdapter()
        headers = adapter._auth_headers()
        assert headers == {}


class TestNormalizeKongLog:
    def test_normalize_full_entry(self):
        entry = {
            "started_at": "2026-03-05T10:00:00",
            "request": {"method": "POST", "uri": "/api/users", "headers": {"x-request-id": "abc"}},
            "response": {"status": 201},
            "latencies": {"proxy": 42},
            "service": {"name": "acme-api"},
        }
        result = normalize_kong_log(entry)
        assert result["gateway_type"] == "kong"
        assert result["method"] == "POST"
        assert result["path"] == "/api/users"
        assert result["status"] == 201
        assert result["latency_ms"] == 42
        assert result["tenant_id"] == "acme-api"
        assert result["request_id"] == "abc"

    def test_normalize_minimal_entry(self):
        result = normalize_kong_log({})
        assert result["gateway_type"] == "kong"
        assert result["method"] == "UNKNOWN"
        assert result["status"] == 0
        assert result["tenant_id"] == "platform"
