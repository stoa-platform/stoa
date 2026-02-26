"""SCIM↔Gateway Reconciliation service (CAB-1484).

Compares SCIM-provisioned OAuth clients with gateway consumer registrations.
Detects drift and provides automated reconciliation (sync SCIM→Gateway).
"""

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters.gateway_adapter_interface import AdapterResult
from ..models.oauth_client import OAuthClientStatus
from ..repositories.oauth_client import OAuthClientRepository
from ..schemas.reconciliation import (
    DriftItem,
    DriftReport,
    DriftType,
    ReconciliationAction,
    ReconciliationActionResult,
    ReconciliationResult,
    ReconciliationStatus,
)

logger = logging.getLogger(__name__)


class ReconciliationService:
    """Detects and resolves drift between SCIM clients and gateway consumers."""

    def __init__(self, db: AsyncSession, gateway_adapter=None):
        self.db = db
        self.repo = OAuthClientRepository(db)
        self.gateway = gateway_adapter
        self._last_check: dict[str, datetime] = {}
        self._last_sync: dict[str, datetime] = {}
        self._last_error: dict[str, str] = {}
        self._drift_counts: dict[str, int] = {}

    async def check_drift(self, tenant_id: str) -> DriftReport:
        """Compare SCIM clients with gateway consumers and report drift.

        Returns a DriftReport with all discrepancies found.
        """
        now = datetime.now(UTC)
        drift_items: list[DriftItem] = []

        # Get all active SCIM clients for tenant
        scim_clients = await self.repo.list_by_tenant(tenant_id)
        active_clients = [c for c in scim_clients if c.status == OAuthClientStatus.ACTIVE.value]

        # Get gateway consumers
        gateway_consumers: dict[str, dict] = {}
        if self.gateway:
            result: AdapterResult = await self.gateway.list_applications(tenant_id)
            if result.success and result.data:
                for app in result.data.get("applications", []):
                    app_name = app.get("name", "")
                    gateway_consumers[app_name] = app

        # Check for clients missing in gateway
        for client in active_clients:
            if client.keycloak_client_id not in gateway_consumers:
                drift_items.append(
                    DriftItem(
                        drift_type=DriftType.MISSING_IN_GATEWAY,
                        client_id=client.id,
                        client_name=client.keycloak_client_id,
                        detail="Client exists in SCIM but not provisioned in gateway",
                        scim_roles=client.product_roles or [],
                        gateway_roles=[],
                    )
                )

        # Check for orphaned gateway consumers (in gateway but not in SCIM)
        scim_client_ids = {c.keycloak_client_id for c in active_clients}
        for gw_name, gw_app in gateway_consumers.items():
            if gw_name not in scim_client_ids:
                drift_items.append(
                    DriftItem(
                        drift_type=DriftType.ORPHANED_IN_GATEWAY,
                        client_name=gw_name,
                        detail="Consumer exists in gateway but not in SCIM",
                        scim_roles=[],
                        gateway_roles=gw_app.get("roles", []),
                    )
                )

        in_sync = len(drift_items) == 0
        self._last_check[tenant_id] = now
        self._drift_counts[tenant_id] = len(drift_items)

        return DriftReport(
            tenant_id=tenant_id,
            checked_at=now,
            in_sync=in_sync,
            total_scim_clients=len(active_clients),
            total_gateway_consumers=len(gateway_consumers),
            drift_items=drift_items,
        )

    async def reconcile(self, tenant_id: str) -> ReconciliationResult:
        """Sync SCIM state to gateway — provision missing, deprovision orphaned."""
        started_at = datetime.now(UTC)
        results: list[ReconciliationActionResult] = []
        actions_failed = 0

        # First check drift
        drift = await self.check_drift(tenant_id)

        for item in drift.drift_items:
            if item.drift_type == DriftType.MISSING_IN_GATEWAY:
                result = await self._provision_consumer(tenant_id, item)
            elif item.drift_type == DriftType.ORPHANED_IN_GATEWAY:
                result = await self._deprovision_consumer(tenant_id, item)
            elif item.drift_type == DriftType.ROLE_MISMATCH:
                result = await self._update_consumer_roles(tenant_id, item)
            else:
                result = ReconciliationActionResult(
                    client_name=item.client_name,
                    action=ReconciliationAction.SKIPPED,
                    detail=f"Unknown drift type: {item.drift_type}",
                )

            if result.action == ReconciliationAction.FAILED:
                actions_failed += 1
            results.append(result)

        completed_at = datetime.now(UTC)
        success = actions_failed == 0

        self._last_sync[tenant_id] = completed_at
        if not success:
            self._last_error[tenant_id] = f"{actions_failed} action(s) failed"
        else:
            self._last_error.pop(tenant_id, None)
        self._drift_counts[tenant_id] = 0 if success else actions_failed

        return ReconciliationResult(
            tenant_id=tenant_id,
            started_at=started_at,
            completed_at=completed_at,
            success=success,
            actions_taken=len(results) - actions_failed,
            actions_failed=actions_failed,
            results=results,
        )

    async def get_status(self, tenant_id: str) -> ReconciliationStatus:
        """Return the current reconciliation status for a tenant."""
        return ReconciliationStatus(
            tenant_id=tenant_id,
            last_check=self._last_check.get(tenant_id),
            last_sync=self._last_sync.get(tenant_id),
            in_sync=self._drift_counts.get(tenant_id, 0) == 0,
            drift_count=self._drift_counts.get(tenant_id, 0),
            last_error=self._last_error.get(tenant_id),
        )

    async def _provision_consumer(self, tenant_id: str, item: DriftItem) -> ReconciliationActionResult:
        """Provision a missing consumer in the gateway."""
        if not self.gateway:
            return ReconciliationActionResult(
                client_name=item.client_name,
                action=ReconciliationAction.SKIPPED,
                detail="No gateway adapter configured",
            )

        try:
            spec = {
                "name": item.client_name,
                "tenant_id": tenant_id,
                "roles": item.scim_roles,
            }
            result = await self.gateway.provision_application(tenant_id, spec)
            if result.success:
                logger.info(f"Provisioned consumer {item.client_name} in gateway for tenant {tenant_id}")
                return ReconciliationActionResult(
                    client_name=item.client_name,
                    action=ReconciliationAction.PROVISIONED,
                    detail=f"Provisioned with roles: {', '.join(item.scim_roles)}",
                )
            return ReconciliationActionResult(
                client_name=item.client_name,
                action=ReconciliationAction.FAILED,
                detail=f"Gateway provisioning failed: {result.error}",
            )
        except Exception as e:
            logger.error(f"Failed to provision {item.client_name}: {e}")
            return ReconciliationActionResult(
                client_name=item.client_name,
                action=ReconciliationAction.FAILED,
                detail=str(e),
            )

    async def _deprovision_consumer(self, tenant_id: str, item: DriftItem) -> ReconciliationActionResult:
        """Remove an orphaned consumer from the gateway."""
        if not self.gateway:
            return ReconciliationActionResult(
                client_name=item.client_name,
                action=ReconciliationAction.SKIPPED,
                detail="No gateway adapter configured",
            )

        try:
            result = await self.gateway.deprovision_application(tenant_id, item.client_name)
            if result.success:
                logger.info(f"Deprovisioned orphaned consumer {item.client_name} from gateway")
                return ReconciliationActionResult(
                    client_name=item.client_name,
                    action=ReconciliationAction.DEPROVISIONED,
                    detail="Removed orphaned consumer from gateway",
                )
            return ReconciliationActionResult(
                client_name=item.client_name,
                action=ReconciliationAction.FAILED,
                detail=f"Gateway deprovisioning failed: {result.error}",
            )
        except Exception as e:
            logger.error(f"Failed to deprovision {item.client_name}: {e}")
            return ReconciliationActionResult(
                client_name=item.client_name,
                action=ReconciliationAction.FAILED,
                detail=str(e),
            )

    async def _update_consumer_roles(self, tenant_id: str, item: DriftItem) -> ReconciliationActionResult:
        """Update consumer roles in the gateway to match SCIM."""
        if not self.gateway:
            return ReconciliationActionResult(
                client_name=item.client_name,
                action=ReconciliationAction.SKIPPED,
                detail="No gateway adapter configured",
            )

        try:
            spec = {
                "name": item.client_name,
                "tenant_id": tenant_id,
                "roles": item.scim_roles,
            }
            result = await self.gateway.provision_application(tenant_id, spec)
            if result.success:
                logger.info(f"Updated roles for {item.client_name} in gateway")
                return ReconciliationActionResult(
                    client_name=item.client_name,
                    action=ReconciliationAction.UPDATED_ROLES,
                    detail=f"Updated roles: {', '.join(item.scim_roles)}",
                )
            return ReconciliationActionResult(
                client_name=item.client_name,
                action=ReconciliationAction.FAILED,
                detail=f"Gateway role update failed: {result.error}",
            )
        except Exception as e:
            logger.error(f"Failed to update roles for {item.client_name}: {e}")
            return ReconciliationActionResult(
                client_name=item.client_name,
                action=ReconciliationAction.FAILED,
                detail=str(e),
            )
