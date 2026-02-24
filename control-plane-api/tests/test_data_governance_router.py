"""Tests for Data Governance Router — Wave 2

Covers: /v1/admin/governance (matrix, drift, reconcile).

Strategy:
  - Mock DataGovernanceService to avoid DB dependency
  - Test RBAC: cpi-admin success, non-admin 403
  - Test validation: invalid entity_type returns 400
  - Test all 3 endpoints: matrix, drift, reconcile
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Service mock target
SVC_PATH = "src.routers.data_governance.DataGovernanceService"


def _make_matrix_response():
    """Build a mock GovernanceMatrixResponse."""
    from src.schemas.data_governance import (
        DataSourceOfTruth,
        DriftStatus,
        GovernanceEntity,
        GovernanceMatrixResponse,
        GovernanceMatrixSummary,
        ReconcileAction,
        SyncDirection,
    )

    return GovernanceMatrixResponse(
        timestamp=datetime.now(UTC),
        entities=[
            GovernanceEntity(
                entity_type="api_catalog",
                source_of_truth=DataSourceOfTruth.GIT,
                sync_direction=SyncDirection.GIT_TO_DB,
                drift_detection=True,
                reconciliation_method=ReconcileAction.ON_SYNC,
                drift_status=DriftStatus.CLEAN,
                total_count=10,
                drifted_count=0,
                error_count=0,
            ),
            GovernanceEntity(
                entity_type="mcp_servers",
                source_of_truth=DataSourceOfTruth.GIT,
                sync_direction=SyncDirection.GIT_TO_DB,
                drift_detection=True,
                reconciliation_method=ReconcileAction.ON_SYNC,
                drift_status=DriftStatus.DRIFTED,
                total_count=5,
                drifted_count=2,
                error_count=0,
            ),
            GovernanceEntity(
                entity_type="gateway_deployments",
                source_of_truth=DataSourceOfTruth.HYBRID,
                sync_direction=SyncDirection.DB_TO_GATEWAY,
                drift_detection=True,
                reconciliation_method=ReconcileAction.AUTO,
                drift_status=DriftStatus.CLEAN,
                total_count=3,
                drifted_count=0,
                error_count=0,
            ),
        ],
        summary=GovernanceMatrixSummary(
            total_entity_types=3,
            total_items=18,
            total_drifted=2,
            total_errors=0,
            health_pct=88.9,
        ),
    )


def _make_drift_response():
    """Build a mock DriftReportResponse."""
    from src.schemas.data_governance import (
        DataSourceOfTruth,
        DriftItem,
        DriftReportResponse,
        EntityDriftDetail,
    )

    return DriftReportResponse(
        timestamp=datetime.now(UTC),
        total_entities=2,
        total_drifted=3,
        entities=[
            EntityDriftDetail(
                entity_type="api_catalog",
                source_of_truth=DataSourceOfTruth.GIT,
                total=10,
                drifted=1,
                items=[
                    DriftItem(
                        entity_id="api-weather-001",
                        entity_name="Weather API",
                        drift_type="stale",
                        detail="Never synced from Git (synced_at is null)",
                    ),
                ],
            ),
            EntityDriftDetail(
                entity_type="mcp_servers",
                source_of_truth=DataSourceOfTruth.GIT,
                total=5,
                drifted=2,
                items=[
                    DriftItem(
                        entity_id="mcp-server-001",
                        entity_name="OpenAI MCP",
                        drift_type="orphan",
                        detail="Status: orphan",
                    ),
                    DriftItem(
                        entity_id="mcp-server-002",
                        entity_name="Claude MCP",
                        drift_type="error",
                        detail="Connection timeout",
                    ),
                ],
            ),
        ],
    )


def _make_reconcile_response(entity_type: str, dry_run: bool = True):
    """Build a mock ReconcileResponse."""
    from src.schemas.data_governance import ReconcileResponse, ReconcileResult

    return ReconcileResponse(
        timestamp=datetime.now(UTC),
        results=[
            ReconcileResult(
                entity_type=entity_type,
                action="mark_for_resync" if entity_type == "api_catalog" else "reset_to_pending",
                items_reconciled=3,
                items_skipped=0,
                dry_run=dry_run,
                errors=[],
            ),
        ],
    )


# ── GET /v1/admin/governance/matrix ───────────────────────────────────


class TestGovernanceMatrix:
    """Tests for GET /v1/admin/governance/matrix."""

    def test_matrix_cpi_admin_success(self, app_with_cpi_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.get_governance_matrix = AsyncMock(return_value=_make_matrix_response())

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.get("/v1/admin/governance/matrix")

        assert resp.status_code == 200
        data = resp.json()
        assert "entities" in data
        assert "summary" in data
        assert len(data["entities"]) == 3
        assert data["summary"]["total_entity_types"] == 3
        assert data["summary"]["total_items"] == 18
        assert data["summary"]["total_drifted"] == 2

    def test_matrix_returns_entity_details(self, app_with_cpi_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.get_governance_matrix = AsyncMock(return_value=_make_matrix_response())

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.get("/v1/admin/governance/matrix")

        entities = resp.json()["entities"]
        api_entity = next(e for e in entities if e["entity_type"] == "api_catalog")
        assert api_entity["source_of_truth"] == "git"
        assert api_entity["sync_direction"] == "git→db"
        assert api_entity["drift_status"] == "clean"
        assert api_entity["total_count"] == 10

    def test_matrix_403_for_viewer(self, app_with_no_tenant_user, mock_db_session):
        """Non-admin users should get 403."""
        with TestClient(app_with_no_tenant_user) as client:
            resp = client.get("/v1/admin/governance/matrix")

        assert resp.status_code == 403

    def test_matrix_403_for_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        """Tenant admins (non cpi-admin) should get 403."""
        with TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/admin/governance/matrix")

        assert resp.status_code == 403


# ── GET /v1/admin/governance/drift ────────────────────────────────────


class TestGovernanceDrift:
    """Tests for GET /v1/admin/governance/drift."""

    def test_drift_cpi_admin_success(self, app_with_cpi_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.get_drift_report = AsyncMock(return_value=_make_drift_response())

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.get("/v1/admin/governance/drift")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_entities"] == 2
        assert data["total_drifted"] == 3
        assert len(data["entities"]) == 2

    def test_drift_includes_item_details(self, app_with_cpi_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.get_drift_report = AsyncMock(return_value=_make_drift_response())

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.get("/v1/admin/governance/drift")

        entities = resp.json()["entities"]
        mcp_entity = next(e for e in entities if e["entity_type"] == "mcp_servers")
        assert mcp_entity["drifted"] == 2
        assert len(mcp_entity["items"]) == 2
        orphan = next(i for i in mcp_entity["items"] if i["drift_type"] == "orphan")
        assert orphan["entity_name"] == "OpenAI MCP"

    def test_drift_403_for_viewer(self, app_with_no_tenant_user, mock_db_session):
        with TestClient(app_with_no_tenant_user) as client:
            resp = client.get("/v1/admin/governance/drift")

        assert resp.status_code == 403


# ── POST /v1/admin/governance/reconcile/{entity_type} ─────────────────


class TestGovernanceReconcile:
    """Tests for POST /v1/admin/governance/reconcile/{entity_type}."""

    def test_reconcile_api_catalog_dry_run(self, app_with_cpi_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.reconcile = AsyncMock(
            return_value=_make_reconcile_response("api_catalog", dry_run=True)
        )

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.post(
                "/v1/admin/governance/reconcile/api_catalog",
                json={"dry_run": True},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 1
        result = data["results"][0]
        assert result["entity_type"] == "api_catalog"
        assert result["action"] == "mark_for_resync"
        assert result["items_reconciled"] == 3
        assert result["dry_run"] is True

    def test_reconcile_mcp_servers_real(self, app_with_cpi_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.reconcile = AsyncMock(
            return_value=_make_reconcile_response("mcp_servers", dry_run=False)
        )

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.post(
                "/v1/admin/governance/reconcile/mcp_servers",
                json={"dry_run": False},
            )

        assert resp.status_code == 200
        result = resp.json()["results"][0]
        assert result["entity_type"] == "mcp_servers"
        assert result["action"] == "reset_to_pending"
        assert result["dry_run"] is False

    def test_reconcile_gateway_deployments(self, app_with_cpi_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.reconcile = AsyncMock(
            return_value=_make_reconcile_response("gateway_deployments", dry_run=True)
        )

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.post(
                "/v1/admin/governance/reconcile/gateway_deployments",
                json={"dry_run": True},
            )

        assert resp.status_code == 200

    def test_reconcile_default_dry_run(self, app_with_cpi_admin, mock_db_session):
        """Default body should be dry_run=True."""
        mock_svc = MagicMock()
        mock_svc.reconcile = AsyncMock(
            return_value=_make_reconcile_response("api_catalog", dry_run=True)
        )

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.post("/v1/admin/governance/reconcile/api_catalog")

        assert resp.status_code == 200

    def test_reconcile_invalid_entity_type_400(self, app_with_cpi_admin, mock_db_session):
        with TestClient(app_with_cpi_admin) as client:
            resp = client.post(
                "/v1/admin/governance/reconcile/invalid_type",
                json={"dry_run": True},
            )

        assert resp.status_code == 400
        assert "Invalid entity type" in resp.json()["detail"]
        assert "api_catalog" in resp.json()["detail"]

    def test_reconcile_403_for_viewer(self, app_with_no_tenant_user, mock_db_session):
        with TestClient(app_with_no_tenant_user) as client:
            resp = client.post(
                "/v1/admin/governance/reconcile/api_catalog",
                json={"dry_run": True},
            )

        assert resp.status_code == 403

    def test_reconcile_403_for_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        with TestClient(app_with_tenant_admin) as client:
            resp = client.post(
                "/v1/admin/governance/reconcile/mcp_servers",
                json={"dry_run": True},
            )

        assert resp.status_code == 403
