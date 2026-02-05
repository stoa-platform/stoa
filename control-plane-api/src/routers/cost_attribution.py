"""API routes for cost attribution and usage reporting - Phase 8

Endpoints:
  GET /v1/admin/usage/report   — Admin: cross-tenant usage report
  GET /v1/admin/usage/{id}     — Admin: single tenant detailed report
  GET /v1/usage/me/costs       — Self-service: my tenant cost report
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.rbac import get_current_user, require_role
from src.database import get_db
from src.models.tenant import Tenant
from src.schemas.cost_attribution import AdminUsageReport, TenantUsageReport
from src.services.cost_attribution_service import cost_attribution_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Cost Attribution"])


# ============================================================================
# Admin endpoints
# ============================================================================

@router.get(
    "/v1/admin/usage/report",
    response_model=AdminUsageReport,
    summary="Cross-tenant usage report",
    description="Aggregated usage and cost report across all tenants. Requires cpi-admin role.",
)
async def get_admin_usage_report(
    days: int = Query(default=30, ge=1, le=365, description="Report period in days"),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(["cpi-admin"])),
):
    """Admin usage report with per-tenant breakdown, sorted by cost."""
    result = await db.execute(select(Tenant))
    tenants = result.scalars().all()

    tenant_list = [
        {
            "id": str(t.id),
            "name": t.name,
            "tier": getattr(t, "tier", "platform") or "platform",
        }
        for t in tenants
    ]

    return await cost_attribution_service.get_admin_report(tenant_list, days=days)


@router.get(
    "/v1/admin/usage/{tenant_id}",
    response_model=TenantUsageReport,
    summary="Tenant detailed usage report",
    description="Detailed usage breakdown for a specific tenant. Requires cpi-admin role.",
)
async def get_tenant_usage_report(
    tenant_id: str,
    days: int = Query(default=30, ge=1, le=365, description="Report period in days"),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(["cpi-admin"])),
):
    """Detailed report for a single tenant: usage breakdown, quota, cost."""
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tier = getattr(tenant, "tier", "platform") or "platform"

    return await cost_attribution_service.get_tenant_report(
        tenant_id=str(tenant.id),
        tenant_name=tenant.name,
        tier=tier,
        days=days,
    )


# ============================================================================
# Self-service endpoint (tenant users)
# ============================================================================

@router.get(
    "/v1/usage/me/costs",
    response_model=TenantUsageReport,
    summary="My tenant cost report",
    description="Usage and cost report for the current user's tenant.",
)
async def get_my_costs(
    days: int = Query(default=30, ge=1, le=365, description="Report period in days"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Self-service cost report for the authenticated user's tenant."""
    tenant_id = getattr(user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant associated with user")

    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tier = getattr(tenant, "tier", "platform") or "platform"

    return await cost_attribution_service.get_tenant_report(
        tenant_id=str(tenant.id),
        tenant_name=tenant.name,
        tier=tier,
        days=days,
    )
