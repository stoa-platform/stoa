"""Service layer for gateway instance management."""

import contextlib
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.registry import AdapterRegistry
from src.models.gateway_instance import (
    GatewayInstance,
    GatewayInstanceStatus,
    GatewayType,
)
from src.repositories.gateway_instance import GatewayInstanceRepository
from src.schemas.gateway import GatewayInstanceCreate, GatewayInstanceUpdate

logger = logging.getLogger(__name__)


class GatewayInstanceService:
    """Business logic for gateway instance management."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = GatewayInstanceRepository(db)

    async def create(self, data: GatewayInstanceCreate) -> GatewayInstance:
        """Register a new gateway instance."""
        # Validate gateway type has a registered adapter
        if not AdapterRegistry.has_type(data.gateway_type):
            available = ", ".join(AdapterRegistry.list_types())
            raise ValueError(
                f"No adapter registered for gateway type '{data.gateway_type}'. " f"Available: {available}"
            )

        # Check unique name
        existing = await self.repo.get_by_name(data.name)
        if existing:
            raise ValueError(f"Gateway instance with name '{data.name}' already exists")

        instance = GatewayInstance(
            name=data.name,
            display_name=data.display_name,
            gateway_type=GatewayType(data.gateway_type),
            environment=data.environment,
            tenant_id=data.tenant_id,
            base_url=data.base_url,
            auth_config=data.auth_config,
            capabilities=data.capabilities,
            tags=data.tags,
            status=GatewayInstanceStatus.OFFLINE,
        )
        return await self.repo.create(instance)

    async def get_by_id(self, instance_id: UUID, *, include_deleted: bool = False) -> GatewayInstance | None:
        """Get gateway instance by ID."""
        return await self.repo.get_by_id(instance_id, include_deleted=include_deleted)

    async def list(
        self,
        gateway_type: str | None = None,
        environment: str | None = None,
        tenant_id: str | None = None,
        include_deleted: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[GatewayInstance], int]:
        """List gateway instances with optional filters."""
        gw_type = GatewayType(gateway_type) if gateway_type else None
        return await self.repo.list_all(
            gateway_type=gw_type,
            environment=environment,
            tenant_id=tenant_id,
            include_deleted=include_deleted,
            page=page,
            page_size=page_size,
        )

    async def update(self, instance_id: UUID, data: GatewayInstanceUpdate) -> GatewayInstance:
        """Update a gateway instance."""
        instance = await self.repo.get_by_id(instance_id)
        if not instance:
            raise ValueError(f"Gateway instance {instance_id} not found")

        if data.display_name is not None:
            instance.display_name = data.display_name
        if data.base_url is not None:
            instance.base_url = data.base_url
        if data.auth_config is not None:
            instance.auth_config = data.auth_config
        if data.capabilities is not None:
            instance.capabilities = data.capabilities
        if data.tags is not None:
            instance.tags = data.tags
        if data.environment is not None:
            instance.environment = data.environment
        if data.protected is not None:
            instance.protected = data.protected

        return await self.repo.update(instance)

    async def delete(self, instance_id: UUID, deleted_by: str) -> None:
        """Soft-delete a gateway instance. Rejects if protected."""
        instance = await self.repo.get_by_id(instance_id)
        if not instance:
            raise ValueError(f"Gateway instance {instance_id} not found")
        if instance.protected:
            raise PermissionError(
                f"Gateway '{instance.display_name}' is protected and cannot be deleted. "
                f"Remove protection first via PUT."
            )
        await self.repo.soft_delete(instance, deleted_by=deleted_by)

    async def restore(self, instance_id: UUID) -> GatewayInstance:
        """Restore a soft-deleted gateway instance."""
        instance = await self.repo.get_by_id(instance_id, include_deleted=True)
        if not instance:
            raise ValueError(f"Gateway instance {instance_id} not found")
        if instance.deleted_at is None:
            raise ValueError(f"Gateway instance {instance_id} is not deleted")
        return await self.repo.restore(instance)

    async def health_check(self, instance_id: UUID) -> dict:
        """Trigger a health check on a gateway instance via its adapter."""
        instance = await self.repo.get_by_id(instance_id)
        if not instance:
            raise ValueError(f"Gateway instance {instance_id} not found")

        from src.services.credential_resolver import create_adapter_with_credentials

        adapter = await create_adapter_with_credentials(
            instance.gateway_type.value, instance.base_url, instance.auth_config,
        )

        try:
            await adapter.connect()
            result = await adapter.health_check()

            new_status = GatewayInstanceStatus.ONLINE if result.success else GatewayInstanceStatus.DEGRADED
            details = result.data or {}
            if not result.success and result.error:
                details = {**details, "error": result.error}
            # Merge health check result into existing health_details to preserve
            # heartbeat data (discovered_apis, uptime_seconds, etc.)
            merged = {**(instance.health_details or {}), **details, "last_health_check_result": new_status.value}
            await self.repo.update_status(instance, status=new_status, health_details=merged)

            return {
                "status": new_status.value,
                "details": details,
                "gateway_name": instance.name,
                "gateway_type": instance.gateway_type.value,
            }
        except Exception as e:
            # Merge error into existing health_details instead of replacing
            merged = {**(instance.health_details or {}), "error": str(e), "last_health_check_result": "offline"}
            await self.repo.update_status(
                instance,
                status=GatewayInstanceStatus.DEGRADED,
                health_details=merged,
            )
            return {
                "status": "degraded",
                "details": {"error": str(e)},
                "gateway_name": instance.name,
                "gateway_type": instance.gateway_type.value,
            }
        finally:
            with contextlib.suppress(Exception):
                await adapter.disconnect()
