"""Regression tests for CAB-2028 — Auth + tenant isolation on /v1/traces/*.

Validates:
- Unauthenticated requests → 401/403
- tenant-admin sees only own tenant's traces
- cpi-admin sees all traces (no tenant filter)
- Demo endpoints restricted to cpi-admin
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

SVC_PATH = "src.routers.traces.TraceService"


def _make_trace(tenant_id: str = "acme", trace_id: str = "trace-001", **overrides):
    """Create a mock trace object."""
    mock = MagicMock()
    defaults = {
        "id": trace_id,
        "trigger_type": "gitlab-push",
        "trigger_source": "gitlab",
        "tenant_id": tenant_id,
        "api_name": "customer-api",
        "environment": "dev",
        "total_duration_ms": 500,
        "error_summary": None,
        "steps": [],
        "git_commit_sha": "abc1234",
        "git_commit_message": "feat: test",
        "git_branch": "main",
        "git_author": "alice",
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)

    mock.status = MagicMock()
    mock.status.value = overrides.get("status_value", "success")

    from datetime import UTC, datetime

    mock.created_at = datetime(2026, 4, 9, tzinfo=UTC)
    mock.completed_at = datetime(2026, 4, 9, tzinfo=UTC)

    mock.to_summary = MagicMock(return_value={
        "id": mock.id, "tenant_id": mock.tenant_id, "status": "success",
    })
    mock.to_dict = MagicMock(return_value={
        "id": mock.id, "tenant_id": mock.tenant_id, "status": "success",
        "trigger_type": mock.trigger_type, "trigger_source": mock.trigger_source,
        "steps": [], "git_commit_sha": None, "git_commit_message": None,
        "git_branch": None, "git_author": None, "git_author_email": None,
        "git_project": None, "git_files_changed": None, "api_id": None,
        "api_name": mock.api_name, "environment": mock.environment,
        "created_at": None, "completed_at": None,
        "total_duration_ms": mock.total_duration_ms, "error_summary": None,
    })
    return mock


# ============ Unauthenticated access → 401/403 ============


class TestTracesNoAuth:
    """Requests without JWT must be rejected."""

    def test_list_traces_no_auth(self, client):
        """GET /v1/traces without token → 401/403."""
        resp = client.get("/v1/traces")
        assert resp.status_code in (401, 403)

    def test_get_trace_stats_no_auth(self, client):
        """GET /v1/traces/stats without token → 401/403."""
        resp = client.get("/v1/traces/stats")
        assert resp.status_code in (401, 403)

    def test_get_live_traces_no_auth(self, client):
        """GET /v1/traces/live without token → 401/403."""
        resp = client.get("/v1/traces/live")
        assert resp.status_code in (401, 403)

    def test_get_trace_detail_no_auth(self, client):
        """GET /v1/traces/{id} without token → 401/403."""
        resp = client.get("/v1/traces/trace-001")
        assert resp.status_code in (401, 403)

    def test_get_trace_timeline_no_auth(self, client):
        """GET /v1/traces/{id}/timeline without token → 401/403."""
        resp = client.get("/v1/traces/trace-001/timeline")
        assert resp.status_code in (401, 403)

    def test_ai_session_stats_no_auth(self, client):
        """GET /v1/traces/stats/ai-sessions without token → 401/403."""
        resp = client.get("/v1/traces/stats/ai-sessions")
        assert resp.status_code in (401, 403)

    def test_export_ai_sessions_no_auth(self, client):
        """GET /v1/traces/export/ai-sessions without token → 401/403."""
        resp = client.get("/v1/traces/export/ai-sessions")
        assert resp.status_code in (401, 403)

    def test_demo_no_auth(self, client):
        """POST /v1/traces/demo without token → 401/403."""
        resp = client.post("/v1/traces/demo")
        assert resp.status_code in (401, 403)


# ============ Tenant isolation ============


class TestTracesTenantIsolation:
    """tenant-admin must only see their own tenant's traces."""

    @patch(SVC_PATH)
    def test_list_traces_filters_by_tenant(self, mock_svc_cls, app_with_tenant_admin):
        """list_traces passes tenant_id from JWT, not query param."""
        mock_svc = AsyncMock()
        mock_svc.list_recent = AsyncMock(return_value=[
            _make_trace(tenant_id="acme"),
        ])
        mock_svc_cls.return_value = mock_svc

        client = TestClient(app_with_tenant_admin)
        resp = client.get("/v1/traces")
        assert resp.status_code == 200

        # Service was called with tenant_id="acme" (from JWT, not query param)
        mock_svc.list_recent.assert_called_once()
        call_kwargs = mock_svc.list_recent.call_args
        # tenant_id is the second positional arg (limit=50, tenant_id=...)
        assert call_kwargs[0][1] == "acme" or call_kwargs.kwargs.get("tenant_id") == "acme"

    @patch(SVC_PATH)
    def test_get_trace_cross_tenant_returns_404(self, mock_svc_cls, app_with_tenant_admin):
        """tenant-admin requesting trace from another tenant → 404."""
        other_trace = _make_trace(tenant_id="other-tenant", trace_id="trace-other")
        mock_svc = AsyncMock()
        mock_svc.get = AsyncMock(return_value=other_trace)
        mock_svc_cls.return_value = mock_svc

        client = TestClient(app_with_tenant_admin)
        resp = client.get("/v1/traces/trace-other")
        assert resp.status_code == 404

    @patch(SVC_PATH)
    def test_get_trace_own_tenant_ok(self, mock_svc_cls, app_with_tenant_admin):
        """tenant-admin requesting own tenant's trace → 200."""
        own_trace = _make_trace(tenant_id="acme", trace_id="trace-acme")
        mock_svc = AsyncMock()
        mock_svc.get = AsyncMock(return_value=own_trace)
        mock_svc_cls.return_value = mock_svc

        client = TestClient(app_with_tenant_admin)
        resp = client.get("/v1/traces/trace-acme")
        assert resp.status_code == 200

    @patch(SVC_PATH)
    def test_timeline_cross_tenant_returns_404(self, mock_svc_cls, app_with_tenant_admin):
        """tenant-admin requesting timeline from another tenant → 404."""
        other_trace = _make_trace(tenant_id="other-tenant", trace_id="trace-other")
        mock_svc = AsyncMock()
        mock_svc.get = AsyncMock(return_value=other_trace)
        mock_svc_cls.return_value = mock_svc

        client = TestClient(app_with_tenant_admin)
        resp = client.get("/v1/traces/trace-other/timeline")
        assert resp.status_code == 404

    @patch(SVC_PATH)
    def test_stats_filtered_by_tenant(self, mock_svc_cls, app_with_tenant_admin):
        """get_stats passes tenant_id from JWT."""
        mock_svc = AsyncMock()
        mock_svc.get_stats = AsyncMock(return_value={
            "total": 5, "by_status": {}, "avg_duration_ms": 100, "success_rate": 80.0,
        })
        mock_svc_cls.return_value = mock_svc

        client = TestClient(app_with_tenant_admin)
        resp = client.get("/v1/traces/stats")
        assert resp.status_code == 200
        mock_svc.get_stats.assert_called_once_with(tenant_id="acme")


