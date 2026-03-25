"""Repository for gateway deployment CRUD and sync operations."""
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.gateway_deployment import DeploymentSyncStatus, GatewayDeployment
from src.models.gateway_instance import GatewayInstance


class GatewayDeploymentRepository:
    """Repository for gateway deployment database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, deployment: GatewayDeployment) -> GatewayDeployment:
        """Create a new gateway deployment."""
        self.session.add(deployment)
        await self.session.flush()
        await self.session.refresh(deployment)
        return deployment

    async def get_by_id(self, deployment_id: UUID) -> GatewayDeployment | None:
        """Get deployment by ID."""
        result = await self.session.execute(
            select(GatewayDeployment).where(GatewayDeployment.id == deployment_id)
        )
        return result.scalar_one_or_none()

    async def get_by_api_and_gateway(
        self, api_catalog_id: UUID, gateway_instance_id: UUID
    ) -> GatewayDeployment | None:
        """Get deployment for a specific API + gateway combination."""
        result = await self.session.execute(
            select(GatewayDeployment).where(
                and_(
                    GatewayDeployment.api_catalog_id == api_catalog_id,
                    GatewayDeployment.gateway_instance_id == gateway_instance_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_by_api(self, api_catalog_id: UUID) -> list[GatewayDeployment]:
        """List all deployments for an API."""
        result = await self.session.execute(
            select(GatewayDeployment)
            .where(GatewayDeployment.api_catalog_id == api_catalog_id)
            .order_by(GatewayDeployment.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_by_gateway(
        self,
        gateway_instance_id: UUID,
        sync_status: DeploymentSyncStatus | None = None,
    ) -> list[GatewayDeployment]:
        """List all deployments for a gateway, optionally filtered by sync status."""
        query = select(GatewayDeployment).where(
            GatewayDeployment.gateway_instance_id == gateway_instance_id
        )
        if sync_status:
            query = query.where(GatewayDeployment.sync_status == sync_status)
        query = query.order_by(GatewayDeployment.created_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_all(
        self,
        sync_status: DeploymentSyncStatus | None = None,
        gateway_instance_id: UUID | None = None,
        environment: str | None = None,
        gateway_type: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[dict], int]:
        """List deployments with optional filters and pagination.

        Always joins GatewayInstance to include gateway name, type, and environment.
        Returns dicts (not ORM objects) with gateway info merged in.
        """
        # Always join GatewayInstance for name/type/environment
        query = (
            select(
                GatewayDeployment,
                GatewayInstance.name.label("gateway_name"),
                GatewayInstance.display_name.label("gateway_display_name"),
                GatewayInstance.gateway_type.label("gateway_type"),
                GatewayInstance.environment.label("gateway_environment"),
            )
            .join(
                GatewayInstance,
                GatewayDeployment.gateway_instance_id == GatewayInstance.id,
            )
        )

        if environment:
            query = query.where(GatewayInstance.environment == environment)
        if gateway_type:
            query = query.where(GatewayInstance.gateway_type == gateway_type)
        if sync_status:
            query = query.where(GatewayDeployment.sync_status == sync_status)
        if gateway_instance_id:
            query = query.where(GatewayDeployment.gateway_instance_id == gateway_instance_id)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        query = query.order_by(GatewayDeployment.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        rows = result.all()

        deployments = []
        for row in rows:
            dep = row.GatewayDeployment
            deployments.append({
                "id": dep.id,
                "api_catalog_id": dep.api_catalog_id,
                "gateway_instance_id": dep.gateway_instance_id,
                "desired_state": dep.desired_state,
                "desired_at": dep.desired_at,
                "actual_state": dep.actual_state,
                "actual_at": dep.actual_at,
                "sync_status": dep.sync_status.value if hasattr(dep.sync_status, "value") else dep.sync_status,
                "last_sync_attempt": dep.last_sync_attempt,
                "last_sync_success": dep.last_sync_success,
                "sync_error": dep.sync_error,
                "sync_attempts": dep.sync_attempts,
                "gateway_resource_id": dep.gateway_resource_id,
                "created_at": dep.created_at,
                "updated_at": dep.updated_at,
                "gateway_name": row.gateway_name,
                "gateway_display_name": row.gateway_display_name,
                "gateway_type": row.gateway_type.value if hasattr(row.gateway_type, "value") else row.gateway_type,
                "gateway_environment": row.gateway_environment,
            })
        return deployments, total

    async def list_by_statuses(self, statuses: list[DeploymentSyncStatus]) -> list[GatewayDeployment]:
        """List deployments matching any of the given statuses."""
        result = await self.session.execute(
            select(GatewayDeployment).where(
                GatewayDeployment.sync_status.in_(statuses)
            )
        )
        return list(result.scalars().all())

    async def list_pending_sync(self) -> list[GatewayDeployment]:
        """List deployments needing sync (pending, drifted, or error with retries)."""
        result = await self.session.execute(
            select(GatewayDeployment).where(
                GatewayDeployment.sync_status.in_([
                    DeploymentSyncStatus.PENDING,
                    DeploymentSyncStatus.DRIFTED,
                    DeploymentSyncStatus.DELETING,
                ])
            )
        )
        return list(result.scalars().all())

    async def list_synced(self) -> list[GatewayDeployment]:
        """List all synced deployments (for drift detection)."""
        result = await self.session.execute(
            select(GatewayDeployment).where(
                GatewayDeployment.sync_status == DeploymentSyncStatus.SYNCED
            )
        )
        return list(result.scalars().all())

    async def get_status_summary(self) -> dict:
        """Get sync status counts for the dashboard."""
        counts = {}
        for status in DeploymentSyncStatus:
            count_query = select(func.count()).where(
                GatewayDeployment.sync_status == status
            )
            result = await self.session.execute(count_query)
            counts[status.value] = result.scalar_one()
        return counts

    async def update(self, deployment: GatewayDeployment) -> GatewayDeployment:
        """Update a deployment (caller modifies fields before calling)."""
        await self.session.flush()
        await self.session.refresh(deployment)
        return deployment

    async def delete(self, deployment: GatewayDeployment) -> None:
        """Delete a deployment."""
        await self.session.delete(deployment)
        await self.session.flush()

    async def get_primary_for_api(
        self, api_id: str, tenant_id: str
    ) -> GatewayDeployment | None:
        """Get the first synced deployment for an API (for provisioning service).

        Looks up the API catalog entry by api_id + tenant_id, then finds
        the first SYNCED deployment for that catalog entry.
        """
        from src.models.catalog import APICatalog

        result = await self.session.execute(
            select(GatewayDeployment)
            .join(APICatalog, GatewayDeployment.api_catalog_id == APICatalog.id)
            .where(
                and_(
                    APICatalog.api_id == api_id,
                    APICatalog.tenant_id == tenant_id,
                    GatewayDeployment.sync_status == DeploymentSyncStatus.SYNCED,
                )
            )
            .limit(1)
        )
        return result.scalar_one_or_none()
