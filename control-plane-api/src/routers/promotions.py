"""Promotions router — GitOps cross-environment promotion flow (CAB-1706)"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import Permission, User, get_current_user, require_permission, require_tenant_access
from ..database import get_db
from ..schemas.promotion import (
    PromotionCreate,
    PromotionDiffResponse,
    PromotionListResponse,
    PromotionResponse,
    PromotionRollbackRequest,
)
from ..services.promotion_service import PromotionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/tenants/{tenant_id}/promotions", tags=["Promotions"])


@router.post("/{api_id}", response_model=PromotionResponse, status_code=201)
@require_permission(Permission.APIS_PROMOTE)
@require_tenant_access
async def create_promotion(
    tenant_id: str,
    api_id: str,
    request: PromotionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a promotion request for an API (dev→staging or staging→production)."""
    service = PromotionService(db)
    try:
        promotion = await service.create_promotion(
            tenant_id=tenant_id,
            api_id=api_id,
            source_environment=request.source_environment,
            target_environment=request.target_environment,
            message=request.message,
            requested_by=user.username,
            user_id=user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return PromotionResponse.model_validate(promotion)


@router.get("", response_model=PromotionListResponse)
@require_tenant_access
async def list_promotions(
    tenant_id: str,
    api_id: str | None = None,
    status: str | None = None,
    target_environment: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List promotions for a tenant with optional filtering."""
    service = PromotionService(db)
    items, total = await service.list_promotions(
        tenant_id=tenant_id,
        api_id=api_id,
        status=status,
        target_environment=target_environment,
        page=page,
        page_size=page_size,
    )
    return PromotionListResponse(
        items=[PromotionResponse.model_validate(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{promotion_id}", response_model=PromotionResponse)
@require_tenant_access
async def get_promotion(
    tenant_id: str,
    promotion_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get promotion details."""
    service = PromotionService(db)
    promotion = await service.get_promotion(tenant_id, promotion_id)
    if not promotion:
        raise HTTPException(status_code=404, detail="Promotion not found")
    return PromotionResponse.model_validate(promotion)


@router.get("/{promotion_id}/diff", response_model=PromotionDiffResponse)
@require_tenant_access
async def get_promotion_diff(
    tenant_id: str,
    promotion_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the spec diff between source and target environments."""
    service = PromotionService(db)
    try:
        diff = await service.get_diff(tenant_id, promotion_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return PromotionDiffResponse(**diff)


@router.post("/{promotion_id}/approve", response_model=PromotionResponse)
@require_permission(Permission.APIS_PROMOTE)
@require_tenant_access
async def approve_promotion(
    tenant_id: str,
    promotion_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve a pending promotion — triggers the promoting pipeline."""
    service = PromotionService(db)
    try:
        promotion = await service.approve_promotion(
            tenant_id=tenant_id,
            promotion_id=promotion_id,
            approved_by=user.username,
            user_id=user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return PromotionResponse.model_validate(promotion)


@router.post("/{promotion_id}/rollback", response_model=PromotionResponse, status_code=201)
@require_permission(Permission.APIS_PROMOTE)
@require_tenant_access
async def rollback_promotion(
    tenant_id: str,
    promotion_id: UUID,
    request: PromotionRollbackRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Rollback a completed promotion — creates a reverse promotion."""
    service = PromotionService(db)
    try:
        rollback = await service.rollback_promotion(
            tenant_id=tenant_id,
            promotion_id=promotion_id,
            message=request.message,
            requested_by=user.username,
            user_id=user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return PromotionResponse.model_validate(rollback)
