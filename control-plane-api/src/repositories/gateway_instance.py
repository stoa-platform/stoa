"""Repository for gateway instance CRUD operations."""

from datetime import UTC, datetime
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

    async def get_by_id(self, instance_id: UUID, *, include_deleted: bool = False) -> GatewayInstance | None:
        """Get gateway instance by ID."""
        query = select(GatewayInstance).where(GatewayInstance.id == instance_id)
        if not include_deleted:
            query = query.where(GatewayInstance.deleted_at.is_(None))
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> GatewayInstance | None:
        """Get gateway instance by unique name."""
        result = await self.session.execute(
            select(GatewayInstance).where(
                GatewayInstance.name == name,
                GatewayInstance.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_self_registered_by_hostname(self, hostname: str) -> GatewayInstance | None:
        """Get the latest self-registered gateway by original registration hostname.

        stoa-connect sends ``STOA_INSTANCE_NAME`` as the registration hostname,
        while the Control Plane stores the canonical instance name as
        ``{hostname}-{mode}-{environment}``. Route polling clients still filter
        by their configured hostname, so route delivery must support both forms.
        """
        result = await self.session.execute(
            select(GatewayInstance)
            .where(
                GatewayInstance.source == "self_register",
                GatewayInstance.health_details["hostname"].as_string() == hostname,
                GatewayInstance.deleted_at.is_(None),
            )
            .order_by(GatewayInstance.updated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_name_including_deleted(self, name: str) -> GatewayInstance | None:
        """Get gateway instance by name, including soft-deleted entries."""
        result = await self.session.execute(
            select(GatewayInstance).where(GatewayInstance.name == name)
        )
        return result.scalar_one_or_none()

    async def get_by_source_and_type(
        self,
        source: str,
        gateway_type: GatewayType,
        environment: str | None = None,
    ) -> GatewayInstance | None:
        """Find a gateway instance by source + type + optional environment.

        Used to find ArgoCD-created entries that a self-registering gateway should adopt
        instead of creating a duplicate.
        """
        query = select(GatewayInstance).where(
            GatewayInstance.source == source,
            GatewayInstance.gateway_type == gateway_type,
            GatewayInstance.deleted_at.is_(None),
        )
        if environment:
            query = query.where(GatewayInstance.environment == environment)
        # Prefer the most recently updated entry
        query = query.order_by(GatewayInstance.updated_at.desc()).limit(1)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_all(
        self,
        gateway_type: GatewayType | None = None,
        environment: str | None = None,
        tenant_id: str | None = None,
        include_deleted: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[GatewayInstance], int]:
        """List gateway instances with optional filters and pagination."""
        query = select(GatewayInstance)

        if not include_deleted:
            query = query.where(GatewayInstance.deleted_at.is_(None))

        if gateway_type:
            query = query.where(GatewayInstance.gateway_type == gateway_type)
        if environment:
            query = query.where(GatewayInstance.environment == environment)
        if tenant_id:
            query = query.where((GatewayInstance.tenant_id == tenant_id) | (GatewayInstance.tenant_id.is_(None)))

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
        instance.status = status
        instance.last_health_check = datetime.now(UTC)
        if health_details is not None:
            instance.health_details = health_details
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def find_self_registered_by_mode_env(
        self,
        mode: str,
        environment: str,
        exclude_name: str | None = None,
        target_gateway_type: str | None = None,
    ) -> list[GatewayInstance]:
        """Find all self-registered gateways with the same runtime mode + environment.

        Used by the cancel-and-replace logic: when a gateway re-registers with
        a new hostname (e.g. after container recreation), find the stale entries
        to soft-delete so the Console doesn't show duplicates.
        """
        query = select(GatewayInstance).where(
            GatewayInstance.mode == mode,
            GatewayInstance.environment == environment,
            GatewayInstance.source == "self_register",
            GatewayInstance.deleted_at.is_(None),
        )
        if exclude_name:
            query = query.where(GatewayInstance.name != exclude_name)
        if target_gateway_type:
            query = query.where(GatewayInstance.target_gateway_type == target_gateway_type)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def soft_delete(self, instance: GatewayInstance, deleted_by: str) -> GatewayInstance:
        """Soft-delete a gateway instance (set deleted_at + deleted_by)."""
        instance.deleted_at = datetime.now(UTC)
        instance.deleted_by = deleted_by
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def restore(self, instance: GatewayInstance) -> GatewayInstance:
        """Restore a soft-deleted gateway instance."""
        instance.deleted_at = None
        instance.deleted_by = None
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, instance: GatewayInstance) -> None:
        """Hard-delete a gateway instance (kept for internal use only)."""
        await self.session.delete(instance)
        await self.session.flush()
