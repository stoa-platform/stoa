"""Tests for self-service logs router (CAB-793).

Endpoints:
  GET /v1/logs/calls              — list my API call logs
  GET /v1/logs/calls/export       — export logs as CSV
  GET /v1/logs/calls/{request_id} — get single log entry
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from src.schemas.logs import LogEntryResponse, LogQueryResponse

# ── Helpers ──

SVC_MODULE = "src.routers.self_service_logs"

_NOW = datetime(2026, 2, 24, 10, 0, 0, tzinfo=UTC)
_THEN = datetime(2026, 2, 24, 9, 0, 0, tzinfo=UTC)


def _make_log_entry(request_id: str = "req-001") -> LogEntryResponse:
    return LogEntryResponse(
        timestamp=_NOW,
        request_id=request_id,
        tool_id="weather-api",
        tool_name="Weather API",
        level="info",
        status="success",
        status_code=200,
        duration_ms=42.0,
        message="Tool call succeeded",
        request_path="/mcp/tools/call",
        request_method="POST",
    )


def _make_log_query_response(entries: list | None = None) -> LogQueryResponse:
    logs = entries if entries is not None else [_make_log_entry()]
    return LogQueryResponse(
        logs=logs,
        total=len(logs),
        limit=50,
        offset=0,
        has_more=False,
        query_time_ms=5.0,
        time_range_start=_THEN,
        time_range_end=_NOW,
    )


# ── GET /v1/logs/calls ──


class TestGetMyLogs:
    def test_get_logs_returns_200(self, client_as_tenant_admin):
        """GET /v1/logs/calls returns 200 with log entries."""
        mock_response = _make_log_query_response()

        with patch(f"{SVC_MODULE}.ConsumerLogsService.query_logs", new_callable=AsyncMock, return_value=mock_response):
            response = client_as_tenant_admin.get("/v1/logs/calls")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["logs"]) == 1
        assert data["logs"][0]["request_id"] == "req-001"

    def test_get_logs_empty_returns_200(self, client_as_tenant_admin):
        """GET /v1/logs/calls with no results returns 200 with empty list."""
        mock_response = _make_log_query_response(entries=[])

        with patch(f"{SVC_MODULE}.ConsumerLogsService.query_logs", new_callable=AsyncMock, return_value=mock_response):
            response = client_as_tenant_admin.get("/v1/logs/calls")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["logs"] == []

    def test_get_logs_with_tool_filter(self, client_as_tenant_admin):
        """GET /v1/logs/calls?tool_id=my-tool forwards tool_id to service."""
        mock_response = _make_log_query_response()

        with patch(
            f"{SVC_MODULE}.ConsumerLogsService.query_logs", new_callable=AsyncMock, return_value=mock_response
        ) as mock_svc:
            client_as_tenant_admin.get("/v1/logs/calls?tool_id=my-tool")

            call_kwargs = mock_svc.call_args.kwargs
            # params.tool_id should be forwarded
            assert call_kwargs["params"].tool_id == "my-tool"

    def test_get_logs_requires_auth(self, client):
        """Unauthenticated request returns 401 or 403."""
        response = client.get("/v1/logs/calls")
        assert response.status_code in (401, 403)

    def test_get_logs_with_pagination(self, client_as_tenant_admin):
        """limit and offset query params forwarded to service."""
        mock_response = _make_log_query_response(entries=[])

        with patch(
            f"{SVC_MODULE}.ConsumerLogsService.query_logs", new_callable=AsyncMock, return_value=mock_response
        ) as mock_svc:
            client_as_tenant_admin.get("/v1/logs/calls?limit=10&offset=5")

            call_kwargs = mock_svc.call_args.kwargs
            assert call_kwargs["params"].limit == 10
            assert call_kwargs["params"].offset == 5

    def test_get_logs_limit_out_of_range_returns_422(self, client_as_tenant_admin):
        """limit > 100 should be rejected with 422."""
        response = client_as_tenant_admin.get("/v1/logs/calls?limit=999")
        assert response.status_code == 422

    def test_get_logs_user_id_from_token_not_request(self, client_as_tenant_admin):
        """user_id must come from the auth token, not request params."""
        mock_response = _make_log_query_response()

        with patch(
            f"{SVC_MODULE}.ConsumerLogsService.query_logs", new_callable=AsyncMock, return_value=mock_response
        ) as mock_svc:
            client_as_tenant_admin.get("/v1/logs/calls")

            call_kwargs = mock_svc.call_args.kwargs
            # user_id must be set (from mock_user_tenant_admin)
            assert call_kwargs["user_id"] == "tenant-admin-user-id"


# ── GET /v1/logs/calls/export ──


class TestExportMyLogs:
    def test_export_returns_csv_content_type(self, client_as_tenant_admin):
        """GET /v1/logs/calls/export returns a streaming CSV response."""
        csv_content = "timestamp,request_id,status\n2026-02-24,req-001,success\n"

        with patch(f"{SVC_MODULE}.ConsumerLogsService.export_csv", new_callable=AsyncMock, return_value=csv_content):
            response = client_as_tenant_admin.get(
                "/v1/logs/calls/export" "?start_time=2026-02-24T09:00:00Z" "&end_time=2026-02-24T10:00:00Z"
            )

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "attachment" in response.headers["content-disposition"]

    def test_export_csv_body_content(self, client_as_tenant_admin):
        """CSV response body contains the expected content."""
        csv_content = "timestamp,request_id,status\n2026-02-24T10:00:00,req-001,success\n"

        with patch(f"{SVC_MODULE}.ConsumerLogsService.export_csv", new_callable=AsyncMock, return_value=csv_content):
            response = client_as_tenant_admin.get(
                "/v1/logs/calls/export" "?start_time=2026-02-24T09:00:00Z" "&end_time=2026-02-24T10:00:00Z"
            )

        assert "req-001" in response.text

    def test_export_missing_start_time_returns_422(self, client_as_tenant_admin):
        """export endpoint requires start_time — missing returns 422."""
        response = client_as_tenant_admin.get("/v1/logs/calls/export?end_time=2026-02-24T10:00:00Z")
        assert response.status_code == 422

    def test_export_missing_end_time_returns_422(self, client_as_tenant_admin):
        """export endpoint requires end_time — missing returns 422."""
        response = client_as_tenant_admin.get("/v1/logs/calls/export?start_time=2026-02-24T09:00:00Z")
        assert response.status_code == 422

    def test_export_filename_includes_user_id(self, client_as_tenant_admin):
        """Content-Disposition filename includes user ID."""
        csv_content = "timestamp,request_id\n"

        with patch(f"{SVC_MODULE}.ConsumerLogsService.export_csv", new_callable=AsyncMock, return_value=csv_content):
            response = client_as_tenant_admin.get(
                "/v1/logs/calls/export" "?start_time=2026-02-24T09:00:00Z" "&end_time=2026-02-24T10:00:00Z"
            )

        cd = response.headers.get("content-disposition", "")
        assert "tenant-admin-user-id" in cd


# ── GET /v1/logs/calls/{request_id} ──


class TestGetLogByRequestId:
    def test_get_existing_log_returns_200(self, client_as_tenant_admin):
        """GET /v1/logs/calls/{request_id} returns 200 when log found."""
        entry = _make_log_entry(request_id="req-abc")
        mock_response = _make_log_query_response(entries=[entry])

        with patch(f"{SVC_MODULE}.ConsumerLogsService.query_logs", new_callable=AsyncMock, return_value=mock_response):
            response = client_as_tenant_admin.get("/v1/logs/calls/req-abc")

        assert response.status_code == 200
        data = response.json()
        assert data["request_id"] == "req-abc"

    def test_get_nonexistent_log_returns_404(self, client_as_tenant_admin):
        """GET /v1/logs/calls/{request_id} returns 404 when log not found."""
        mock_response = _make_log_query_response(entries=[])

        with patch(f"{SVC_MODULE}.ConsumerLogsService.query_logs", new_callable=AsyncMock, return_value=mock_response):
            response = client_as_tenant_admin.get("/v1/logs/calls/req-does-not-exist")

        assert response.status_code == 404
        assert "req-does-not-exist" in response.json()["detail"]

    def test_get_log_passes_request_id_as_search(self, client_as_tenant_admin):
        """request_id is used as search parameter to query_logs."""
        mock_response = _make_log_query_response(entries=[])

        with patch(
            f"{SVC_MODULE}.ConsumerLogsService.query_logs", new_callable=AsyncMock, return_value=mock_response
        ) as mock_svc:
            client_as_tenant_admin.get("/v1/logs/calls/req-xyz")

            call_kwargs = mock_svc.call_args.kwargs
            assert call_kwargs["params"].search == "req-xyz"
            assert call_kwargs["params"].limit == 1
