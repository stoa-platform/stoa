"""
Spec tests for CAB-2004: Admin Logs via Loki

Generated from SPEC.md acceptance criteria.
All tests MUST FAIL until implementation is complete.

Endpoint: GET /v1/admin/logs
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


SAMPLE_ADMIN_LOGS = [
    {
        "timestamp": datetime(2026, 4, 7, 12, 0, 0),
        "service": "stoa-gateway",
        "level": "info",
        "message": "request completed",
        "trace_id": "abc123",
        "tenant_id": "acme",
        "request_id": "req-001",
        "duration_ms": 42.5,
        "path": "/mcp/tools/list",
        "method": "GET",
        "status_code": 200,
        "consumer_id": "consumer-789",
    },
    {
        "timestamp": datetime(2026, 4, 7, 12, 1, 0),
        "service": "control-plane-api",
        "level": "error",
        "message": "auth failed for user@example.com",
        "trace_id": "def456",
        "tenant_id": "acme",
        "request_id": "req-002",
        "duration_ms": 5.0,
        "path": "/v1/apis",
        "method": "POST",
        "status_code": 401,
        "consumer_id": None,
    },
]


class TestAdminLogsEndpoint:
    """AC1: GET /v1/admin/logs returns structured log entries from Loki."""

    def test_ac1_returns_structured_logs(self, app_with_cpi_admin):
        """AC1: Endpoint returns structured log entries with correct schema."""
        with patch("src.routers.admin_logs.loki_client") as mock_loki:
            mock_loki.query_range = AsyncMock(return_value=SAMPLE_ADMIN_LOGS)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/logs")

            assert response.status_code == 200
            data = response.json()
            assert "logs" in data
            assert "total" in data
            assert "limit" in data
            assert "has_more" in data
            assert "query_time_ms" in data
            assert len(data["logs"]) == 2

            entry = data["logs"][0]
            assert "timestamp" in entry
            assert "service" in entry
            assert "level" in entry
            assert "message" in entry
            assert "trace_id" in entry
            assert "duration_ms" in entry
            assert "path" in entry
            assert "method" in entry
            assert "status_code" in entry


class TestAdminLogsRBAC:
    """AC2 + AC3: RBAC enforcement."""

    def test_ac2_cpi_admin_sees_all_tenants(self, app_with_cpi_admin):
        """AC2: cpi-admin sees logs from all tenants (no tenant_id filter in LogQL)."""
        with patch("src.routers.admin_logs.loki_client") as mock_loki:
            mock_loki.query_range = AsyncMock(return_value=SAMPLE_ADMIN_LOGS)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/logs")

            assert response.status_code == 200
            # cpi-admin should NOT have tenant_id filter applied
            call_args = mock_loki.query_range.call_args
            logql = call_args.kwargs.get("logql") or call_args.args[0]
            assert "tenant_id" not in logql

    def test_ac2_tenant_admin_sees_own_tenant_only(self, app_with_tenant_admin):
        """AC2: tenant-admin sees only own tenant logs (tenant_id scoped in LogQL)."""
        with patch("src.routers.admin_logs.loki_client") as mock_loki:
            mock_loki.query_range = AsyncMock(return_value=[SAMPLE_ADMIN_LOGS[0]])

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/admin/logs")

            assert response.status_code == 200
            # tenant-admin should have tenant_id="acme" in LogQL
            call_args = mock_loki.query_range.call_args
            logql = call_args.kwargs.get("logql") or call_args.args[0]
            assert "acme" in logql

    def test_ac3_viewer_gets_403(self, app_with_viewer):
        """AC3: viewer role receives 403."""
        with TestClient(app_with_viewer) as client:
            response = client.get("/v1/admin/logs")

        assert response.status_code == 403

    def test_ac3_unauthenticated_gets_401(self, client):
        """AC3: No token returns 401."""
        response = client.get("/v1/admin/logs")
        assert response.status_code in (401, 403)


class TestAdminLogsPIIMasking:
    """AC4: PII masking applied to all log entries."""

    def test_ac4_pii_masked_in_messages(self, app_with_cpi_admin):
        """AC4: Email and phone in log messages are masked."""
        logs_with_pii = [
            {
                **SAMPLE_ADMIN_LOGS[1],
                "message": "auth failed for john@example.com phone +33612345678",
            },
        ]

        with patch("src.routers.admin_logs.loki_client") as mock_loki:
            mock_loki.query_range = AsyncMock(return_value=logs_with_pii)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/logs")

            assert response.status_code == 200
            entry = response.json()["logs"][0]
            assert "john@example.com" not in entry["message"]
            assert "+33612345678" not in entry["message"]


class TestAdminLogsFilters:
    """AC5-AC8: Filtering capabilities."""

    def test_ac5_service_filter_gateway(self, app_with_cpi_admin):
        """AC5: service=gateway restricts to stoa-gateway logs."""
        with patch("src.routers.admin_logs.loki_client") as mock_loki:
            mock_loki.query_range = AsyncMock(return_value=[SAMPLE_ADMIN_LOGS[0]])

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/logs", params={"service": "gateway"})

            assert response.status_code == 200
            call_args = mock_loki.query_range.call_args
            logql = call_args.kwargs.get("logql") or call_args.args[0]
            assert "stoa-gateway" in logql

    def test_ac5_service_filter_all(self, app_with_cpi_admin):
        """AC5: service=all includes all services."""
        with patch("src.routers.admin_logs.loki_client") as mock_loki:
            mock_loki.query_range = AsyncMock(return_value=SAMPLE_ADMIN_LOGS)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/logs", params={"service": "all"})

            assert response.status_code == 200
            call_args = mock_loki.query_range.call_args
            logql = call_args.kwargs.get("logql") or call_args.args[0]
            # Should use regex for all services
            assert "stoa-gateway" in logql or "job=~" in logql

    def test_ac6_level_filter(self, app_with_cpi_admin):
        """AC6: level=error restricts to error-level logs."""
        with patch("src.routers.admin_logs.loki_client") as mock_loki:
            mock_loki.query_range = AsyncMock(return_value=[SAMPLE_ADMIN_LOGS[1]])

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/logs", params={"level": "error"})

            assert response.status_code == 200
            call_args = mock_loki.query_range.call_args
            logql = call_args.kwargs.get("logql") or call_args.args[0]
            assert "error" in logql

    def test_ac7_search_filter(self, app_with_cpi_admin):
        """AC7: search param applies free-text filter."""
        with patch("src.routers.admin_logs.loki_client") as mock_loki:
            mock_loki.query_range = AsyncMock(return_value=[SAMPLE_ADMIN_LOGS[0]])

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/logs", params={"search": "tools/list"})

            assert response.status_code == 200
            call_args = mock_loki.query_range.call_args
            logql = call_args.kwargs.get("logql") or call_args.args[0]
            assert "tools/list" in logql

    def test_ac8_time_range_defaults_to_1h(self, app_with_cpi_admin):
        """AC8: No time range params defaults to last 1 hour."""
        with patch("src.routers.admin_logs.loki_client") as mock_loki:
            mock_loki.query_range = AsyncMock(return_value=[])

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/logs")

            assert response.status_code == 200
            call_args = mock_loki.query_range.call_args
            start = call_args.kwargs.get("start")
            end = call_args.kwargs.get("end")
            assert start is not None
            assert end is not None
            assert (end - start) <= timedelta(hours=1, seconds=5)

    def test_ac8_rejects_time_range_over_24h(self, app_with_cpi_admin):
        """AC8: Time range > 24h returns 400."""
        now = datetime.now(timezone.utc)
        start = (now - timedelta(hours=48)).isoformat()
        end = now.isoformat()

        with TestClient(app_with_cpi_admin) as client:
            response = client.get(
                "/v1/admin/logs",
                params={"start_time": start, "end_time": end},
            )

        assert response.status_code == 400
        assert "24 hours" in response.json()["detail"].lower()


class TestAdminLogsEdgeCases:
    """Edge cases from spec."""

    def test_edge_loki_unavailable_returns_503(self, app_with_cpi_admin):
        """Loki unreachable returns 503."""
        with patch("src.routers.admin_logs.loki_client") as mock_loki:
            mock_loki.query_range = AsyncMock(return_value=None)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/logs")

            assert response.status_code == 503
            assert "loki" in response.json()["detail"].lower()

    def test_edge_empty_results(self, app_with_cpi_admin):
        """Empty results return proper empty response."""
        with patch("src.routers.admin_logs.loki_client") as mock_loki:
            mock_loki.query_range = AsyncMock(return_value=[])

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/logs")

            assert response.status_code == 200
            data = response.json()
            assert data["logs"] == []
            assert data["total"] == 0

    def test_edge_special_chars_in_search_escaped(self, app_with_cpi_admin):
        """Special characters in search are escaped to prevent LogQL injection."""
        with patch("src.routers.admin_logs.loki_client") as mock_loki:
            mock_loki.query_range = AsyncMock(return_value=[])

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(
                    "/v1/admin/logs", params={"search": 'foo"bar'}
                )

            assert response.status_code == 200
            call_args = mock_loki.query_range.call_args
            logql = call_args.kwargs.get("logql") or call_args.args[0]
            # Raw double-quote should be escaped in LogQL
            assert 'foo"bar' not in logql

    def test_edge_limit_boundary(self, app_with_cpi_admin):
        """limit > 200 is rejected or clamped."""
        with TestClient(app_with_cpi_admin) as client:
            response = client.get("/v1/admin/logs", params={"limit": 500})

        # Either 422 (validation) or 200 with clamped limit
        assert response.status_code in (200, 422)
        if response.status_code == 200:
            assert response.json()["limit"] <= 200
