"""Repository for gateway deployment CRUD and sync operations."""

from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.catalog import APICatalog
from src.models.gateway_deployment import DeploymentSyncStatus, GatewayDeployment
from src.models.gateway_instance import GatewayInstance
from src.models.promotion import Promotion


def _wire_value(value: object) -> object:
    """Return enum value for wire responses while preserving plain values."""
    return value.value if hasattr(value, "value") else value


def _deployment_mode(gateway_type: object, mode: str | None, source: str | None) -> str:
    """Derive the canonical deployment topology used by the Console contract."""
    normalized_mode = (mode or "").strip().lower()
    if normalized_mode == "sidecar":
        return "sidecar"
    if normalized_mode in {"edge", "edge-mcp"}:
        return "edge"
    if normalized_mode == "connect" or source == "self_register":
        return "connect"

    normalized_type = str(_wire_value(gateway_type) or "").strip().lower()
    if normalized_type in {"stoa", "stoa_edge_mcp"}:
        return "edge"
    if normalized_type == "stoa_sidecar":
        return "sidecar"
    return "connect"


def _target_gateway_type(gateway_type: object) -> str:
    """Normalize STOA topology-specific types to the technology family."""
    normalized_type = str(_wire_value(gateway_type) or "").strip().lower()
    if normalized_type.startswith("stoa_"):
        return "stoa"
    return normalized_type


