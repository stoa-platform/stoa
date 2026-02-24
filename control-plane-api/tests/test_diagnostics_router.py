"""Tests for Diagnostics Router — CAB-1436

Covers: /v1/admin/diagnostics (run, connectivity, history)
Router-level tests using actual Pydantic schemas so response_model validation passes.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from src.schemas.diagnostic import ConnectivityResult, DiagnosticListResponse, DiagnosticReport

SVC_PATH = "src.routers.diagnostics.DiagnosticService"


def _mock_report(**overrides):
    defaults = {"tenant_id": "acme", "gateway_id": str(uuid4())}
    defaults.update(overrides)
    return DiagnosticReport(**defaults)


def _mock_connectivity(**overrides):
    defaults = {"gateway_id": str(uuid4()), "overall_status": "healthy", "stages": []}
    defaults.update(overrides)
    return ConnectivityResult(**defaults)


class TestRunDiagnostic:
    """Tests for GET /v1/admin/diagnostics/{gateway_id}."""

    def test_run_diagnostic_success(self, app_with_cpi_admin, mock_db_session):
        report = _mock_report()
        mock_svc = MagicMock()
        mock_svc.diagnose = AsyncMock(return_value=report)

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.get(f"/v1/admin/diagnostics/{uuid4()}")

        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == "acme"

    def test_run_diagnostic_with_params(self, app_with_cpi_admin, mock_db_session):
        report = _mock_report()
        mock_svc = MagicMock()
        mock_svc.diagnose = AsyncMock(return_value=report)

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.get(f"/v1/admin/diagnostics/{uuid4()}?time_range_minutes=120&request_id=req-001")

        assert resp.status_code == 200
        mock_svc.diagnose.assert_called_once()

    def test_run_diagnostic_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        with TestClient(app_with_no_tenant_user) as client:
            resp = client.get(f"/v1/admin/diagnostics/{uuid4()}")

        assert resp.status_code == 403


class TestCheckConnectivity:
    """Tests for GET /v1/admin/diagnostics/{gateway_id}/connectivity."""

    def test_connectivity_success(self, app_with_cpi_admin, mock_db_session):
        result = _mock_connectivity()
        mock_svc = MagicMock()
        mock_svc.check_connectivity = AsyncMock(return_value=result)

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.get(f"/v1/admin/diagnostics/{uuid4()}/connectivity")

        assert resp.status_code == 200

    def test_connectivity_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        result = _mock_connectivity()
        mock_svc = MagicMock()
        mock_svc.check_connectivity = AsyncMock(return_value=result)

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_tenant_admin) as client:
            resp = client.get(f"/v1/admin/diagnostics/{uuid4()}/connectivity")

        assert resp.status_code == 200

    def test_connectivity_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        with TestClient(app_with_no_tenant_user) as client:
            resp = client.get(f"/v1/admin/diagnostics/{uuid4()}/connectivity")

        assert resp.status_code == 403


class TestDiagnosticHistory:
    """Tests for GET /v1/admin/diagnostics/{gateway_id}/history."""

    def test_history_success(self, app_with_cpi_admin, mock_db_session):
        history = DiagnosticListResponse(items=[], total=0)
        mock_svc = MagicMock()
        mock_svc.get_history = AsyncMock(return_value=history)

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.get(f"/v1/admin/diagnostics/{uuid4()}/history")

        assert resp.status_code == 200

    def test_history_custom_limit(self, app_with_cpi_admin, mock_db_session):
        history = DiagnosticListResponse(items=[], total=0)
        mock_svc = MagicMock()
        mock_svc.get_history = AsyncMock(return_value=history)

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.get(f"/v1/admin/diagnostics/{uuid4()}/history?limit=50")

        assert resp.status_code == 200

    def test_history_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        with TestClient(app_with_no_tenant_user) as client:
            resp = client.get(f"/v1/admin/diagnostics/{uuid4()}/history")

        assert resp.status_code == 403


class TestDiagnosticSummary:
    """Tests for GET /v1/admin/diagnostics/summary."""

    def test_summary_success(self, app_with_cpi_admin, mock_db_session):
        from src.schemas.diagnostic import DiagnosticSummaryResponse

        summary = DiagnosticSummaryResponse(tenant_id="acme", total_errors=5, time_range_minutes=60)
        mock_svc = MagicMock()
        mock_svc.get_summary = AsyncMock(return_value=summary)

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.get("/v1/admin/diagnostics/summary")

        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == "acme"
        assert data["total_errors"] == 5

    def test_summary_custom_time_range(self, app_with_cpi_admin, mock_db_session):
        from src.schemas.diagnostic import DiagnosticSummaryResponse

        summary = DiagnosticSummaryResponse(tenant_id="acme", total_errors=0, time_range_minutes=120)
        mock_svc = MagicMock()
        mock_svc.get_summary = AsyncMock(return_value=summary)

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.get("/v1/admin/diagnostics/summary?time_range_minutes=120")

        assert resp.status_code == 200
        mock_svc.get_summary.assert_called_once()

    def test_summary_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        from src.schemas.diagnostic import DiagnosticSummaryResponse

        summary = DiagnosticSummaryResponse(tenant_id="acme", total_errors=0, time_range_minutes=60)
        mock_svc = MagicMock()
        mock_svc.get_summary = AsyncMock(return_value=summary)

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/admin/diagnostics/summary")

        assert resp.status_code == 200

    def test_summary_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        with TestClient(app_with_no_tenant_user) as client:
            resp = client.get("/v1/admin/diagnostics/summary")

        assert resp.status_code == 403
