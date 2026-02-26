"""Tests for SCIM↔Gateway reconciliation service (CAB-1484)."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.adapters.gateway_adapter_interface import AdapterResult
from src.models.oauth_client import OAuthClientStatus
from src.schemas.reconciliation import (
    DriftItem,
    DriftType,
    ReconciliationAction,
    ReconciliationActionResult,
    ReconciliationResult,
    ReconciliationStatus,
)
from src.services.scim_gateway_reconciliation import ReconciliationService


# ---- Fixtures ----


def _make_client(client_id: str, name: str, tenant: str, roles: list[str] | None = None, status: str = "active"):
    """Create a mock OAuthClient."""
    client = MagicMock()
    client.id = client_id
    client.tenant_id = tenant
    client.keycloak_client_id = name
    client.client_name = name
    client.product_roles = roles or []
    client.status = status
    return client


def _make_gateway_adapter(apps: list[dict] | None = None, provision_ok: bool = True, deprovision_ok: bool = True):
    """Create a mock gateway adapter."""
    adapter = AsyncMock()
    adapter.list_applications.return_value = AdapterResult(
        success=True, data={"applications": apps or []}
    )
    adapter.provision_application.return_value = AdapterResult(success=provision_ok, error=None if provision_ok else "provision failed")
    adapter.deprovision_application.return_value = AdapterResult(success=deprovision_ok, error=None if deprovision_ok else "deprovision failed")
    return adapter


@pytest.fixture
def db():
    return AsyncMock()


# ---- Schema Tests ----


class TestSchemas:
    def test_drift_item_creation(self):
        item = DriftItem(
            drift_type=DriftType.MISSING_IN_GATEWAY,
            client_name="acme-svc",
            detail="Not in gateway",
            scim_roles=["api:read"],
        )
        assert item.drift_type == DriftType.MISSING_IN_GATEWAY
        assert item.client_name == "acme-svc"
        assert item.scim_roles == ["api:read"]
        assert item.gateway_roles == []

    def test_drift_type_values(self):
        assert DriftType.MISSING_IN_GATEWAY.value == "missing_in_gateway"
        assert DriftType.ORPHANED_IN_GATEWAY.value == "orphaned_in_gateway"
        assert DriftType.ROLE_MISMATCH.value == "role_mismatch"

    def test_reconciliation_action_values(self):
        assert ReconciliationAction.PROVISIONED.value == "provisioned"
        assert ReconciliationAction.DEPROVISIONED.value == "deprovisioned"
        assert ReconciliationAction.UPDATED_ROLES.value == "updated_roles"
        assert ReconciliationAction.SKIPPED.value == "skipped"
        assert ReconciliationAction.FAILED.value == "failed"

    def test_reconciliation_status_defaults(self):
        status = ReconciliationStatus(tenant_id="t1")
        assert status.in_sync is True
        assert status.drift_count == 0
        assert status.last_check is None
        assert status.last_sync is None
        assert status.last_error is None

    def test_reconciliation_action_result(self):
        result = ReconciliationActionResult(
            client_name="svc-1",
            action=ReconciliationAction.PROVISIONED,
            detail="Created with roles",
        )
        assert result.action == ReconciliationAction.PROVISIONED


# ---- Service Tests ----


class TestCheckDrift:
    @pytest.mark.asyncio
    async def test_in_sync_no_drift(self, db):
        """All SCIM clients have matching gateway consumers."""
        adapter = _make_gateway_adapter(apps=[{"name": "t1-svc-a"}, {"name": "t1-svc-b"}])
        service = ReconciliationService(db=db, gateway_adapter=adapter)
        service.repo = AsyncMock()
        service.repo.list_by_tenant.return_value = [
            _make_client("1", "t1-svc-a", "t1", ["api:read"]),
            _make_client("2", "t1-svc-b", "t1", ["api:write"]),
        ]

        report = await service.check_drift("t1")
        assert report.in_sync is True
        assert len(report.drift_items) == 0
        assert report.total_scim_clients == 2
        assert report.total_gateway_consumers == 2

    @pytest.mark.asyncio
    async def test_missing_in_gateway(self, db):
        """SCIM client not provisioned in gateway."""
        adapter = _make_gateway_adapter(apps=[])
        service = ReconciliationService(db=db, gateway_adapter=adapter)
        service.repo = AsyncMock()
        service.repo.list_by_tenant.return_value = [
            _make_client("1", "t1-svc-a", "t1", ["api:read"]),
        ]

        report = await service.check_drift("t1")
        assert report.in_sync is False
        assert len(report.drift_items) == 1
        assert report.drift_items[0].drift_type == DriftType.MISSING_IN_GATEWAY
        assert report.drift_items[0].client_name == "t1-svc-a"

    @pytest.mark.asyncio
    async def test_orphaned_in_gateway(self, db):
        """Gateway consumer has no matching SCIM client."""
        adapter = _make_gateway_adapter(apps=[{"name": "orphan-svc", "roles": ["stale"]}])
        service = ReconciliationService(db=db, gateway_adapter=adapter)
        service.repo = AsyncMock()
        service.repo.list_by_tenant.return_value = []

        report = await service.check_drift("t1")
        assert report.in_sync is False
        assert len(report.drift_items) == 1
        assert report.drift_items[0].drift_type == DriftType.ORPHANED_IN_GATEWAY
        assert report.drift_items[0].gateway_roles == ["stale"]

    @pytest.mark.asyncio
    async def test_mixed_drift(self, db):
        """Both missing and orphaned consumers."""
        adapter = _make_gateway_adapter(apps=[{"name": "orphan-svc"}])
        service = ReconciliationService(db=db, gateway_adapter=adapter)
        service.repo = AsyncMock()
        service.repo.list_by_tenant.return_value = [
            _make_client("1", "missing-svc", "t1"),
        ]

        report = await service.check_drift("t1")
        assert not report.in_sync
        assert len(report.drift_items) == 2
        types = {i.drift_type for i in report.drift_items}
        assert types == {DriftType.MISSING_IN_GATEWAY, DriftType.ORPHANED_IN_GATEWAY}

    @pytest.mark.asyncio
    async def test_no_gateway_adapter(self, db):
        """Without gateway adapter, only SCIM clients are counted."""
        service = ReconciliationService(db=db, gateway_adapter=None)
        service.repo = AsyncMock()
        service.repo.list_by_tenant.return_value = [
            _make_client("1", "svc-a", "t1"),
        ]

        report = await service.check_drift("t1")
        assert report.total_gateway_consumers == 0
        assert len(report.drift_items) == 1

    @pytest.mark.asyncio
    async def test_revoked_clients_excluded(self, db):
        """Revoked clients should not appear in drift report."""
        adapter = _make_gateway_adapter(apps=[])
        service = ReconciliationService(db=db, gateway_adapter=adapter)
        service.repo = AsyncMock()
        service.repo.list_by_tenant.return_value = [
            _make_client("1", "revoked-svc", "t1", status="revoked"),
        ]

        report = await service.check_drift("t1")
        assert report.in_sync is True
        assert report.total_scim_clients == 0

    @pytest.mark.asyncio
    async def test_updates_last_check(self, db):
        """check_drift updates internal status tracking."""
        adapter = _make_gateway_adapter(apps=[])
        service = ReconciliationService(db=db, gateway_adapter=adapter)
        service.repo = AsyncMock()
        service.repo.list_by_tenant.return_value = []

        await service.check_drift("t1")
        status = await service.get_status("t1")
        assert status.last_check is not None


class TestReconcile:
    @pytest.mark.asyncio
    async def test_provisions_missing(self, db):
        """Reconcile provisions clients missing from gateway."""
        adapter = _make_gateway_adapter(apps=[])
        service = ReconciliationService(db=db, gateway_adapter=adapter)
        service.repo = AsyncMock()
        service.repo.list_by_tenant.return_value = [
            _make_client("1", "svc-a", "t1", ["api:read"]),
        ]

        result = await service.reconcile("t1")
        assert result.success is True
        assert result.actions_taken == 1
        assert result.results[0].action == ReconciliationAction.PROVISIONED
        adapter.provision_application.assert_called_once()

    @pytest.mark.asyncio
    async def test_deprovisions_orphaned(self, db):
        """Reconcile removes orphaned gateway consumers."""
        adapter = _make_gateway_adapter(apps=[{"name": "orphan"}])
        service = ReconciliationService(db=db, gateway_adapter=adapter)
        service.repo = AsyncMock()
        service.repo.list_by_tenant.return_value = []

        result = await service.reconcile("t1")
        assert result.success is True
        assert result.results[0].action == ReconciliationAction.DEPROVISIONED
        adapter.deprovision_application.assert_called_once()

    @pytest.mark.asyncio
    async def test_provision_failure(self, db):
        """Failed provisioning reported correctly."""
        adapter = _make_gateway_adapter(apps=[], provision_ok=False)
        service = ReconciliationService(db=db, gateway_adapter=adapter)
        service.repo = AsyncMock()
        service.repo.list_by_tenant.return_value = [
            _make_client("1", "svc-a", "t1"),
        ]

        result = await service.reconcile("t1")
        assert result.success is False
        assert result.actions_failed == 1
        assert result.results[0].action == ReconciliationAction.FAILED

    @pytest.mark.asyncio
    async def test_no_drift_no_actions(self, db):
        """When in sync, reconcile takes no actions."""
        adapter = _make_gateway_adapter(apps=[{"name": "svc-a"}])
        service = ReconciliationService(db=db, gateway_adapter=adapter)
        service.repo = AsyncMock()
        service.repo.list_by_tenant.return_value = [
            _make_client("1", "svc-a", "t1"),
        ]

        result = await service.reconcile("t1")
        assert result.success is True
        assert result.actions_taken == 0
        assert len(result.results) == 0

    @pytest.mark.asyncio
    async def test_reconcile_updates_status(self, db):
        """After reconcile, status reflects the sync."""
        adapter = _make_gateway_adapter(apps=[{"name": "svc-a"}])
        service = ReconciliationService(db=db, gateway_adapter=adapter)
        service.repo = AsyncMock()
        service.repo.list_by_tenant.return_value = [
            _make_client("1", "svc-a", "t1"),
        ]

        await service.reconcile("t1")
        status = await service.get_status("t1")
        assert status.last_sync is not None
        assert status.in_sync is True

    @pytest.mark.asyncio
    async def test_reconcile_without_gateway(self, db):
        """Without adapter, actions are skipped."""
        service = ReconciliationService(db=db, gateway_adapter=None)
        service.repo = AsyncMock()
        service.repo.list_by_tenant.return_value = [
            _make_client("1", "svc-a", "t1"),
        ]

        result = await service.reconcile("t1")
        assert result.success is True
        assert result.results[0].action == ReconciliationAction.SKIPPED

    @pytest.mark.asyncio
    async def test_provision_exception_handled(self, db):
        """Gateway adapter exception is caught and reported."""
        adapter = AsyncMock()
        adapter.list_applications.return_value = AdapterResult(success=True, data={"applications": []})
        adapter.provision_application.side_effect = ConnectionError("gateway down")
        service = ReconciliationService(db=db, gateway_adapter=adapter)
        service.repo = AsyncMock()
        service.repo.list_by_tenant.return_value = [
            _make_client("1", "svc-a", "t1"),
        ]

        result = await service.reconcile("t1")
        assert result.success is False
        assert "gateway down" in result.results[0].detail


class TestGetStatus:
    @pytest.mark.asyncio
    async def test_default_status(self, db):
        """Fresh service returns default status."""
        service = ReconciliationService(db=db)
        status = await service.get_status("t1")
        assert status.tenant_id == "t1"
        assert status.in_sync is True
        assert status.drift_count == 0

    @pytest.mark.asyncio
    async def test_status_after_drift_detected(self, db):
        """Status reflects drift after check."""
        adapter = _make_gateway_adapter(apps=[])
        service = ReconciliationService(db=db, gateway_adapter=adapter)
        service.repo = AsyncMock()
        service.repo.list_by_tenant.return_value = [
            _make_client("1", "svc-a", "t1"),
        ]

        await service.check_drift("t1")
        status = await service.get_status("t1")
        assert status.in_sync is False
        assert status.drift_count == 1

    @pytest.mark.asyncio
    async def test_status_after_failed_reconcile(self, db):
        """Status reflects error after failed reconcile."""
        adapter = _make_gateway_adapter(apps=[], provision_ok=False)
        service = ReconciliationService(db=db, gateway_adapter=adapter)
        service.repo = AsyncMock()
        service.repo.list_by_tenant.return_value = [
            _make_client("1", "svc-a", "t1"),
        ]

        await service.reconcile("t1")
        status = await service.get_status("t1")
        assert status.last_error is not None
        assert "failed" in status.last_error