def _desired_git_fields(
    desired_state: dict | None,
    api_git_path: str | None = None,
    api_git_commit_sha: str | None = None,
) -> dict[str, object]:
    """Return stable Git provenance fields for deployment list responses."""
    desired = desired_state or {}
    desired_commit_sha = desired.get("desired_commit_sha") or api_git_commit_sha
    desired_git_path = desired.get("desired_git_path") or api_git_path
    return {
        "desired_source": desired.get("desired_source") or ("git" if desired_commit_sha else "unknown"),
        "git_sync_status": desired.get("git_sync_status") or ("up_to_date" if desired_commit_sha else "unknown"),
        "desired_commit_sha": desired_commit_sha,
        "desired_git_path": desired_git_path,
    }


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
        result = await self.session.execute(select(GatewayDeployment).where(GatewayDeployment.id == deployment_id))
        return result.scalar_one_or_none()

    async def get_by_api_and_gateway(self, api_catalog_id: UUID, gateway_instance_id: UUID) -> GatewayDeployment | None:
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
        query = select(GatewayDeployment).where(GatewayDeployment.gateway_instance_id == gateway_instance_id)
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
        query = select(
            GatewayDeployment,
            APICatalog.git_path.label("api_git_path"),
            APICatalog.git_commit_sha.label("api_git_commit_sha"),
            GatewayInstance.name.label("gateway_name"),
            GatewayInstance.display_name.label("gateway_display_name"),
            GatewayInstance.gateway_type.label("gateway_type"),
            GatewayInstance.environment.label("gateway_environment"),
        ).join(
            GatewayInstance,
            GatewayDeployment.gateway_instance_id == GatewayInstance.id,
        ).join(
            APICatalog,
            GatewayDeployment.api_catalog_id == APICatalog.id,
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
            git_fields = _desired_git_fields(dep.desired_state, row.api_git_path, row.api_git_commit_sha)
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
                "sync_steps": dep.sync_steps,
                "gateway_resource_id": dep.gateway_resource_id,
                "created_at": dep.created_at,
                "updated_at": dep.updated_at,
                "gateway_name": row.gateway_name,
                "gateway_display_name": row.gateway_display_name,
                "gateway_type": row.gateway_type.value if hasattr(row.gateway_type, "value") else row.gateway_type,
                "gateway_environment": row.gateway_environment,
                **git_fields,
            })
        return deployments, total

    async def list_console_contract(
        self,
        environment: str | None = None,
        gateway_instance_id: UUID | None = None,
        tenant_id: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[dict], int]:
        """List aggregated deployment rows for the Console /api-deployments page."""
        query = (
            select(
                GatewayDeployment,
                APICatalog.id.label("api_catalog_id"),
                APICatalog.api_id.label("api_id"),
                APICatalog.api_name.label("api_name"),
                APICatalog.tenant_id.label("tenant_id"),
                APICatalog.git_path.label("api_git_path"),
                APICatalog.git_commit_sha.label("api_git_commit_sha"),
                GatewayInstance.id.label("gateway_id"),
                GatewayInstance.name.label("gateway_name"),
                GatewayInstance.display_name.label("gateway_display_name"),
                GatewayInstance.gateway_type.label("gateway_type"),
                GatewayInstance.environment.label("gateway_environment"),
                GatewayInstance.status.label("gateway_status"),
                GatewayInstance.mode.label("gateway_mode"),
                GatewayInstance.source.label("gateway_source"),
                Promotion.status.label("promotion_state"),
            )
            .join(APICatalog, GatewayDeployment.api_catalog_id == APICatalog.id)
            .join(GatewayInstance, GatewayDeployment.gateway_instance_id == GatewayInstance.id)
            .outerjoin(Promotion, GatewayDeployment.promotion_id == Promotion.id)
        )

        if environment:
            query = query.where(GatewayInstance.environment == environment)
        if gateway_instance_id:
            query = query.where(GatewayDeployment.gateway_instance_id == gateway_instance_id)
        if tenant_id:
            query = query.where(APICatalog.tenant_id == tenant_id)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        query = query.order_by(GatewayDeployment.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        items = []
        for row in result.all():
            dep = row.GatewayDeployment
            desired_state = dep.desired_state or {}
            git_fields = _desired_git_fields(desired_state, row.api_git_path, row.api_git_commit_sha)
            items.append(
                {
                    "deployment_id": dep.id,
                    "api_catalog_id": row.api_catalog_id,
                    "api_id": row.api_id,
                    "api_name": row.api_name,
                    "tenant_id": row.tenant_id,
                    "environment": row.gateway_environment,
                    "desired_state": desired_state,
                    **git_fields,
                    "gateway_target": {
                        "id": row.gateway_id,
                        "name": row.gateway_name,
                        "display_name": row.gateway_display_name,
                        "environment": row.gateway_environment,
                        "deployment_mode": _deployment_mode(row.gateway_type, row.gateway_mode, row.gateway_source),
                        "target_gateway_type": _target_gateway_type(row.gateway_type),
                        "source": row.gateway_source,
                    },
                    "deployment_status": _wire_value(dep.sync_status),
                    "gateway_health": _wire_value(row.gateway_status),
                    "last_ack": dep.last_sync_success,
                    "promotion_state": row.promotion_state,
                    "sync_error": dep.sync_error,
                }
            )
        return items, total

    async def list_by_statuses(self, statuses: list[DeploymentSyncStatus]) -> list[GatewayDeployment]:
        """List deployments matching any of the given statuses."""
        result = await self.session.execute(
            select(GatewayDeployment).where(GatewayDeployment.sync_status.in_(statuses))
        )
        return list(result.scalars().all())

    async def list_by_statuses_and_gateway(
        self, statuses: list[DeploymentSyncStatus], gateway_instance_id: UUID
    ) -> list[GatewayDeployment]:
        """List deployments matching statuses AND a specific gateway instance."""
        result = await self.session.execute(
            select(GatewayDeployment).where(
                GatewayDeployment.sync_status.in_(statuses),
                GatewayDeployment.gateway_instance_id == gateway_instance_id,
            )
        )
        return list(result.scalars().all())

    async def list_pending_sync(self) -> list[GatewayDeployment]:
        """List deployments needing sync (pending, drifted, or error with retries)."""
        result = await self.session.execute(
            select(GatewayDeployment).where(
                GatewayDeployment.sync_status.in_(
                    [
                        DeploymentSyncStatus.PENDING,
                        DeploymentSyncStatus.DRIFTED,
                        DeploymentSyncStatus.DELETING,
                    ]
                )
            )
        )
        return list(result.scalars().all())

    async def list_synced(self) -> list[GatewayDeployment]:
        """List all synced deployments (for drift detection)."""
        result = await self.session.execute(
            select(GatewayDeployment).where(GatewayDeployment.sync_status == DeploymentSyncStatus.SYNCED)
        )
        return list(result.scalars().all())

    async def list_by_promotion(self, promotion_id: UUID) -> list[GatewayDeployment]:
        """List all deployments linked to a promotion."""
        result = await self.session.execute(
            select(GatewayDeployment).where(GatewayDeployment.promotion_id == promotion_id)
        )
        return list(result.scalars().all())

    async def get_status_summary(self) -> dict:
        """Get sync status counts for the dashboard."""
        counts = {}
        for status in DeploymentSyncStatus:
            count_query = select(func.count()).where(GatewayDeployment.sync_status == status)
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

    async def get_primary_for_api(self, api_id: str, tenant_id: str) -> GatewayDeployment | None:
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
