"""Gateway metrics aggregation service for observability dashboard."""
import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.gateway_deployment import DeploymentSyncStatus, GatewayDeployment
from src.models.gateway_instance import GatewayInstance, GatewayInstanceStatus

logger = logging.getLogger(__name__)


class GatewayMetricsService:
    """Aggregates health and sync metrics across gateways."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_health_summary(self) -> dict:
        """Count gateways by status (online/offline/degraded/maintenance)."""
        counts = {}
        total = 0
        for status in GatewayInstanceStatus:
            result = await self.db.execute(
                select(func.count()).where(GatewayInstance.status == status)
            )
            count = result.scalar_one()
            counts[status.value] = count
            total += count

        counts["total_gateways"] = total
        if total > 0:
            online = counts.get("online", 0)
            counts["health_percentage"] = round((online / total) * 100, 1)
        else:
            counts["health_percentage"] = 0.0

        return counts

    async def get_sync_status_summary(self, gateway_id: UUID | None = None) -> dict:
        """Count deployments by sync_status, optionally filtered by gateway."""
        counts = {}
        total = 0
        for status in DeploymentSyncStatus:
            query = select(func.count()).where(GatewayDeployment.sync_status == status)
            if gateway_id:
                query = query.where(GatewayDeployment.gateway_instance_id == gateway_id)
            result = await self.db.execute(query)
            count = result.scalar_one()
            counts[status.value] = count
            total += count

        counts["total_deployments"] = total
        synced = counts.get("synced", 0)
        if total > 0:
            counts["sync_percentage"] = round((synced / total) * 100, 1)
        else:
            counts["sync_percentage"] = 0.0

        return counts

    async def get_gateway_metrics(self, gateway_id: UUID) -> dict | None:
        """Per-gateway metrics: status, health, sync summary, recent errors."""
        result = await self.db.execute(
            select(GatewayInstance).where(GatewayInstance.id == gateway_id)
        )
        gateway = result.scalar_one_or_none()
        if not gateway:
            return None

        sync_summary = await self.get_sync_status_summary(gateway_id=gateway_id)

        # Get recent errors (last 5)
        error_result = await self.db.execute(
            select(GatewayDeployment)
            .where(
                GatewayDeployment.gateway_instance_id == gateway_id,
                GatewayDeployment.sync_status == DeploymentSyncStatus.ERROR,
            )
            .order_by(GatewayDeployment.last_sync_attempt.desc())
            .limit(5)
        )
        recent_errors = [
            {
                "deployment_id": str(d.id),
                "api_catalog_id": str(d.api_catalog_id),
                "error": d.sync_error,
                "attempts": d.sync_attempts,
                "last_attempt": d.last_sync_attempt.isoformat() if d.last_sync_attempt else None,
            }
            for d in error_result.scalars().all()
        ]

        return {
            "gateway_id": str(gateway.id),
            "name": gateway.name,
            "display_name": gateway.display_name,
            "gateway_type": gateway.gateway_type.value if gateway.gateway_type else "",
            "status": gateway.status.value if gateway.status else "offline",
            "last_health_check": gateway.last_health_check.isoformat() if gateway.last_health_check else None,
            "sync": sync_summary,
            "recent_errors": recent_errors,
        }

    async def get_aggregated_metrics(self) -> dict:
        """Combined health + sync summaries + overall_status."""
        health = await self.get_health_summary()
        sync = await self.get_sync_status_summary()

        # Determine overall status
        total_gateways = health.get("total_gateways", 0)
        online = health.get("online", 0)
        error_count = sync.get("error", 0)
        drifted_count = sync.get("drifted", 0)

        if total_gateways == 0:
            overall = "unknown"
        elif online == total_gateways and error_count == 0 and drifted_count == 0:
            overall = "healthy"
        elif online == 0:
            overall = "critical"
        else:
            overall = "degraded"

        return {
            "health": health,
            "sync": sync,
            "overall_status": overall,
        }
