"""LLM Budget API — Provider config + budget CRUD for tenant admins (CAB-1491)."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import User, get_current_user
from ..database import get_db
from ..schemas.llm_budget import (
    LlmBudgetCreate,
    LlmBudgetResponse,
    LlmBudgetUpdate,
    LlmProviderCreate,
    LlmProviderResponse,
    SpendSummaryResponse,
)
from ..services.llm_budget_service import LlmBudgetService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/tenants/{tenant_id}/llm",
    tags=["LLM Budget & Providers"],
)


def _has_tenant_access(user: User, tenant_id: str) -> bool:
    """Check if user has access to a tenant."""
    if "cpi-admin" in user.roles:
        return True
    return user.tenant_id == tenant_id


# ---- Provider endpoints ----


@router.post("/providers", response_model=LlmProviderResponse, status_code=201)
async def create_provider(
    tenant_id: str,
    request: LlmProviderCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new LLM provider configuration for a tenant."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    service = LlmBudgetService(db)
    provider = await service.create_provider(tenant_id, request)
    await db.commit()
    logger.info("Created LLM provider %s for tenant %s by %s", provider.id, tenant_id, user.email)
    return provider


@router.get("/providers", response_model=list[LlmProviderResponse])
async def list_providers(
    tenant_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all LLM provider configurations for a tenant."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    service = LlmBudgetService(db)
    return await service.list_providers(tenant_id)


@router.delete("/providers/{provider_id}", status_code=204)
async def delete_provider(
    tenant_id: str,
    provider_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an LLM provider configuration."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    service = LlmBudgetService(db)
    try:
        await service.delete_provider(provider_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Provider not found")

    await db.commit()
    logger.info("Deleted LLM provider %s by %s", provider_id, user.email)


# ---- Budget endpoints ----


@router.post("/budget", response_model=LlmBudgetResponse, status_code=201)
async def create_budget(
    tenant_id: str,
    request: LlmBudgetCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create an LLM budget for a tenant (one per tenant)."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    service = LlmBudgetService(db)
    try:
        budget = await service.create_budget(tenant_id, request)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    await db.commit()
    logger.info("Created LLM budget for tenant %s by %s", tenant_id, user.email)
    return budget


@router.get("/budget", response_model=LlmBudgetResponse)
async def get_budget(
    tenant_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the LLM budget for a tenant."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    service = LlmBudgetService(db)
    try:
        return await service.get_budget(tenant_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Budget not found")


@router.put("/budget", response_model=LlmBudgetResponse)
async def update_budget(
    tenant_id: str,
    request: LlmBudgetUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the LLM budget configuration for a tenant."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    service = LlmBudgetService(db)
    try:
        budget = await service.update_budget(tenant_id, request)
    except ValueError:
        raise HTTPException(status_code=404, detail="Budget not found")

    await db.commit()
    logger.info("Updated LLM budget for tenant %s by %s", tenant_id, user.email)
    return budget


@router.get("/spend", response_model=SpendSummaryResponse)
async def get_spend_summary(
    tenant_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current LLM spend summary for a tenant."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    service = LlmBudgetService(db)
    try:
        return await service.get_spend_summary(tenant_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Budget not found")
