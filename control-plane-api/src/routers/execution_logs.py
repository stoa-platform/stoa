"""Execution logs router — Consumer execution view + error taxonomy (CAB-1318)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import User, get_current_user
from ..database import get_db
from ..models.execution_log import ErrorCategory, ExecutionStatus
from ..repositories.execution_log import ExecutionLogRepository
from ..schemas.execution_log import (
    ErrorCategoryEnum,
    ErrorTaxonomyResponse,
    ExecutionLogListResponse,
    ExecutionLogResponse,
    ExecutionLogSummary,
    ExecutionStatusEnum,
    TaxonomyItem,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Execution Logs"])


def _has_tenant_access(user: User, tenant_id: str) -> bool:
    """Check if user has access to a tenant."""
    if "cpi-admin" in user.roles:
        return True
    return user.tenant_id == tenant_id


# ============== Admin Endpoints (tenant-scoped) ==============


@router.get(
    "/v1/tenants/{tenant_id}/executions",
    response_model=ExecutionLogListResponse,
)
async def list_executions(
    tenant_id: str,
    status: ExecutionStatusEnum | None = None,
    error_category: ErrorCategoryEnum | None = None,
    consumer_id: str | None = None,
    api_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List executions for a tenant (paginated, filtered)."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = ExecutionLogRepository(db)
    db_status = ExecutionStatus(status.value) if status else None
    db_category = ErrorCategory(error_category.value) if error_category else None

    logs, total = await repo.list_by_tenant(
        tenant_id=tenant_id,
        status=db_status,
        error_category=db_category,
        consumer_id=consumer_id,
        api_id=api_id,
        page=page,
        page_size=page_size,
    )

    return ExecutionLogListResponse(
        items=[ExecutionLogSummary.model_validate(log) for log in logs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/v1/tenants/{tenant_id}/executions/taxonomy",
    response_model=ErrorTaxonomyResponse,
)
async def get_execution_taxonomy(
    tenant_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get error taxonomy aggregate for a tenant."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = ExecutionLogRepository(db)
    items, total_errors, total_executions = await repo.get_taxonomy(tenant_id=tenant_id)

    error_rate = round((total_errors / total_executions) * 100, 1) if total_executions > 0 else 0

    return ErrorTaxonomyResponse(
        items=[TaxonomyItem(**item) for item in items],
        total_errors=total_errors,
        total_executions=total_executions,
        error_rate=error_rate,
    )


@router.get(
    "/v1/tenants/{tenant_id}/executions/{execution_id}",
    response_model=ExecutionLogResponse,
)
async def get_execution_detail(
    tenant_id: str,
    execution_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get full execution detail."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = ExecutionLogRepository(db)
    log = await repo.get_by_id(execution_id)

    if not log or log.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Execution log not found")

    return ExecutionLogResponse.model_validate(log)


# ============== Portal Endpoints (consumer-scoped) ==============


@router.get(
    "/v1/usage/me/executions",
    response_model=ExecutionLogListResponse,
)
async def list_my_executions(
    status: ExecutionStatusEnum | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List my executions (portal user, consumer-scoped)."""
    if not user.consumer_id:
        return ExecutionLogListResponse(items=[], total=0, page=page, page_size=page_size)

    repo = ExecutionLogRepository(db)
    db_status = ExecutionStatus(status.value) if status else None

    logs, total = await repo.list_by_consumer(
        consumer_id=user.consumer_id,
        status=db_status,
        page=page,
        page_size=page_size,
    )

    return ExecutionLogListResponse(
        items=[ExecutionLogSummary.model_validate(log) for log in logs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/v1/usage/me/executions/taxonomy",
    response_model=ErrorTaxonomyResponse,
)
async def get_my_execution_taxonomy(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get my error taxonomy (portal user, consumer-scoped)."""
    if not user.consumer_id:
        return ErrorTaxonomyResponse(items=[], total_errors=0, total_executions=0, error_rate=0)

    repo = ExecutionLogRepository(db)
    items, total_errors, total_executions = await repo.get_taxonomy(
        tenant_id=user.tenant_id,
        consumer_id=user.consumer_id,
    )

    error_rate = round((total_errors / total_executions) * 100, 1) if total_executions > 0 else 0

    return ErrorTaxonomyResponse(
        items=[TaxonomyItem(**item) for item in items],
        total_errors=total_errors,
        total_executions=total_executions,
        error_rate=error_rate,
    )
