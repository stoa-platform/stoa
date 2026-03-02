"""Gateway metrics aggregation service for observability dashboard.

Phase 2 (CAB-1635): per-tenant filtering, adapter operation metrics, health history.
"""

import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.metrics import (
    ADAPTER_OPERATION_DURATION,
    ADAPTER_OPERATIONS_TOTAL,
)
from src.models.gateway_deployment import DeploymentSyncStatus, GatewayDeployment
from src.models.gateway_instance import GatewayInstance, GatewayInstanceStatus

logger = logging.getLogger(__name__)


class GatewayMetricsService:
    """Aggregates health and sync metrics across gateways."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_health_summary(self, tenant_id: str | None = None) -> dict:
        """Count gateways by status (online/offline/degraded/maintenance).

        Args:
            tenant_id: When provided, only count gateways belonging to this tenant.
                       cpi-admin passes None to see all.
        """
        counts = {}
        total = 0
        for status in GatewayInstanceStatus:
            query = select(func.count()).where(GatewayInstance.status == status)
            if tenant_id:
                query = query.where(GatewayInstance.tenant_id == tenant_id)
            result = await self.db.execute(query)
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

    async def get_sync_status_summary(self, gateway_id: UUID | None = None, tenant_id: str | None = None) -> dict:
        """Count deployments by sync_status, optionally filtered by gateway or tenant.

        Args:
            gateway_id: Filter by specific gateway instance.
            tenant_id: Filter by tenant (joins through gateway_instances).
                       Skipped when gateway_id is already provided.
        """
        counts = {}
        total = 0
        for status in DeploymentSyncStatus:
            query = select(func.count()).where(GatewayDeployment.sync_status == status)
            if gateway_id:
                query = query.where(GatewayDeployment.gateway_instance_id == gateway_id)
            elif tenant_id:
                query = query.join(
                    GatewayInstance,
                    GatewayDeployment.gateway_instance_id == GatewayInstance.id,
                ).where(GatewayInstance.tenant_id == tenant_id)
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

    async def get_gateway_metrics(self, gateway_id: UUID, tenant_id: str | None = None) -> dict | None:
        """Per-gateway metrics: status, health, sync summary, recent errors.

        Args:
            gateway_id: Gateway instance ID.
            tenant_id: When provided, verifies gateway belongs to this tenant.
        """
        query = select(GatewayInstance).where(GatewayInstance.id == gateway_id)
        if tenant_id:
            query = query.where(GatewayInstance.tenant_id == tenant_id)
        result = await self.db.execute(query)
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

    async def get_aggregated_metrics(self, tenant_id: str | None = None) -> dict:
        """Combined health + sync summaries + overall_status."""
        health = await self.get_health_summary(tenant_id=tenant_id)
        sync = await self.get_sync_status_summary(tenant_id=tenant_id)

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

    def get_adapter_operation_metrics(self) -> dict:
        """Read adapter operation metrics from in-process Prometheus registry.

        Returns per-gateway-type: total_ops, success_rate, avg_latency_ms, operations breakdown.
        """
        metrics_by_gateway: dict[str, dict] = {}

        # Collect operation counts from Counter
        for metric_family in ADAPTER_OPERATIONS_TOTAL.collect():
            for sample in metric_family.samples:
                if sample.name.endswith("_created"):
                    continue
                gw = sample.labels.get("gateway_type", "unknown")
                op = sample.labels.get("operation", "unknown")
                status = sample.labels.get("status", "unknown")

                if gw not in metrics_by_gateway:
                    metrics_by_gateway[gw] = {
                        "total_ops": 0,
                        "success_count": 0,
                        "error_count": 0,
                        "operations": {},
                    }

                entry = metrics_by_gateway[gw]
                if op not in entry["operations"]:
                    entry["operations"][op] = {"total": 0, "success": 0, "error": 0, "timeout": 0}

                entry["operations"][op][status] = int(sample.value)
                entry["operations"][op]["total"] += int(sample.value)
                entry["total_ops"] += int(sample.value)
                if status == "success":
                    entry["success_count"] += int(sample.value)
                elif status in ("error", "timeout"):
                    entry["error_count"] += int(sample.value)

        # Collect latency (sum/count from Histogram for avg calculation)
        for metric_family in ADAPTER_OPERATION_DURATION.collect():
            for sample in metric_family.samples:
                gw = sample.labels.get("gateway_type", "unknown")
                if gw not in metrics_by_gateway:
                    continue
                if sample.name.endswith("_sum"):
                    metrics_by_gateway[gw].setdefault("_duration_sum", 0.0)
                    metrics_by_gateway[gw]["_duration_sum"] += sample.value
                elif sample.name.endswith("_count"):
                    metrics_by_gateway[gw].setdefault("_duration_count", 0)
                    metrics_by_gateway[gw]["_duration_count"] += int(sample.value)

        # Compute derived fields
        for data in metrics_by_gateway.values():
            total = data["total_ops"]
            data["success_rate"] = round((data["success_count"] / total) * 100, 1) if total > 0 else 0.0
            count = data.pop("_duration_count", 0)
            total_sum = data.pop("_duration_sum", 0.0)
            data["avg_latency_ms"] = round((total_sum / count) * 1000, 2) if count > 0 else 0.0

        return {"gateway_types": metrics_by_gateway}

    async def get_health_history(self, gateway_id: UUID, tenant_id: str | None = None) -> dict | None:
        """Get health check details for a specific gateway.

        Returns current health status, last check time, and health_details JSONB
        which contains check_method, consecutive_failures, last_error, etc.

        Args:
            gateway_id: Gateway instance ID.
            tenant_id: When provided, verifies gateway belongs to this tenant.
        """
        query = select(GatewayInstance).where(GatewayInstance.id == gateway_id)
        if tenant_id:
            query = query.where(GatewayInstance.tenant_id == tenant_id)
        result = await self.db.execute(query)
        gateway = result.scalar_one_or_none()
        if not gateway:
            return None

        return {
            "gateway_id": str(gateway.id),
            "name": gateway.name,
            "gateway_type": gateway.gateway_type.value if gateway.gateway_type else "",
            "status": gateway.status.value if gateway.status else "offline",
            "last_health_check": gateway.last_health_check.isoformat() if gateway.last_health_check else None,
            "health_details": gateway.health_details or {},
            "tenant_id": gateway.tenant_id,
        }
