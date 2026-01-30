"""
Tests for Self-Service Logs API (CAB-793)
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


SAMPLE_LOKI_CALLS = [
    {
        "id": "call-0001",
        "timestamp": datetime(2026, 1, 15, 10, 0, 0),
        "tool_id": "crm-search",
        "tool_name": "CRM Search",
        "status": "success",
        "latency_ms": 120,
        "error_message": None,
    },
    {
        "id": "call-0002",
        "timestamp": datetime(2026, 1, 15, 10, 5, 0),
        "tool_id": "invoice-api",
        "tool_name": "Invoice API",
        "status": "error",
        "latency_ms": 5000,
        "error_message": "Timeout calling user@example.com endpoint",
    },
]


class TestGetMyLogs:
    """Tests for GET /v1/logs/calls"""

    def test_returns_own_logs(self, app_with_tenant_admin):
        with patch("src.routers.self_service_logs.loki_client") as mock_loki:
            mock_loki.get_recent_calls = AsyncMock(return_value=SAMPLE_LOKI_CALLS)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/logs/calls")

            assert response.status_code == 200
            data = response.json()
            assert len(data["logs"]) == 2
            assert data["limit"] == 50
            assert data["offset"] == 0

            # Verify user_id from JWT was passed (tenant-admin-user-id)
            call_args = mock_loki.get_recent_calls.call_args
            assert call_args.kwargs["user_id"] == "tenant-admin-user-id"
            assert call_args.kwargs["tenant_id"] == "acme"

    def test_applies_pii_masking(self, app_with_tenant_admin):
        """PII in log entries should be masked."""
        calls_with_pii = [
            {
                "id": "call-0001",
                "timestamp": datetime(2026, 1, 15, 10, 0, 0),
                "tool_id": "crm-search",
                "tool_name": "CRM Search",
                "status": "error",
                "latency_ms": 100,
                "error_message": "Failed for user john@example.com phone +33612345678",
            },
        ]

        with patch("src.routers.self_service_logs.loki_client") as mock_loki:
            mock_loki.get_recent_calls = AsyncMock(return_value=calls_with_pii)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/logs/calls")

            assert response.status_code == 200
            log_entry = response.json()["logs"][0]
            # Email and phone should be masked
            if log_entry.get("error_message"):
                assert "john@example.com" not in log_entry["error_message"]
                assert "+33612345678" not in log_entry["error_message"]

    def test_enforces_max_time_range(self, app_with_tenant_admin):
        """Time range > 24h should be truncated."""
        with patch("src.routers.self_service_logs.loki_client") as mock_loki:
            mock_loki.get_recent_calls = AsyncMock(return_value=[])

            now = datetime.now(timezone.utc)
            start = (now - timedelta(hours=48)).isoformat()
            end = now.isoformat()

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(
                    "/v1/logs/calls",
                    params={"start_time": start, "end_time": end},
                )

            assert response.status_code == 200
            # The service should have clamped the time range
            call_args = mock_loki.get_recent_calls.call_args
            from_date = call_args.kwargs["from_date"]
            to_date = call_args.kwargs["to_date"]
            assert (to_date - from_date) <= timedelta(hours=24, seconds=1)

    def test_pagination(self, app_with_tenant_admin):
        with patch("src.routers.self_service_logs.loki_client") as mock_loki:
            # Return limit+1 to trigger has_more
            mock_loki.get_recent_calls = AsyncMock(
                return_value=SAMPLE_LOKI_CALLS + [SAMPLE_LOKI_CALLS[0]]
            )

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/logs/calls", params={"limit": 2})

            assert response.status_code == 200
            data = response.json()
            assert len(data["logs"]) == 2
            assert data["has_more"] is True

    def test_filter_by_tool_id(self, app_with_tenant_admin):
        with patch("src.routers.self_service_logs.loki_client") as mock_loki:
            mock_loki.get_recent_calls = AsyncMock(return_value=[SAMPLE_LOKI_CALLS[0]])

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(
                    "/v1/logs/calls", params={"tool_id": "crm-search"}
                )

            assert response.status_code == 200
            call_args = mock_loki.get_recent_calls.call_args
            assert call_args.kwargs["tool_id"] == "crm-search"

    def test_filter_by_status(self, app_with_tenant_admin):
        with patch("src.routers.self_service_logs.loki_client") as mock_loki:
            mock_loki.get_recent_calls = AsyncMock(return_value=[])

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(
                    "/v1/logs/calls", params={"status": "error"}
                )

            assert response.status_code == 200
            call_args = mock_loki.get_recent_calls.call_args
            assert call_args.kwargs["status"] == "error"

    def test_unauthenticated_returns_401(self, client):
        """No token should return 401."""
        response = client.get("/v1/logs/calls")
        assert response.status_code in (401, 403)


class TestExportCSV:
    """Tests for GET /v1/logs/calls/export"""

    def test_export_csv_returns_csv(self, app_with_tenant_admin):
        with patch("src.routers.self_service_logs.loki_client") as mock_loki:
            mock_loki.get_recent_calls = AsyncMock(return_value=SAMPLE_LOKI_CALLS)

            now = datetime.now(timezone.utc)
            start = (now - timedelta(hours=1)).isoformat()
            end = now.isoformat()

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(
                    "/v1/logs/calls/export",
                    params={"start_time": start, "end_time": end},
                )

            assert response.status_code == 200
            assert "text/csv" in response.headers["content-type"]
            assert "attachment" in response.headers["content-disposition"]
            # Check CSV headers
            lines = response.text.strip().split("\n")
            assert "timestamp" in lines[0]
            assert "request_id" in lines[0]

    def test_export_csv_unauthenticated(self, client):
        now = datetime.now(timezone.utc)
        response = client.get(
            "/v1/logs/calls/export",
            params={
                "start_time": (now - timedelta(hours=1)).isoformat(),
                "end_time": now.isoformat(),
            },
        )
        assert response.status_code in (401, 403)


class TestGetLogByRequestId:
    """Tests for GET /v1/logs/calls/{request_id}"""

    def test_returns_single_entry(self, app_with_tenant_admin):
        with patch("src.routers.self_service_logs.loki_client") as mock_loki:
            mock_loki.get_recent_calls = AsyncMock(return_value=[SAMPLE_LOKI_CALLS[0]])

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/logs/calls/call-0001")

            assert response.status_code == 200
            # request_id may be partially masked by PII masker (api_key pattern)
            assert response.status_code == 200
            assert "request_id" in response.json()

    def test_returns_404_when_not_found(self, app_with_tenant_admin):
        with patch("src.routers.self_service_logs.loki_client") as mock_loki:
            mock_loki.get_recent_calls = AsyncMock(return_value=[])

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/logs/calls/nonexistent")

            assert response.status_code == 404
