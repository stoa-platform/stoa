"""Tests for Reconciliation Router — CAB-1526

Tests the /v1/tenants/{tenant_id}/reconciliation/ endpoints.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from src.schemas.reconciliation import (
    DriftItem,
    DriftReport,
    DriftType,
    ReconciliationAction,
    ReconciliationActionResult,
    ReconciliationResult,
    ReconciliationStatus,
)

SVC_PATH = "src.routers.reconciliation.ReconciliationService"


class TestCheckDrift:
    """GET /v1/tenants/{tenant_id}/reconciliation/drift"""

    def test_drift_in_sync(self, client_as_tenant_admin):
        report = DriftReport(
            tenant_id="acme",
            checked_at=datetime(2026, 2, 27, tzinfo=UTC),
            in_sync=True,
            total_scim_clients=5,
            total_gateway_consumers=5,
            drift_items=[],
        )
        with patch(SVC_PATH) as MockSvc:
            instance = MockSvc.return_value
            instance.check_drift = AsyncMock(return_value=report)

            resp = client_as_tenant_admin.get("/v1/tenants/acme/reconciliation/drift")

        assert resp.status_code == 200
        body = resp.json()
        assert body["in_sync"] is True
        assert body["total_scim_clients"] == 5
        assert body["drift_items"] == []

    def test_drift_with_items(self, client_as_tenant_admin):
        report = DriftReport(
            tenant_id="acme",
            checked_at=datetime(2026, 2, 27, tzinfo=UTC),
            in_sync=False,
            total_scim_clients=5,
            total_gateway_consumers=4,
            drift_items=[
                DriftItem(
                    drift_type=DriftType.MISSING_IN_GATEWAY,
                    client_name="acme-billing",
                    detail="Client exists in SCIM but not in gateway",
                    scim_roles=["api:read"],
                    gateway_roles=[],
                ),
            ],
        )
        with patch(SVC_PATH) as MockSvc:
            instance = MockSvc.return_value
            instance.check_drift = AsyncMock(return_value=report)

            resp = client_as_tenant_admin.get("/v1/tenants/acme/reconciliation/drift")

        assert resp.status_code == 200
        body = resp.json()
        assert body["in_sync"] is False
        assert len(body["drift_items"]) == 1
        assert body["drift_items"][0]["drift_type"] == "missing_in_gateway"

    def test_drift_cpi_admin_cross_tenant(self, client_as_cpi_admin):
        report = DriftReport(
            tenant_id="other-tenant",
            checked_at=datetime(2026, 2, 27, tzinfo=UTC),
            in_sync=True,
            total_scim_clients=0,
            total_gateway_consumers=0,
        )
        with patch(SVC_PATH) as MockSvc:
            instance = MockSvc.return_value
            instance.check_drift = AsyncMock(return_value=report)

            resp = client_as_cpi_admin.get("/v1/tenants/other-tenant/reconciliation/drift")

        assert resp.status_code == 200


class TestTriggerReconciliation:
    """POST /v1/tenants/{tenant_id}/reconciliation/sync"""

    def test_sync_success(self, client_as_tenant_admin):
        result = ReconciliationResult(
            tenant_id="acme",
            started_at=datetime(2026, 2, 27, 10, 0, tzinfo=UTC),
            completed_at=datetime(2026, 2, 27, 10, 0, 5, tzinfo=UTC),
            success=True,
            actions_taken=2,
            actions_failed=0,
            results=[
                ReconciliationActionResult(
                    client_name="acme-billing",
                    action=ReconciliationAction.PROVISIONED,
                    detail="Provisioned in gateway",
                ),
                ReconciliationActionResult(
                    client_name="stale-app",
                    action=ReconciliationAction.DEPROVISIONED,
                    detail="Removed orphaned consumer",
                ),
            ],
        )
        with patch(SVC_PATH) as MockSvc:
            instance = MockSvc.return_value
            instance.reconcile = AsyncMock(return_value=result)

            resp = client_as_tenant_admin.post("/v1/tenants/acme/reconciliation/sync")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["actions_taken"] == 2
        assert body["actions_failed"] == 0
        assert len(body["results"]) == 2

    def test_sync_with_failures(self, client_as_tenant_admin):
        result = ReconciliationResult(
            tenant_id="acme",
            started_at=datetime(2026, 2, 27, 10, 0, tzinfo=UTC),
            completed_at=datetime(2026, 2, 27, 10, 0, 5, tzinfo=UTC),
            success=False,
            actions_taken=1,
            actions_failed=1,
            results=[
                ReconciliationActionResult(
                    client_name="acme-billing",
                    action=ReconciliationAction.FAILED,
                    detail="Gateway unreachable",
                ),
            ],
        )
        with patch(SVC_PATH) as MockSvc:
            instance = MockSvc.return_value
            instance.reconcile = AsyncMock(return_value=result)

            resp = client_as_tenant_admin.post("/v1/tenants/acme/reconciliation/sync")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["actions_failed"] == 1


class TestGetStatus:
    """GET /v1/tenants/{tenant_id}/reconciliation/status"""

    def test_status_healthy(self, client_as_tenant_admin):
        status = ReconciliationStatus(
            tenant_id="acme",
            last_check=datetime(2026, 2, 27, 10, 0, tzinfo=UTC),
            last_sync=datetime(2026, 2, 27, 9, 0, tzinfo=UTC),
            in_sync=True,
            drift_count=0,
        )
        with patch(SVC_PATH) as MockSvc:
            instance = MockSvc.return_value
            instance.get_status = AsyncMock(return_value=status)

            resp = client_as_tenant_admin.get("/v1/tenants/acme/reconciliation/status")

        assert resp.status_code == 200
        body = resp.json()
        assert body["in_sync"] is True
        assert body["drift_count"] == 0
        assert body["last_error"] is None

    def test_status_with_drift(self, client_as_tenant_admin):
        status = ReconciliationStatus(
            tenant_id="acme",
            last_check=datetime(2026, 2, 27, 10, 0, tzinfo=UTC),
            in_sync=False,
            drift_count=3,
            last_error="Gateway timeout during sync",
        )
        with patch(SVC_PATH) as MockSvc:
            instance = MockSvc.return_value
            instance.get_status = AsyncMock(return_value=status)

            resp = client_as_tenant_admin.get("/v1/tenants/acme/reconciliation/status")

        assert resp.status_code == 200
        body = resp.json()
        assert body["in_sync"] is False
        assert body["drift_count"] == 3
        assert "Gateway timeout" in body["last_error"]

    def test_status_never_checked(self, client_as_tenant_admin):
        status = ReconciliationStatus(tenant_id="acme")
        with patch(SVC_PATH) as MockSvc:
            instance = MockSvc.return_value
            instance.get_status = AsyncMock(return_value=status)

            resp = client_as_tenant_admin.get("/v1/tenants/acme/reconciliation/status")

        assert resp.status_code == 200
        body = resp.json()
        assert body["last_check"] is None
        assert body["in_sync"] is True
