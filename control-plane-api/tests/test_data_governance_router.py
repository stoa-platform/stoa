"""Tests for data governance router (CAB-1324)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.routers.data_governance import router
from src.schemas.data_governance import (
    DataSourceOfTruth,
    DriftItem,
    DriftReportResponse,
    DriftStatus,
    EntityDriftDetail,
    GovernanceEntity,
    GovernanceMatrixResponse,
    GovernanceMatrixSummary,
    ReconcileAction,
    ReconcileResponse,
    ReconcileResult,
    SyncDirection,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 2, 24, 12, 0, 0, tzinfo=UTC)


def _make_admin_user():
    return MagicMock(
        id="admin-1",
        email="admin@test.com",
        username="admin",
        roles=["cpi-admin"],
        tenant_id=None,
    )


def _make_viewer_user():
    return MagicMock(
        id="viewer-1",
        email="viewer@test.com",
        username="viewer",
        roles=["viewer"],
        tenant_id="t-1",
    )


def _make_matrix_response() -> GovernanceMatrixResponse:
    return GovernanceMatrixResponse(
        timestamp=_NOW,
        entities=[
            GovernanceEntity(
                entity_type="api_catalog",
                source_of_truth=DataSourceOfTruth.GIT,
                sync_direction=SyncDirection.GIT_TO_DB,
                drift_detection=True,
                reconciliation_method=ReconcileAction.ON_SYNC,
                last_sync_at=_NOW,
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
                last_sync_at=_NOW,
                drift_status=DriftStatus.DRIFTED,
                total_count=5,
                drifted_count=1,
                error_count=0,
            ),
            GovernanceEntity(
                entity_type="gateway_deployments",
                source_of_truth=DataSourceOfTruth.HYBRID,
                sync_direction=SyncDirection.DB_TO_GATEWAY,
                drift_detection=True,
                reconciliation_method=ReconcileAction.AUTO,
                last_sync_at=_NOW,
                drift_status=DriftStatus.ERROR,
                total_count=3,
                drifted_count=0,
                error_count=1,
            ),
        ],
        summary=GovernanceMatrixSummary(
            total_entity_types=3,
            total_items=18,
            total_drifted=1,
            total_errors=1,
            health_pct=88.9,
        ),
    )


def _make_drift_report() -> DriftReportResponse:
    return DriftReportResponse(
        timestamp=_NOW,
        total_entities=3,
        total_drifted=2,
        entities=[
            EntityDriftDetail(
                entity_type="api_catalog",
                source_of_truth=DataSourceOfTruth.GIT,
                total=10,
                drifted=0,
                items=[],
            ),
            EntityDriftDetail(
                entity_type="mcp_servers",
                source_of_truth=DataSourceOfTruth.GIT,
                total=5,
                drifted=1,
                items=[
                    DriftItem(
                        entity_id="orphan-server",
                        entity_name="Orphan Server",
                        drift_type="orphan",
                        detail="Status: orphan",
                        last_sync_at=_NOW,
                    )
                ],
            ),
            EntityDriftDetail(
                entity_type="gateway_deployments",
                source_of_truth=DataSourceOfTruth.HYBRID,
                total=3,
                drifted=1,
                items=[
                    DriftItem(
                        entity_id="dep-abc12345",
                        entity_name="deployment-dep-abc1",
                        drift_type="desync",
                        detail="Status: drifted",
                    )
                ],
            ),
        ],
    )


def _make_reconcile_response(entity_type: str, dry_run: bool) -> ReconcileResponse:
    return ReconcileResponse(
        timestamp=_NOW,
        results=[
            ReconcileResult(
                entity_type=entity_type,
                action="reset_to_pending",
                items_reconciled=2,
                items_skipped=0,
                dry_run=dry_run,
            )
        ],
    )


def _create_app(user_factory=_make_admin_user):
    """Create a test app with mocked auth."""
    app = FastAPI()
    app.include_router(router)

    from src.auth.dependencies import get_current_user
    from src.database import get_db

    app.dependency_overrides[get_current_user] = user_factory
    app.dependency_overrides[get_db] = lambda: AsyncMock()

    return app


# ---------------------------------------------------------------------------
# Tests — Governance Matrix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_governance_matrix_success():
    app = _create_app()
    mock_response = _make_matrix_response()

    with patch("src.routers.data_governance.DataGovernanceService") as MockSvc:
        MockSvc.return_value.get_governance_matrix = AsyncMock(return_value=mock_response)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/admin/governance/matrix")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["entities"]) == 3
    assert data["summary"]["total_entity_types"] == 3
    assert data["summary"]["total_items"] == 18
    assert data["summary"]["health_pct"] == 88.9


@pytest.mark.asyncio
async def test_get_governance_matrix_entity_fields():
    app = _create_app()
    mock_response = _make_matrix_response()

    with patch("src.routers.data_governance.DataGovernanceService") as MockSvc:
        MockSvc.return_value.get_governance_matrix = AsyncMock(return_value=mock_response)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/admin/governance/matrix")

    api_entity = resp.json()["entities"][0]
    assert api_entity["entity_type"] == "api_catalog"
    assert api_entity["source_of_truth"] == "git"
    assert api_entity["sync_direction"] == "git→db"
    assert api_entity["drift_detection"] is True
    assert api_entity["drift_status"] == "clean"
    assert api_entity["total_count"] == 10


@pytest.mark.asyncio
async def test_get_governance_matrix_forbidden_for_viewer():
    app = _create_app(user_factory=_make_viewer_user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/admin/governance/matrix")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Tests — Drift Report
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_drift_report_success():
    app = _create_app()
    mock_response = _make_drift_report()

    with patch("src.routers.data_governance.DataGovernanceService") as MockSvc:
        MockSvc.return_value.get_drift_report = AsyncMock(return_value=mock_response)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/admin/governance/drift")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_drifted"] == 2
    assert len(data["entities"]) == 3


@pytest.mark.asyncio
async def test_get_drift_report_shows_drift_items():
    app = _create_app()
    mock_response = _make_drift_report()

    with patch("src.routers.data_governance.DataGovernanceService") as MockSvc:
        MockSvc.return_value.get_drift_report = AsyncMock(return_value=mock_response)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/admin/governance/drift")

    mcp_entity = resp.json()["entities"][1]
    assert mcp_entity["entity_type"] == "mcp_servers"
    assert mcp_entity["drifted"] == 1
    assert len(mcp_entity["items"]) == 1
    assert mcp_entity["items"][0]["drift_type"] == "orphan"


@pytest.mark.asyncio
async def test_get_drift_report_forbidden_for_viewer():
    app = _create_app(user_factory=_make_viewer_user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/admin/governance/drift")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Tests — Reconciliation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_dry_run():
    app = _create_app()
    mock_response = _make_reconcile_response("mcp_servers", dry_run=True)

    with patch("src.routers.data_governance.DataGovernanceService") as MockSvc:
        MockSvc.return_value.reconcile = AsyncMock(return_value=mock_response)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/admin/governance/reconcile/mcp_servers",
                json={"dry_run": True},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["results"][0]["dry_run"] is True
    assert data["results"][0]["items_reconciled"] == 2


@pytest.mark.asyncio
async def test_reconcile_apply():
    app = _create_app()
    mock_response = _make_reconcile_response("gateway_deployments", dry_run=False)

    with patch("src.routers.data_governance.DataGovernanceService") as MockSvc:
        MockSvc.return_value.reconcile = AsyncMock(return_value=mock_response)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/admin/governance/reconcile/gateway_deployments",
                json={"dry_run": False},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["results"][0]["dry_run"] is False


@pytest.mark.asyncio
async def test_reconcile_invalid_entity_type():
    app = _create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/admin/governance/reconcile/invalid_type",
            json={"dry_run": True},
        )

    assert resp.status_code == 400
    assert "Invalid entity type" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_reconcile_forbidden_for_viewer():
    app = _create_app(user_factory=_make_viewer_user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/admin/governance/reconcile/mcp_servers",
            json={"dry_run": True},
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_reconcile_default_is_dry_run():
    app = _create_app()
    mock_response = _make_reconcile_response("api_catalog", dry_run=True)

    with patch("src.routers.data_governance.DataGovernanceService") as MockSvc:
        instance = MockSvc.return_value
        instance.reconcile = AsyncMock(return_value=mock_response)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/admin/governance/reconcile/api_catalog",
            )

    assert resp.status_code == 200
    # Verify the service was called with dry_run=True (default)
    instance.reconcile.assert_called_once_with("api_catalog", dry_run=True)


# ---------------------------------------------------------------------------
# Tests — Schema validation
# ---------------------------------------------------------------------------


def test_governance_entity_schema():
    entity = GovernanceEntity(
        entity_type="test",
        source_of_truth=DataSourceOfTruth.GIT,
        sync_direction=SyncDirection.GIT_TO_DB,
        drift_detection=True,
        reconciliation_method=ReconcileAction.ON_SYNC,
    )
    assert entity.drift_status == DriftStatus.UNKNOWN
    assert entity.total_count == 0


def test_drift_item_schema():
    item = DriftItem(
        entity_id="abc",
        entity_name="Test",
        drift_type="orphan",
        detail="orphaned",
    )
    assert item.last_sync_at is None


def test_reconcile_result_schema():
    result = ReconcileResult(
        entity_type="test",
        action="reset",
        items_reconciled=5,
        dry_run=True,
    )
    assert result.items_skipped == 0
    assert result.errors == []


def test_matrix_summary_health_pct():
    summary = GovernanceMatrixSummary(
        total_entity_types=3,
        total_items=100,
        total_drifted=5,
        total_errors=2,
        health_pct=93.0,
    )
    assert summary.health_pct == 93.0


# ---------------------------------------------------------------------------
# Tests — Service unit tests (entity registry)
# ---------------------------------------------------------------------------


def test_entity_registry_has_three_types():
    from src.services.data_governance_service import _ENTITY_REGISTRY

    assert len(_ENTITY_REGISTRY) == 3
    types = {e["entity_type"] for e in _ENTITY_REGISTRY}
    assert types == {"api_catalog", "mcp_servers", "gateway_deployments"}


def test_compute_drift_status_clean():
    from src.services.data_governance_service import DataGovernanceService

    status = DataGovernanceService._compute_drift_status({"total": 10, "drifted": 0, "errors": 0})
    assert status == DriftStatus.CLEAN


def test_compute_drift_status_drifted():
    from src.services.data_governance_service import DataGovernanceService

    status = DataGovernanceService._compute_drift_status({"total": 10, "drifted": 3, "errors": 0})
    assert status == DriftStatus.DRIFTED


def test_compute_drift_status_error():
    from src.services.data_governance_service import DataGovernanceService

    status = DataGovernanceService._compute_drift_status({"total": 10, "drifted": 0, "errors": 2})
    assert status == DriftStatus.ERROR


def test_compute_drift_status_unknown_when_empty():
    from src.services.data_governance_service import DataGovernanceService

    status = DataGovernanceService._compute_drift_status({"total": 0, "drifted": 0, "errors": 0})
    assert status == DriftStatus.UNKNOWN


def test_compute_drift_status_error_takes_priority():
    from src.services.data_governance_service import DataGovernanceService

    status = DataGovernanceService._compute_drift_status({"total": 10, "drifted": 5, "errors": 1})
    assert status == DriftStatus.ERROR
