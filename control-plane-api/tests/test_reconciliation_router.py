"""Tests for Reconciliation Router — CAB-1527

Covers: /v1/tenants/{tenant_id}/reconciliation (drift check, sync trigger, status).
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

RECON_SVC_PATH = "src.routers.reconciliation.ReconciliationService"


def _make_drift_report(tenant_id: str = "acme", in_sync: bool = True):
    from src.schemas.reconciliation import DriftReport

    return DriftReport(
        tenant_id=tenant_id,
        checked_at=datetime.now(UTC),
        in_sync=in_sync,
        total_scim_clients=3,
        total_gateway_consumers=3,
        drift_items=[],
    )


def _make_reconciliation_result(tenant_id: str = "acme", success: bool = True):
    from src.schemas.reconciliation import ReconciliationResult

    now = datetime.now(UTC)
    return ReconciliationResult(
        tenant_id=tenant_id,
        started_at=now,
        completed_at=now,
        success=success,
        actions_taken=0,
        actions_failed=0,
        results=[],
    )


def _make_status(tenant_id: str = "acme"):
    from src.schemas.reconciliation import ReconciliationStatus

    return ReconciliationStatus(
        tenant_id=tenant_id,
        last_check=datetime.now(UTC),
        last_sync=None,
        in_sync=True,
        drift_count=0,
        last_error=None,
    )


# ============== GET /drift ==============


class TestCheckDrift:
    """GET /v1/tenants/{tenant_id}/reconciliation/drift"""

    def test_check_drift_in_sync(self, client):
        report = _make_drift_report(in_sync=True)
        mock_svc = MagicMock()
        mock_svc.check_drift = AsyncMock(return_value=report)

        with patch(RECON_SVC_PATH, return_value=mock_svc):
            resp = client.get("/v1/tenants/acme/reconciliation/drift")

        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == "acme"
        assert data["in_sync"] is True
        assert data["drift_items"] == []
        mock_svc.check_drift.assert_awaited_once_with("acme")

    def test_check_drift_with_drift(self, client):
        from src.schemas.reconciliation import DriftItem, DriftType

        report = _make_drift_report(in_sync=False)
        report.drift_items = [
            DriftItem(
                drift_type=DriftType.MISSING_IN_GATEWAY,
                client_name="acme-billing",
                detail="missing",
                scim_roles=["api:read"],
                gateway_roles=[],
            )
        ]
        report.total_gateway_consumers = 2

        mock_svc = MagicMock()
        mock_svc.check_drift = AsyncMock(return_value=report)

        with patch(RECON_SVC_PATH, return_value=mock_svc):
            resp = client.get("/v1/tenants/acme/reconciliation/drift")

        assert resp.status_code == 200
        data = resp.json()
        assert data["in_sync"] is False
        assert len(data["drift_items"]) == 1
        assert data["drift_items"][0]["drift_type"] == "missing_in_gateway"

    def test_check_drift_different_tenant(self, client):
        report = _make_drift_report(tenant_id="beta-corp")
        mock_svc = MagicMock()
        mock_svc.check_drift = AsyncMock(return_value=report)

        with patch(RECON_SVC_PATH, return_value=mock_svc):
            resp = client.get("/v1/tenants/beta-corp/reconciliation/drift")

        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == "beta-corp"
        mock_svc.check_drift.assert_awaited_once_with("beta-corp")


# ============== POST /sync ==============


class TestTriggerReconciliation:
    """POST /v1/tenants/{tenant_id}/reconciliation/sync"""

    def test_sync_success(self, client):
        result = _make_reconciliation_result(success=True)
        mock_svc = MagicMock()
        mock_svc.reconcile = AsyncMock(return_value=result)

        with patch(RECON_SVC_PATH, return_value=mock_svc):
            resp = client.post("/v1/tenants/acme/reconciliation/sync")

        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == "acme"
        assert data["success"] is True
        assert data["actions_taken"] == 0
        mock_svc.reconcile.assert_awaited_once_with("acme")

    def test_sync_with_actions(self, client):
        from src.schemas.reconciliation import ReconciliationAction, ReconciliationActionResult

        result = _make_reconciliation_result(success=True)
        result.actions_taken = 2
        result.results = [
            ReconciliationActionResult(
                client_name="acme-billing",
                action=ReconciliationAction.PROVISIONED,
                detail="Provisioned successfully",
            ),
            ReconciliationActionResult(
                client_name="acme-analytics",
                action=ReconciliationAction.UPDATED_ROLES,
                detail="Roles updated",
            ),
        ]

        mock_svc = MagicMock()
        mock_svc.reconcile = AsyncMock(return_value=result)

        with patch(RECON_SVC_PATH, return_value=mock_svc):
            resp = client.post("/v1/tenants/acme/reconciliation/sync")

        assert resp.status_code == 200
        data = resp.json()
        assert data["actions_taken"] == 2
        assert len(data["results"]) == 2
        assert data["results"][0]["action"] == "provisioned"

    def test_sync_partial_failure(self, client):
        result = _make_reconciliation_result(success=False)
        result.actions_failed = 1

        mock_svc = MagicMock()
        mock_svc.reconcile = AsyncMock(return_value=result)

        with patch(RECON_SVC_PATH, return_value=mock_svc):
            resp = client.post("/v1/tenants/acme/reconciliation/sync")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["actions_failed"] == 1


# ============== GET /status ==============


class TestGetStatus:
    """GET /v1/tenants/{tenant_id}/reconciliation/status"""

    def test_get_status_in_sync(self, client):
        status = _make_status()
        mock_svc = MagicMock()
        mock_svc.get_status = AsyncMock(return_value=status)

        with patch(RECON_SVC_PATH, return_value=mock_svc):
            resp = client.get("/v1/tenants/acme/reconciliation/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == "acme"
        assert data["in_sync"] is True
        assert data["drift_count"] == 0
        assert data["last_error"] is None
        mock_svc.get_status.assert_awaited_once_with("acme")

    def test_get_status_with_drift(self, client):
        from src.schemas.reconciliation import ReconciliationStatus

        status = ReconciliationStatus(
            tenant_id="acme",
            last_check=datetime.now(UTC),
            last_sync=datetime.now(UTC),
            in_sync=False,
            drift_count=3,
            last_error="Gateway unreachable",
        )

        mock_svc = MagicMock()
        mock_svc.get_status = AsyncMock(return_value=status)

        with patch(RECON_SVC_PATH, return_value=mock_svc):
            resp = client.get("/v1/tenants/acme/reconciliation/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["in_sync"] is False
        assert data["drift_count"] == 3
        assert data["last_error"] == "Gateway unreachable"
        assert data["last_sync"] is not None

    def test_get_status_never_checked(self, client):
        from src.schemas.reconciliation import ReconciliationStatus

        status = ReconciliationStatus(
            tenant_id="new-tenant",
            last_check=None,
            last_sync=None,
            in_sync=True,
            drift_count=0,
            last_error=None,
        )

        mock_svc = MagicMock()
        mock_svc.get_status = AsyncMock(return_value=status)

        with patch(RECON_SVC_PATH, return_value=mock_svc):
            resp = client.get("/v1/tenants/new-tenant/reconciliation/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["last_check"] is None
        assert data["last_sync"] is None
