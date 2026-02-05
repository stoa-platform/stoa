"""API routes for gateway observability and metrics.

IMPORTANT: This router uses prefix /v1/admin/gateways (same as gateway_instances).
Static paths like /metrics and /health-summary MUST be registered BEFORE the
gateway_instances router to avoid FastAPI treating them as /{gateway_id} UUID params.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.rbac import require_role
from src.database import get_db
from src.services.gateway_metrics_service import GatewayMetricsService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/admin/gateways",
    tags=["Gateway Observability"],
)


@router.get("/metrics")
async def get_aggregated_metrics(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """Aggregated metrics across all gateways (health + sync)."""
    svc = GatewayMetricsService(db)
    return await svc.get_aggregated_metrics()


@router.get("/health-summary")
async def get_health_summary(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """Gateway health status counts."""
    svc = GatewayMetricsService(db)
    return await svc.get_health_summary()


@router.get("/{gateway_id}/metrics")
async def get_gateway_metrics(
    gateway_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["cpi-admin", "tenant-admin"])),
):
    """Per-gateway detailed metrics."""
    svc = GatewayMetricsService(db)
    result = await svc.get_gateway_metrics(gateway_id)
    if not result:
        raise HTTPException(status_code=404, detail="Gateway instance not found")
    return result
