"""Tests for Traces Router — CAB-1436

Covers: /v1/traces (list, get, stats, live, timeline, demo)
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient


SVC_PATH = "src.routers.traces.TraceService"


def _make_trace(**overrides):
    """Create a mock trace object."""
    mock = MagicMock()
    defaults = {
        "id": str(uuid4()),
        "trigger_type": "gitlab-push",
        "trigger_source": "gitlab",
        "git_commit_sha": "abc1234def",
        "git_commit_message": "feat: add endpoint",
        "git_branch": "main",
        "git_author": "alice",
        "git_author_email": "alice@test.com",
        "tenant_id": "acme",
        "api_name": "weather-api",
        "environment": "dev",
        "total_duration_ms": 450,
        "error_summary": None,
        "steps": [],
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)

    # Mock status as enum-like
    mock.status = MagicMock()
    mock.status.value = overrides.get("status_value", "success")

    # Mock created_at
    from datetime import datetime, timezone
    mock.created_at = datetime(2026, 2, 24, tzinfo=timezone.utc)

    mock.to_summary.return_value = {
        "id": defaults["id"],
        "status": overrides.get("status_value", "success"),
        "trigger_type": defaults["trigger_type"],
        "tenant_id": defaults["tenant_id"],
        "api_name": defaults["api_name"],
        "total_duration_ms": defaults["total_duration_ms"],
    }
    mock.to_dict.return_value = {
        "id": defaults["id"],
        "status": overrides.get("status_value", "success"),
        "steps": defaults["steps"],
    }
    return mock


class TestListTraces:
    """Tests for GET /v1/traces."""

    def test_list_traces_default(self, app_with_cpi_admin, mock_db_session):
        """List traces with default params."""
        trace = _make_trace()
        mock_svc = MagicMock()
        mock_svc.list_recent = AsyncMock(return_value=[trace])

        with patch(SVC_PATH, return_value=mock_svc):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.get("/v1/traces")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["traces"]) == 1

    def test_list_traces_with_filters(self, app_with_cpi_admin, mock_db_session):
        """List traces with tenant and status filters."""
        mock_svc = MagicMock()
        mock_svc.list_recent = AsyncMock(return_value=[])

        with patch(SVC_PATH, return_value=mock_svc):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.get("/v1/traces?tenant_id=acme&status=success&limit=10")

        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_list_traces_invalid_status(self, app_with_cpi_admin, mock_db_session):
        """Invalid status returns 400."""
        mock_svc = MagicMock()

        with patch(SVC_PATH, return_value=mock_svc):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.get("/v1/traces?status=bogus")

        assert resp.status_code == 400


class TestGetTrace:
    """Tests for GET /v1/traces/{trace_id}."""

    def test_get_trace_success(self, app_with_cpi_admin, mock_db_session):
        """Get single trace by ID."""
        trace = _make_trace()
        mock_svc = MagicMock()
        mock_svc.get = AsyncMock(return_value=trace)

        with patch(SVC_PATH, return_value=mock_svc):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.get(f"/v1/traces/{trace.id}")

        assert resp.status_code == 200

    def test_get_trace_404(self, app_with_cpi_admin, mock_db_session):
        """Non-existent trace returns 404."""
        mock_svc = MagicMock()
        mock_svc.get = AsyncMock(return_value=None)

        with patch(SVC_PATH, return_value=mock_svc):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.get("/v1/traces/nonexistent-id")

        assert resp.status_code == 404


class TestTraceStats:
    """Tests for GET /v1/traces/stats."""

    def test_stats_success(self, app_with_cpi_admin, mock_db_session):
        """Get trace statistics."""
        mock_svc = MagicMock()
        mock_svc.get_stats = AsyncMock(
            return_value={"total": 100, "success": 85, "failed": 15}
        )

        with patch(SVC_PATH, return_value=mock_svc):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.get("/v1/traces/stats")

        assert resp.status_code == 200
        assert resp.json()["total"] == 100


class TestLiveTraces:
    """Tests for GET /v1/traces/live."""

    def test_live_traces(self, app_with_cpi_admin, mock_db_session):
        """Get currently running traces."""
        trace = _make_trace(status_value="in_progress")
        mock_svc = MagicMock()
        mock_svc.list_recent = AsyncMock(return_value=[trace])

        with patch(SVC_PATH, return_value=mock_svc):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.get("/v1/traces/live")

        assert resp.status_code == 200
        assert resp.json()["count"] == 1


class TestTraceTimeline:
    """Tests for GET /v1/traces/{trace_id}/timeline."""

    def test_timeline_success(self, app_with_cpi_admin, mock_db_session):
        """Get timeline view of a trace."""
        trace = _make_trace(
            steps=[
                {
                    "name": "webhook_received",
                    "status": "success",
                    "started_at": "2026-02-24T10:00:00",
                    "completed_at": "2026-02-24T10:00:01",
                    "duration_ms": 50,
                    "error": None,
                    "details": {},
                },
            ]
        )
        mock_svc = MagicMock()
        mock_svc.get = AsyncMock(return_value=trace)

        with patch(SVC_PATH, return_value=mock_svc):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.get(f"/v1/traces/{trace.id}/timeline")

        assert resp.status_code == 200
        data = resp.json()
        assert "timeline" in data
        assert len(data["timeline"]) == 1
        assert data["timeline"][0]["name"] == "webhook_received"

    def test_timeline_404(self, app_with_cpi_admin, mock_db_session):
        """Non-existent trace returns 404."""
        mock_svc = MagicMock()
        mock_svc.get = AsyncMock(return_value=None)

        with patch(SVC_PATH, return_value=mock_svc):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.get("/v1/traces/nonexistent/timeline")

        assert resp.status_code == 404


class TestDemoTrace:
    """Tests for POST /v1/traces/demo and /v1/traces/demo/batch."""

    def test_create_demo_trace(self, app_with_cpi_admin, mock_db_session):
        """Create a single demo trace."""
        mock_trace = _make_trace()
        mock_svc = MagicMock()
        mock_svc.create = AsyncMock(return_value=mock_trace)
        mock_svc.add_step = AsyncMock()
        mock_svc.complete = AsyncMock()
        mock_svc.get = AsyncMock(return_value=mock_trace)

        with patch(SVC_PATH, return_value=mock_svc):
            with TestClient(app_with_cpi_admin) as client:
                resp = client.post("/v1/traces/demo")

        assert resp.status_code == 200
        data = resp.json()
        assert data["created"] is True
        assert "trace_id" in data
