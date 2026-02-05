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
                f"No adapter registered for gateway type '{data.gateway_type}'. "
                f"Available: {available}"
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

    async def get_by_id(self, instance_id: UUID) -> GatewayInstance | None:
        """Get gateway instance by ID."""
        return await self.repo.get_by_id(instance_id)

    async def list(
        self,
        gateway_type: str | None = None,
        environment: str | None = None,
        tenant_id: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[GatewayInstance], int]:
        """List gateway instances with optional filters."""
        gw_type = GatewayType(gateway_type) if gateway_type else None
        return await self.repo.list_all(
            gateway_type=gw_type,
            environment=environment,
            tenant_id=tenant_id,
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

        return await self.repo.update(instance)

    async def delete(self, instance_id: UUID) -> None:
        """Deregister a gateway instance."""
        instance = await self.repo.get_by_id(instance_id)
        if not instance:
            raise ValueError(f"Gateway instance {instance_id} not found")
        await self.repo.delete(instance)

    async def health_check(self, instance_id: UUID) -> dict:
        """Trigger a health check on a gateway instance via its adapter."""
        instance = await self.repo.get_by_id(instance_id)
        if not instance:
            raise ValueError(f"Gateway instance {instance_id} not found")

        adapter = AdapterRegistry.create(
            instance.gateway_type.value,
            config={
                "base_url": instance.base_url,
                "auth_config": instance.auth_config,
            },
        )

        try:
            await adapter.connect()
            result = await adapter.health_check()

            new_status = GatewayInstanceStatus.ONLINE if result.success else GatewayInstanceStatus.DEGRADED
            await self.repo.update_status(
                instance, status=new_status, health_details=result.data
            )

            return {
                "status": new_status.value,
                "details": result.data,
                "gateway_name": instance.name,
                "gateway_type": instance.gateway_type.value,
            }
        except Exception as e:
            await self.repo.update_status(
                instance,
                status=GatewayInstanceStatus.OFFLINE,
                health_details={"error": str(e)},
            )
            return {
                "status": "offline",
                "details": {"error": str(e)},
                "gateway_name": instance.name,
                "gateway_type": instance.gateway_type.value,
            }
        finally:
            with contextlib.suppress(Exception):
                await adapter.disconnect()
