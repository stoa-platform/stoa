"""Plans router - Subscription plan management (CAB-1121)."""

import logging
import math
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import User, get_current_user
from ..database import get_db
from ..models.plan import Plan, PlanStatus
from ..repositories.plan import PlanRepository
from ..schemas.plan import (
    PlanCreate,
    PlanListResponse,
    PlanResponse,
    PlanStatusEnum,
    PlanUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/plans", tags=["Plans"])


def _has_tenant_access(user: User, tenant_id: str) -> bool:
    """Check if user has access to a tenant."""
    if "cpi-admin" in user.roles:
        return True
    return user.tenant_id == tenant_id


# ============== CRUD Endpoints ==============


@router.post("/{tenant_id}", response_model=PlanResponse, status_code=201)
async def create_plan(
    tenant_id: str,
    request: PlanCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new subscription plan for a tenant."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = PlanRepository(db)

    # Check for duplicate slug
    existing = await repo.get_by_slug(tenant_id, request.slug)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Plan with slug '{request.slug}' already exists in this tenant",
        )

    plan = Plan(
        slug=request.slug,
        name=request.name,
        description=request.description,
        tenant_id=tenant_id,
        rate_limit_per_second=request.rate_limit_per_second,
        rate_limit_per_minute=request.rate_limit_per_minute,
        daily_request_limit=request.daily_request_limit,
        monthly_request_limit=request.monthly_request_limit,
        burst_limit=request.burst_limit,
        requires_approval=request.requires_approval,
        auto_approve_roles=request.auto_approve_roles,
        status=PlanStatus.ACTIVE,
        pricing_metadata=request.pricing_metadata,
        created_by=user.id,
    )

    try:
        plan = await repo.create(plan)
        logger.info(f"Created plan {plan.id} slug={request.slug} tenant={tenant_id} by={user.email}")
    except Exception as e:
        logger.error(f"Failed to create plan: {e}")
        raise HTTPException(status_code=500, detail="Failed to create plan")

    return PlanResponse.model_validate(plan)


@router.get("/{tenant_id}", response_model=PlanListResponse)
async def list_plans(
    tenant_id: str,
    status: PlanStatusEnum | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List subscription plans for a tenant."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = PlanRepository(db)

    db_status = PlanStatus(status.value) if status else None
    plans, total = await repo.list_by_tenant(
        tenant_id=tenant_id,
        status=db_status,
        page=page,
        page_size=page_size,
    )

    return PlanListResponse(
        items=[PlanResponse.model_validate(p) for p in plans],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 1,
    )


@router.get("/{tenant_id}/by-slug/{slug}", response_model=PlanResponse)
async def get_plan_by_slug(
    tenant_id: str,
    slug: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get plan by slug within a tenant."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = PlanRepository(db)
    plan = await repo.get_by_slug(tenant_id, slug)

    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    return PlanResponse.model_validate(plan)


@router.get("/{tenant_id}/{plan_id}", response_model=PlanResponse)
async def get_plan(
    tenant_id: str,
    plan_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get plan details by ID."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = PlanRepository(db)
    plan = await repo.get_by_id(plan_id)

    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    if plan.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Plan not found")

    return PlanResponse.model_validate(plan)


@router.put("/{tenant_id}/{plan_id}", response_model=PlanResponse)
async def update_plan(
    tenant_id: str,
    plan_id: UUID,
    request: PlanUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update plan details."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = PlanRepository(db)
    plan = await repo.get_by_id(plan_id)

    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    if plan.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Plan not found")

    # Apply updates
    update_data = request.model_dump(exclude_unset=True)
    if "status" in update_data:
        update_data["status"] = PlanStatus(update_data["status"])
    for field, value in update_data.items():
        setattr(plan, field, value)

    plan = await repo.update(plan)

    logger.info(f"Updated plan {plan_id} by {user.email}")

    return PlanResponse.model_validate(plan)


@router.delete("/{tenant_id}/{plan_id}", status_code=204)
async def delete_plan(
    tenant_id: str,
    plan_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a plan."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = PlanRepository(db)
    plan = await repo.get_by_id(plan_id)

    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    if plan.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Plan not found")

    await repo.delete(plan)

    logger.info(f"Deleted plan {plan_id} by {user.email}")
