"""Tests for Admin Prospects Router — CAB-911

Covers: GET /v1/admin/prospects (list), /metrics, /export, /{invite_id}
All endpoints require cpi-admin role via _require_admin helper.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

PROSPECTS_SVC_PATH = "src.routers.admin_prospects.prospects_service"


def _mock_prospect_detail(**overrides):
    """Build a mock ProspectDetail — use MagicMock to avoid Pydantic schema coupling."""
    from datetime import datetime

    from src.schemas.prospects import ProspectDetail, ProspectMetrics

    pid = uuid4()
    now = datetime.utcnow()
    data = {
        "id": pid,
        "email": "prospect@example.com",
        "company": "Acme Corp",
        "status": "opened",
        "source": "invite",
        "created_at": now,
        "opened_at": now,
        "expires_at": now,
        "nps_score": None,
        "nps_category": None,
        "nps_comment": None,
        "metrics": ProspectMetrics(),
        "timeline": [],
        "errors": [],
    }
    data.update(overrides)
    return ProspectDetail(**data)


def _mock_list_response(items=None):
    """Build a ProspectListResponse mock."""
    mock = MagicMock()
    mock.items = items or []
    mock.total = len(mock.items)
    mock.page = 1
    mock.page_size = 25
    return mock


def _mock_metrics_response():
    """Build a ProspectsMetricsResponse mock."""
    mock = MagicMock()
    mock.total_invited = 10
    mock.total_opened = 6
    mock.total_converted = 2
    mock.conversion_rate = 20.0
    mock.avg_time_to_first_tool_seconds = 300
    mock.nps_promoters = 2
    mock.nps_passives = 1
    mock.nps_detractors = 0
    mock.nps_score = 66.7
    mock.top_companies = []
    return mock


# ============== 403 Non-Admin Access ==============


class TestAdminProspectsRBAC:
    """Verify that all endpoints require cpi-admin role."""

    def test_list_prospects_403_for_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        with TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/admin/prospects")

        assert resp.status_code == 403
        assert "admin" in resp.json()["detail"].lower()

    def test_metrics_403_for_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        with TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/admin/prospects/metrics")

        assert resp.status_code == 403

    def test_export_403_for_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        with TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/admin/prospects/export")

        assert resp.status_code == 403

    def test_get_prospect_403_for_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        with TestClient(app_with_tenant_admin) as client:
            resp = client.get(f"/v1/admin/prospects/{uuid4()}")

        assert resp.status_code == 403

    def test_list_prospects_403_for_viewer(self, app_with_no_tenant_user, mock_db_session):
        with TestClient(app_with_no_tenant_user) as client:
            resp = client.get("/v1/admin/prospects")

        assert resp.status_code == 403


# ============== List Prospects ==============


class TestListProspects:
    """GET /v1/admin/prospects"""

    def test_list_prospects_success(self, app_with_cpi_admin, mock_db_session):
        mock_response = _mock_list_response()

        with (
            patch(f"{PROSPECTS_SVC_PATH}.list_prospects", new=AsyncMock(return_value=mock_response)),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.get("/v1/admin/prospects")

        assert resp.status_code == 200

    def test_list_prospects_with_filters(self, app_with_cpi_admin, mock_db_session):
        mock_response = _mock_list_response()

        with (
            patch(f"{PROSPECTS_SVC_PATH}.list_prospects", new=AsyncMock(return_value=mock_response)) as mock_svc,
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.get("/v1/admin/prospects?company=Acme&status=opened&page=2&limit=10")

        assert resp.status_code == 200
        call_kwargs = mock_svc.call_args.kwargs
        assert call_kwargs["company"] == "Acme"
        assert call_kwargs["status"] == "opened"
        assert call_kwargs["page"] == 2
        assert call_kwargs["limit"] == 10

    def test_list_prospects_empty(self, app_with_cpi_admin, mock_db_session):
        mock_response = _mock_list_response(items=[])

        with (
            patch(f"{PROSPECTS_SVC_PATH}.list_prospects", new=AsyncMock(return_value=mock_response)),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.get("/v1/admin/prospects")

        assert resp.status_code == 200


# ============== Metrics ==============


class TestGetProspectsMetrics:
    """GET /v1/admin/prospects/metrics"""

    def test_metrics_success(self, app_with_cpi_admin, mock_db_session):
        mock_response = _mock_metrics_response()

        with (
            patch(f"{PROSPECTS_SVC_PATH}.get_metrics", new=AsyncMock(return_value=mock_response)),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.get("/v1/admin/prospects/metrics")

        assert resp.status_code == 200

    def test_metrics_with_date_range(self, app_with_cpi_admin, mock_db_session):
        mock_response = _mock_metrics_response()

        with (
            patch(f"{PROSPECTS_SVC_PATH}.get_metrics", new=AsyncMock(return_value=mock_response)) as mock_svc,
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.get(
                "/v1/admin/prospects/metrics" "?date_from=2026-01-01T00:00:00&date_to=2026-02-01T00:00:00"
            )

        assert resp.status_code == 200
        call_kwargs = mock_svc.call_args.kwargs
        assert call_kwargs["date_from"] is not None
        assert call_kwargs["date_to"] is not None


# ============== Export CSV ==============


class TestExportProspects:
    """GET /v1/admin/prospects/export"""

    def test_export_success_returns_csv(self, app_with_cpi_admin, mock_db_session):
        csv_data = b"email,company,status\nprospect@example.com,Acme,opened\n"

        with (
            patch(f"{PROSPECTS_SVC_PATH}.export_prospects_csv", new=AsyncMock(return_value=csv_data)),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.get("/v1/admin/prospects/export")

        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "attachment" in resp.headers["content-disposition"]
        assert resp.content == csv_data

    def test_export_filename_contains_timestamp(self, app_with_cpi_admin, mock_db_session):
        csv_data = b"email,company\n"

        with (
            patch(f"{PROSPECTS_SVC_PATH}.export_prospects_csv", new=AsyncMock(return_value=csv_data)),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.get("/v1/admin/prospects/export")

        assert "prospects_" in resp.headers["content-disposition"]
        assert ".csv" in resp.headers["content-disposition"]


# ============== Get Prospect Detail ==============


class TestGetProspect:
    """GET /v1/admin/prospects/{invite_id}"""

    def test_get_prospect_success(self, app_with_cpi_admin, mock_db_session):
        invite_id = uuid4()
        detail = _mock_prospect_detail(invite_id=invite_id)

        with (
            patch(f"{PROSPECTS_SVC_PATH}.get_prospect_detail", new=AsyncMock(return_value=detail)),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.get(f"/v1/admin/prospects/{invite_id}")

        assert resp.status_code == 200

    def test_get_prospect_404(self, app_with_cpi_admin, mock_db_session):
        with (
            patch(f"{PROSPECTS_SVC_PATH}.get_prospect_detail", new=AsyncMock(return_value=None)),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.get(f"/v1/admin/prospects/{uuid4()}")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Prospect not found"

    def test_get_prospect_invalid_uuid(self, app_with_cpi_admin, mock_db_session):
        with TestClient(app_with_cpi_admin) as client:
            resp = client.get("/v1/admin/prospects/not-a-uuid")

        assert resp.status_code == 422
