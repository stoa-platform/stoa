"""Billing API — Department budget CRUD for tenant admins (CAB-1458)."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import User, get_current_user
from ..database import get_db
from ..schemas.billing import (
    DepartmentBudgetCreate,
    DepartmentBudgetListResponse,
    DepartmentBudgetResponse,
    DepartmentBudgetUpdate,
)
from ..services.billing_service import BillingService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/tenants/{tenant_id}/budgets",
    tags=["Billing - Department Budgets"],
)


def _has_tenant_access(user: User, tenant_id: str) -> bool:
    """Check if user has access to a tenant."""
    if "cpi-admin" in user.roles:
        return True
    return user.tenant_id == tenant_id


@router.post("", response_model=DepartmentBudgetResponse, status_code=201)
async def create_budget(
    tenant_id: str,
    request: DepartmentBudgetCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new department budget."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    service = BillingService(db)
    budget = await service.create_budget(tenant_id, request, created_by=user.email)
    await db.commit()
    logger.info("Created budget %s for tenant %s by %s", budget.id, tenant_id, user.email)
    return budget


@router.get("", response_model=DepartmentBudgetListResponse)
async def list_budgets(
    tenant_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List department budgets for a tenant."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    service = BillingService(db)
    return await service.list_budgets(tenant_id, page, page_size)


@router.get("/{budget_id}", response_model=DepartmentBudgetResponse)
async def get_budget(
    tenant_id: str,
    budget_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific department budget."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    service = BillingService(db)
    try:
        return await service.get_budget(budget_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Budget not found")


@router.put("/{budget_id}", response_model=DepartmentBudgetResponse)
async def update_budget(
    tenant_id: str,
    budget_id: UUID,
    request: DepartmentBudgetUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a department budget configuration."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    service = BillingService(db)
    try:
        budget = await service.update_budget(budget_id, request)
    except ValueError:
        raise HTTPException(status_code=404, detail="Budget not found")

    await db.commit()
    logger.info("Updated budget %s by %s", budget_id, user.email)
    return budget


@router.delete("/{budget_id}", status_code=204)
async def delete_budget(
    tenant_id: str,
    budget_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a department budget."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    service = BillingService(db)
    budget_obj = await service.repo.get_by_id(budget_id)
    if not budget_obj or budget_obj.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Budget not found")

    await service.repo.delete(budget_obj)
    await db.commit()
    logger.info("Deleted budget %s by %s", budget_id, user.email)
