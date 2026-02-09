"""Admin Quotas Router — Quota usage monitoring and management (CAB-1121 Phase 4)."""

import logging
import math
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import User, get_current_user
from ..database import get_db
from ..repositories.quota_usage import QuotaUsageRepository
from ..schemas.quota import (
    QuotaListResponse,
    QuotaStatsResponse,
    QuotaUsageResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/admin/quotas", tags=["Quotas"])


def _has_admin_access(user: User, tenant_id: str) -> bool:
    """Check if user has admin access to tenant quotas."""
    if "cpi-admin" in user.roles:
        return True
    return "tenant-admin" in user.roles and user.tenant_id == tenant_id


@router.get("/{tenant_id}", response_model=QuotaListResponse)
async def list_quota_usage(
    tenant_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all consumers' quota usage for a tenant."""
    if not _has_admin_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = QuotaUsageRepository(db)
    items, total = await repo.list_by_tenant(tenant_id, page=page, page_size=page_size)

    return QuotaListResponse(
        items=[QuotaUsageResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 1,
    )


@router.get("/{tenant_id}/stats", response_model=QuotaStatsResponse)
async def get_quota_stats(
    tenant_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get aggregate quota stats for a tenant."""
    if not _has_admin_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = QuotaUsageRepository(db)
    stats = await repo.get_stats(tenant_id)

    return QuotaStatsResponse(**stats)


@router.get("/{tenant_id}/{consumer_id}", response_model=QuotaUsageResponse)
async def get_consumer_quota(
    tenant_id: str,
    consumer_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get specific consumer's quota usage."""
    if not _has_admin_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = QuotaUsageRepository(db)
    usage = await repo.get_current(consumer_id, tenant_id)

    if not usage:
        raise HTTPException(status_code=404, detail="No quota usage found for this consumer")

    return QuotaUsageResponse.model_validate(usage)


@router.post("/{tenant_id}/{consumer_id}/reset", response_model=QuotaUsageResponse)
async def reset_consumer_quota(
    tenant_id: str,
    consumer_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually reset a consumer's quota counters."""
    if not _has_admin_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = QuotaUsageRepository(db)
    usage = await repo.reset(consumer_id, tenant_id)

    if not usage:
        raise HTTPException(status_code=404, detail="No quota usage found for this consumer")

    logger.info(f"Quota reset for consumer {consumer_id} tenant={tenant_id} by={user.email}")

    return QuotaUsageResponse.model_validate(usage)
