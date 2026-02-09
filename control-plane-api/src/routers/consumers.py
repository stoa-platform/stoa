"""Consumers router - External API consumer management (CAB-1121)."""

import logging
import math
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import User, get_current_user
from ..database import get_db
from ..models.consumer import Consumer, ConsumerStatus
from ..repositories.consumer import ConsumerRepository
from ..schemas.consumer import (
    ConsumerCreate,
    ConsumerListResponse,
    ConsumerResponse,
    ConsumerStatusEnum,
    ConsumerUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/consumers", tags=["Consumers"])


def _has_tenant_access(user: User, tenant_id: str) -> bool:
    """Check if user has access to a tenant."""
    if "cpi-admin" in user.roles:
        return True
    return user.tenant_id == tenant_id


# ============== CRUD Endpoints ==============


@router.post("/{tenant_id}", response_model=ConsumerResponse, status_code=201)
async def create_consumer(
    tenant_id: str,
    request: ConsumerCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new consumer for a tenant."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = ConsumerRepository(db)

    # Check for duplicate external_id
    existing = await repo.get_by_external_id(tenant_id, request.external_id)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Consumer with external_id '{request.external_id}' already exists in this tenant",
        )

    consumer = Consumer(
        external_id=request.external_id,
        name=request.name,
        email=request.email,
        company=request.company,
        description=request.description,
        tenant_id=tenant_id,
        keycloak_user_id=request.keycloak_user_id,
        status=ConsumerStatus.ACTIVE,
        consumer_metadata=request.consumer_metadata,
        created_by=user.id,
    )

    try:
        consumer = await repo.create(consumer)
        logger.info(
            f"Created consumer {consumer.id} external_id={request.external_id} " f"tenant={tenant_id} by={user.email}"
        )
    except Exception as e:
        logger.error(f"Failed to create consumer: {e}")
        raise HTTPException(status_code=500, detail="Failed to create consumer")

    return ConsumerResponse.model_validate(consumer)


@router.get("/{tenant_id}", response_model=ConsumerListResponse)
async def list_consumers(
    tenant_id: str,
    status: ConsumerStatusEnum | None = None,
    search: str | None = Query(None, max_length=255),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List consumers for a tenant with optional filtering."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = ConsumerRepository(db)

    db_status = ConsumerStatus(status.value) if status else None
    consumers, total = await repo.list_by_tenant(
        tenant_id=tenant_id,
        status=db_status,
        search=search,
        page=page,
        page_size=page_size,
    )

    return ConsumerListResponse(
        items=[ConsumerResponse.model_validate(c) for c in consumers],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 1,
    )


@router.get("/{tenant_id}/{consumer_id}", response_model=ConsumerResponse)
async def get_consumer(
    tenant_id: str,
    consumer_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get consumer details by ID."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = ConsumerRepository(db)
    consumer = await repo.get_by_id(consumer_id)

    if not consumer:
        raise HTTPException(status_code=404, detail="Consumer not found")

    if consumer.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Consumer not found")

    return ConsumerResponse.model_validate(consumer)


@router.put("/{tenant_id}/{consumer_id}", response_model=ConsumerResponse)
async def update_consumer(
    tenant_id: str,
    consumer_id: UUID,
    request: ConsumerUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update consumer details."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = ConsumerRepository(db)
    consumer = await repo.get_by_id(consumer_id)

    if not consumer:
        raise HTTPException(status_code=404, detail="Consumer not found")

    if consumer.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Consumer not found")

    # Apply updates
    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(consumer, field, value)

    consumer = await repo.update(consumer)

    logger.info(f"Updated consumer {consumer_id} by {user.email}")

    return ConsumerResponse.model_validate(consumer)


@router.delete("/{tenant_id}/{consumer_id}", status_code=204)
async def delete_consumer(
    tenant_id: str,
    consumer_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a consumer."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = ConsumerRepository(db)
    consumer = await repo.get_by_id(consumer_id)

    if not consumer:
        raise HTTPException(status_code=404, detail="Consumer not found")

    if consumer.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Consumer not found")

    await repo.delete(consumer)

    logger.info(f"Deleted consumer {consumer_id} by {user.email}")


# ============== Status Management Endpoints ==============


@router.post("/{tenant_id}/{consumer_id}/suspend", response_model=ConsumerResponse)
async def suspend_consumer(
    tenant_id: str,
    consumer_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Suspend an active consumer."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = ConsumerRepository(db)
    consumer = await repo.get_by_id(consumer_id)

    if not consumer:
        raise HTTPException(status_code=404, detail="Consumer not found")

    if consumer.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Consumer not found")

    if consumer.status != ConsumerStatus.ACTIVE:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot suspend consumer in {consumer.status.value} status",
        )

    consumer = await repo.update_status(consumer, ConsumerStatus.SUSPENDED)
    logger.info(f"Consumer {consumer_id} suspended by {user.email}")

    return ConsumerResponse.model_validate(consumer)


@router.post("/{tenant_id}/{consumer_id}/activate", response_model=ConsumerResponse)
async def activate_consumer(
    tenant_id: str,
    consumer_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reactivate a suspended consumer."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = ConsumerRepository(db)
    consumer = await repo.get_by_id(consumer_id)

    if not consumer:
        raise HTTPException(status_code=404, detail="Consumer not found")

    if consumer.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Consumer not found")

    if consumer.status != ConsumerStatus.SUSPENDED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot activate consumer in {consumer.status.value} status",
        )

    consumer = await repo.update_status(consumer, ConsumerStatus.ACTIVE)
    logger.info(f"Consumer {consumer_id} activated by {user.email}")

    return ConsumerResponse.model_validate(consumer)


@router.post("/{tenant_id}/{consumer_id}/block", response_model=ConsumerResponse)
async def block_consumer(
    tenant_id: str,
    consumer_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Block a consumer (permanent until unblocked)."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = ConsumerRepository(db)
    consumer = await repo.get_by_id(consumer_id)

    if not consumer:
        raise HTTPException(status_code=404, detail="Consumer not found")

    if consumer.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Consumer not found")

    if consumer.status == ConsumerStatus.BLOCKED:
        raise HTTPException(status_code=400, detail="Consumer is already blocked")

    consumer = await repo.update_status(consumer, ConsumerStatus.BLOCKED)
    logger.info(f"Consumer {consumer_id} blocked by {user.email}")

    return ConsumerResponse.model_validate(consumer)
