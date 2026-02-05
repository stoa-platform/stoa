"""Gateway import service — reverse sync from gateway to STOA catalog.

Connects to a registered gateway via its adapter, discovers deployed APIs,
and creates APICatalog + GatewayDeployment records for APIs not already in
the catalog. Supports both dry-run preview and full import.
"""
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.registry import AdapterRegistry
from src.models.catalog import APICatalog
from src.models.gateway_deployment import DeploymentSyncStatus, GatewayDeployment
from src.repositories.gateway_deployment import GatewayDeploymentRepository
from src.repositories.gateway_instance import GatewayInstanceRepository

logger = logging.getLogger(__name__)


@dataclass
class ImportPreview:
    """Preview of a single API to be imported."""

    api_id: str
    api_name: str
    tenant_id: str
    gateway_resource_id: str
    action: str  # "create" or "skip"
    reason: str  # e.g. "New API — will be imported", "Already in catalog"


@dataclass
class ImportResult:
    """Result of a gateway import operation."""

    created: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    details: list[ImportPreview] = field(default_factory=list)


class GatewayImportService:
    """Import APIs from a gateway into the STOA catalog."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.gw_repo = GatewayInstanceRepository(db)
        self.deploy_repo = GatewayDeploymentRepository(db)

    async def preview_import(self, gateway_instance_id: UUID) -> list[ImportPreview]:
        """Dry-run: show what would be imported without creating anything."""
        gateway = await self.gw_repo.get_by_id(gateway_instance_id)
        if not gateway:
            raise ValueError("Gateway instance not found")

        adapter = AdapterRegistry.create(
            gateway.gateway_type.value,
            config={"base_url": gateway.base_url, "auth_config": gateway.auth_config},
        )
        await adapter.connect()
        try:
            remote_apis = await adapter.list_apis()
        finally:
            await adapter.disconnect()

        previews = []
        for api_data in remote_apis:
            api_name = api_data.get("name", api_data.get("id", ""))
            tenant_id = api_data.get("tenant_id", gateway.tenant_id or "imported")
            api_id = api_data.get("id", api_name)
            resource_id = api_data.get("id", "")

            existing = await self._find_catalog_entry(tenant_id, api_id)
            if existing:
                previews.append(ImportPreview(
                    api_id=api_id,
                    api_name=api_name,
                    tenant_id=tenant_id,
                    gateway_resource_id=resource_id,
                    action="skip",
                    reason="Already in catalog",
                ))
            else:
                previews.append(ImportPreview(
                    api_id=api_id,
                    api_name=api_name,
                    tenant_id=tenant_id,
                    gateway_resource_id=resource_id,
                    action="create",
                    reason="New API — will be imported",
                ))

        return previews

    async def import_from_gateway(self, gateway_instance_id: UUID) -> ImportResult:
        """Import APIs from a gateway into the catalog + create SYNCED deployments."""
        gateway = await self.gw_repo.get_by_id(gateway_instance_id)
        if not gateway:
            raise ValueError("Gateway instance not found")

        adapter = AdapterRegistry.create(
            gateway.gateway_type.value,
            config={"base_url": gateway.base_url, "auth_config": gateway.auth_config},
        )
        await adapter.connect()
        try:
            remote_apis = await adapter.list_apis()
        finally:
            await adapter.disconnect()

        result = ImportResult()
        now = datetime.now(UTC)

        for api_data in remote_apis:
            api_name = api_data.get("name", api_data.get("id", ""))
            tenant_id = api_data.get("tenant_id", gateway.tenant_id or "imported")
            api_id = api_data.get("id", api_name)
            resource_id = api_data.get("id", "")

            try:
                existing = await self._find_catalog_entry(tenant_id, api_id)
                if existing:
                    result.skipped += 1
                    result.details.append(ImportPreview(
                        api_id=api_id,
                        api_name=api_name,
                        tenant_id=tenant_id,
                        gateway_resource_id=resource_id,
                        action="skip",
                        reason="Already in catalog",
                    ))
                    continue

                # Create catalog entry
                catalog_entry = APICatalog(
                    tenant_id=tenant_id,
                    api_id=api_id,
                    api_name=api_name,
                    version=api_data.get("version"),
                    status="active",
                    api_metadata=api_data,
                    target_gateways=[gateway.name],
                    synced_at=now,
                )
                self.db.add(catalog_entry)
                await self.db.flush()

                # Create SYNCED deployment (already deployed on gateway)
                deployment = GatewayDeployment(
                    api_catalog_id=catalog_entry.id,
                    gateway_instance_id=gateway.id,
                    desired_state={
                        "spec_hash": api_data.get("spec_hash", ""),
                        "version": api_data.get("version"),
                        "api_name": api_name,
                        "api_id": api_id,
                        "tenant_id": tenant_id,
                        "activated": True,
                    },
                    desired_at=now,
                    actual_state=api_data,
                    actual_at=now,
                    sync_status=DeploymentSyncStatus.SYNCED,
                    gateway_resource_id=resource_id,
                    last_sync_success=now,
                )
                await self.deploy_repo.create(deployment)

                result.created += 1
                result.details.append(ImportPreview(
                    api_id=api_id,
                    api_name=api_name,
                    tenant_id=tenant_id,
                    gateway_resource_id=resource_id,
                    action="create",
                    reason="Imported",
                ))

            except Exception as e:
                logger.warning("Failed to import API %s/%s: %s", tenant_id, api_id, e)
                result.errors.append(f"{tenant_id}/{api_id}: {e}")

        await self.db.commit()
        logger.info(
            "Import from %s: %d created, %d skipped, %d errors",
            gateway.name,
            result.created,
            result.skipped,
            len(result.errors),
        )
        return result

    async def _find_catalog_entry(self, tenant_id: str, api_id: str):
        """Find existing catalog entry by tenant+api_id."""
        result = await self.db.execute(
            select(APICatalog).where(
                APICatalog.tenant_id == tenant_id,
                APICatalog.api_id == api_id,
                APICatalog.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()
