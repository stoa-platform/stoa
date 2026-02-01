"""
Tenant Lifecycle API Routes
CAB-409: Auto-Cleanup & Notifications for demo.gostoa.dev

Endpoints:
    GET  /tenants/{tenant_id}/lifecycle/status   -> Current lifecycle status
    POST /tenants/{tenant_id}/lifecycle/extend    -> Extend trial (+7 days, 1x)
    POST /tenants/{tenant_id}/lifecycle/upgrade   -> Convert to Enterprise
    POST /lifecycle/cron                          -> Manual cron trigger (admin)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.auth import get_current_user, User

from .models import (
    ExtendTrialRequest,
    ExtendTrialResponse,
    TenantStatusResponse,
    UpgradeTenantRequest,
    UpgradeTenantResponse,
    LifecycleCronSummary,
)
from .service import LifecycleError, TenantLifecycleService, TenantNotFoundError
from .notifications import NotificationService
from .cleanup import CleanupService

router = APIRouter(prefix="/v1/tenants", tags=["Tenant Lifecycle"])
admin_router = APIRouter(prefix="/v1/lifecycle", tags=["Lifecycle Admin"])


# ─── Dependencies ─────────────────────────────────────────────────────────────

async def get_lifecycle_service(
    db: AsyncSession = Depends(get_db),
) -> TenantLifecycleService:
    """Wire up the lifecycle service with its dependencies."""
    notification_service = NotificationService(db)
    cleanup_service = CleanupService(db)
    return TenantLifecycleService(db, notification_service, cleanup_service)


# ─── Tenant Lifecycle Endpoints ───────────────────────────────────────────────

@router.get(
    "/{tenant_id}/lifecycle/status",
    response_model=TenantStatusResponse,
    summary="Get tenant lifecycle status",
    description="Returns current lifecycle state, days remaining, and available actions.",
)
async def get_tenant_lifecycle_status(
    tenant_id: str,
    service: TenantLifecycleService = Depends(get_lifecycle_service),
    current_user: User = Depends(get_current_user),
):
    # COUNCIL Chucky: tenant isolation check
    if current_user.tenant_id and current_user.tenant_id != tenant_id:
        if "cpi-admin" not in current_user.roles:
            raise HTTPException(status_code=403, detail="Access denied to this tenant")
    try:
        return await service.get_status(tenant_id)
    except TenantNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tenant {tenant_id} not found")


@router.post(
    "/{tenant_id}/lifecycle/extend",
    response_model=ExtendTrialResponse,
    summary="Extend trial period",
    description="Extend the demo trial by 7 days. Allowed once per tenant.",
)
async def extend_tenant_trial(
    tenant_id: str,
    request: ExtendTrialRequest = ExtendTrialRequest(),
    service: TenantLifecycleService = Depends(get_lifecycle_service),
    current_user: User = Depends(get_current_user),
):
    if current_user.tenant_id and current_user.tenant_id != tenant_id:
        if "cpi-admin" not in current_user.roles:
            raise HTTPException(status_code=403, detail="Access denied to this tenant")
    try:
        return await service.extend_trial(tenant_id, reason=request.reason)
    except TenantNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tenant {tenant_id} not found")
    except LifecycleError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post(
    "/{tenant_id}/lifecycle/upgrade",
    response_model=UpgradeTenantResponse,
    summary="Upgrade to paid tier",
    description="Convert a demo tenant to a paid tier. Preserves data and configuration.",
)
async def upgrade_tenant(
    tenant_id: str,
    request: UpgradeTenantRequest,
    service: TenantLifecycleService = Depends(get_lifecycle_service),
    current_user: User = Depends(get_current_user),
):
    if current_user.tenant_id and current_user.tenant_id != tenant_id:
        if "cpi-admin" not in current_user.roles:
            raise HTTPException(status_code=403, detail="Access denied to this tenant")
    try:
        return await service.upgrade_tenant(
            tenant_id,
            target_tier=request.target_tier,
            contact_email=request.contact_email,
        )
    except TenantNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tenant {tenant_id} not found")
    except LifecycleError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ─── Admin Endpoints ─────────────────────────────────────────────────────────

@admin_router.post(
    "/cron",
    response_model=LifecycleCronSummary,
    summary="Trigger lifecycle cron manually",
    description="Run the lifecycle check manually. Requires cpi-admin role.",
)
async def trigger_lifecycle_cron(
    service: TenantLifecycleService = Depends(get_lifecycle_service),
    current_user: User = Depends(get_current_user),
):
    if "cpi-admin" not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin role required")
    return await service.run_lifecycle_check()
