"""Repository for gateway instance CRUD operations."""
from datetime import UTC
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.gateway_instance import GatewayInstance, GatewayInstanceStatus, GatewayType


class GatewayInstanceRepository:
    """Repository for gateway instance database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, instance: GatewayInstance) -> GatewayInstance:
        """Create a new gateway instance."""
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def get_by_id(self, instance_id: UUID) -> GatewayInstance | None:
        """Get gateway instance by ID."""
        result = await self.session.execute(
            select(GatewayInstance).where(GatewayInstance.id == instance_id)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> GatewayInstance | None:
        """Get gateway instance by unique name."""
        result = await self.session.execute(
            select(GatewayInstance).where(GatewayInstance.name == name)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        gateway_type: GatewayType | None = None,
        environment: str | None = None,
        tenant_id: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[GatewayInstance], int]:
        """List gateway instances with optional filters and pagination."""
        query = select(GatewayInstance)

        if gateway_type:
            query = query.where(GatewayInstance.gateway_type == gateway_type)
        if environment:
            query = query.where(GatewayInstance.environment == environment)
        if tenant_id:
            query = query.where(
                (GatewayInstance.tenant_id == tenant_id) | (GatewayInstance.tenant_id.is_(None))
            )

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        # Paginate
        query = query.order_by(GatewayInstance.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        instances = result.scalars().all()

        return list(instances), total

    async def update(self, instance: GatewayInstance) -> GatewayInstance:
        """Update a gateway instance (caller modifies fields before calling)."""
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update_status(
        self,
        instance: GatewayInstance,
        status: GatewayInstanceStatus,
        health_details: dict | None = None,
    ) -> GatewayInstance:
        """Update gateway health status."""
        from datetime import datetime

        instance.status = status
        instance.last_health_check = datetime.now(UTC)
        if health_details is not None:
            instance.health_details = health_details
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, instance: GatewayInstance) -> None:
        """Delete a gateway instance."""
        await self.session.delete(instance)
        await self.session.flush()