# ============ cpi-admin sees all ============


class TestTracesCpiAdmin:
    """cpi-admin sees all traces without tenant filtering."""

    @patch(SVC_PATH)
    def test_list_traces_no_tenant_filter(self, mock_svc_cls, app_with_cpi_admin):
        """cpi-admin list_traces passes tenant_id=None (sees all)."""
        mock_svc = AsyncMock()
        mock_svc.list_recent = AsyncMock(return_value=[])
        mock_svc_cls.return_value = mock_svc

        client = TestClient(app_with_cpi_admin)
        resp = client.get("/v1/traces")
        assert resp.status_code == 200

        call_args = mock_svc.list_recent.call_args
        # tenant_id should be None for cpi-admin
        if call_args.args and len(call_args.args) > 1:
            assert call_args.args[1] is None
        else:
            assert call_args.kwargs.get("tenant_id") is None

    @patch(SVC_PATH)
    def test_get_trace_from_any_tenant(self, mock_svc_cls, app_with_cpi_admin):
        """cpi-admin can view trace from any tenant."""
        trace = _make_trace(tenant_id="foreign-tenant")
        mock_svc = AsyncMock()
        mock_svc.get = AsyncMock(return_value=trace)
        mock_svc_cls.return_value = mock_svc

        client = TestClient(app_with_cpi_admin)
        resp = client.get("/v1/traces/trace-001")
        assert resp.status_code == 200


# ============ Demo restricted to cpi-admin ============


class TestDemoRestricted:
    """Demo endpoints restricted to cpi-admin."""

    @patch(SVC_PATH)
    def test_demo_as_tenant_admin_forbidden(self, mock_svc_cls, app_with_tenant_admin):
        """POST /v1/traces/demo as tenant-admin → 403."""
        client = TestClient(app_with_tenant_admin)
        resp = client.post("/v1/traces/demo")
        assert resp.status_code == 403

    @patch(SVC_PATH)
    def test_demo_batch_as_tenant_admin_forbidden(self, mock_svc_cls, app_with_tenant_admin):
        """POST /v1/traces/demo/batch as tenant-admin → 403."""
        client = TestClient(app_with_tenant_admin)
        resp = client.post("/v1/traces/demo/batch")
        assert resp.status_code == 403
