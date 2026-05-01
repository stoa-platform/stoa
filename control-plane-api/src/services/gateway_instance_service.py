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
from src.services.gateway_topology import normalize_gateway_topology

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

        topology = normalize_gateway_topology(
            gateway_type=data.gateway_type,
            mode=None,
            source="manual",
            deployment_mode=data.deployment_mode,
            target_gateway_type=data.target_gateway_type,
            topology=data.topology,
            endpoints=data.endpoints,
            base_url=data.base_url,
            public_url=data.public_url,
            ui_url=data.ui_url,
            target_gateway_url=data.target_gateway_url,
            tags=data.tags,
            name=data.name,
        )

        instance = GatewayInstance(
            name=data.name,
            display_name=data.display_name,
            gateway_type=GatewayType(data.gateway_type),
            environment=data.environment,
            tenant_id=data.tenant_id,
            base_url=data.base_url,
            target_gateway_url=data.target_gateway_url,
            public_url=data.public_url,
            ui_url=data.ui_url,
            endpoints=topology.endpoints,
            deployment_mode=topology.deployment_mode,
            target_gateway_type=topology.target_gateway_type,
            topology=topology.topology,
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

    async def update(
        self, instance_id: UUID, data: GatewayInstanceUpdate, *, user_id: str | None = None
    ) -> GatewayInstance:
        """Update a gateway instance. Tracks enable/disable changes for audit."""
        instance = await self.repo.get_by_id(instance_id)
        if not instance:
            raise ValueError(f"Gateway instance {instance_id} not found")

        if data.display_name is not None:
            instance.display_name = data.display_name
        if data.base_url is not None:
            instance.base_url = data.base_url
        if data.target_gateway_url is not None:
            instance.target_gateway_url = data.target_gateway_url
        if data.public_url is not None:
            instance.public_url = data.public_url
        if data.ui_url is not None:
            instance.ui_url = data.ui_url
        if data.endpoints is not None:
            instance.endpoints = data.endpoints
        if data.deployment_mode is not None:
            instance.deployment_mode = data.deployment_mode
        if data.target_gateway_type is not None:
            instance.target_gateway_type = data.target_gateway_type
        if data.topology is not None:
            instance.topology = data.topology
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
        if data.enabled is not None:
            old_enabled = instance.enabled
            instance.enabled = data.enabled
            if old_enabled != data.enabled:
                action = "enabled" if data.enabled else "disabled"
                logger.info(
                    "Gateway %s %s by %s (was %s)",
                    instance.name,
                    action,
                    user_id or "unknown",
                    "enabled" if old_enabled else "disabled",
                )
        if data.visibility is not None:
            instance.visibility = data.visibility

        normalized = normalize_gateway_topology(
            gateway_type=instance.gateway_type,
            mode=instance.mode,
            source=instance.source,
            deployment_mode=instance.deployment_mode,
            target_gateway_type=instance.target_gateway_type,
            topology=instance.topology,
            health_details=instance.health_details,
            endpoints=instance.endpoints,
            base_url=instance.base_url,
            public_url=instance.public_url,
            ui_url=instance.ui_url,
            target_gateway_url=instance.target_gateway_url,
            tags=instance.tags,
            name=instance.name,
        )
        instance.deployment_mode = normalized.deployment_mode
        instance.target_gateway_type = normalized.target_gateway_type
        instance.topology = normalized.topology
        instance.endpoints = normalized.endpoints

        return await self.repo.update(instance)

    async def assert_enabled(self, instance_id: UUID) -> GatewayInstance:
        """Return the gateway if it exists and is enabled, else raise."""
        instance = await self.repo.get_by_id(instance_id)
        if not instance:
            raise ValueError(f"Gateway instance {instance_id} not found")
        if not instance.enabled:
            raise PermissionError(
                f"Gateway '{instance.name}' is disabled. "
                f"Enable it via PUT /v1/admin/gateways/{instance_id} before deploying."
            )
        return instance

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

        from src.services.credential_resolver import (
            _PULL_MODEL_GATEWAY_TYPES,
            AGENT_MANAGED_MESSAGE,
            create_adapter_with_credentials,
        )

        gw_type = instance.gateway_type.value if hasattr(instance.gateway_type, "value") else str(instance.gateway_type)
        if instance.source == "self_register" and gw_type in _PULL_MODEL_GATEWAY_TYPES:
            return {
                "status": instance.status.value if instance.status else "unknown",
                "details": {"info": AGENT_MANAGED_MESSAGE},
                "gateway_name": instance.name,
                "gateway_type": gw_type,
            }

        adapter = await create_adapter_with_credentials(
            instance.gateway_type.value,
            instance.base_url,
            instance.auth_config,
        )

        try:
            await adapter.connect()
            result = await adapter.health_check()

            new_status = GatewayInstanceStatus.ONLINE if result.success else GatewayInstanceStatus.DEGRADED
            details = result.data or {}
            if not result.success and result.error:
                details = {**details, "error": result.error}
            # Merge into existing health_details to preserve heartbeat data
            merged = {**(instance.health_details or {}), **details, "last_health_check_result": new_status.value}
            await self.repo.update_status(instance, status=new_status, health_details=merged)

            return {
                "status": new_status.value,
                "details": details,
                "gateway_name": instance.name,
                "gateway_type": instance.gateway_type.value,
            }
        except Exception as e:
            # Merge error into existing health_details to preserve heartbeat data
            merged = {
                **(instance.health_details or {}),
                "error": str(e),
                "last_health_check_result": "error",
            }
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
