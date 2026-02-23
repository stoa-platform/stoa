"""Credential mapping router — per-consumer backend credential injection (CAB-1432)."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import User, get_current_user
from ..database import get_db
from ..models.credential_mapping import CredentialAuthType, CredentialMapping
from ..repositories.credential_mapping import CredentialMappingRepository
from ..schemas.credential_mapping import (
    CredentialMappingCreate,
    CredentialMappingListResponse,
    CredentialMappingResponse,
    CredentialMappingSyncItem,
    CredentialMappingUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/tenants/{tenant_id}/credential-mappings",
    tags=["Credential Mappings"],
)


def _has_tenant_access(user: User, tenant_id: str) -> bool:
    """Check if user has access to a tenant."""
    if "cpi-admin" in user.roles:
        return True
    return user.tenant_id == tenant_id


def _require_write_access(user: User, tenant_id: str) -> None:
    """Require write access (tenant-admin or cpi-admin)."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")
    if "cpi-admin" not in user.roles and "tenant-admin" not in user.roles:
        raise HTTPException(status_code=403, detail="Write access requires tenant-admin or cpi-admin role")


def _require_admin_access(user: User) -> None:
    """Require cpi-admin role (for sync endpoint)."""
    if "cpi-admin" not in user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")


def _to_response(mapping: CredentialMapping) -> CredentialMappingResponse:
    """Convert model to response (never expose encrypted value)."""
    return CredentialMappingResponse(
        id=mapping.id,  # type: ignore[arg-type]
        consumer_id=mapping.consumer_id,  # type: ignore[arg-type]
        api_id=mapping.api_id,  # type: ignore[arg-type]
        tenant_id=mapping.tenant_id,  # type: ignore[arg-type]
        auth_type=mapping.auth_type.value if hasattr(mapping.auth_type, "value") else str(mapping.auth_type),  # type: ignore[arg-type]
        header_name=mapping.header_name,  # type: ignore[arg-type]
        has_credential=mapping.encrypted_value is not None,
        description=mapping.description,  # type: ignore[arg-type]
        is_active=mapping.is_active,  # type: ignore[arg-type]
        created_at=mapping.created_at,  # type: ignore[arg-type]
        updated_at=mapping.updated_at,  # type: ignore[arg-type]
        created_by=mapping.created_by,  # type: ignore[arg-type]
    )


@router.post("", response_model=CredentialMappingResponse, status_code=201)
async def create_credential_mapping(
    tenant_id: str,
    request: CredentialMappingCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new credential mapping for a consumer + API pair."""
    _require_write_access(user, tenant_id)

    repo = CredentialMappingRepository(db)

    # Check uniqueness
    existing = await repo.get_by_consumer_and_api(request.consumer_id, request.api_id)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Credential mapping already exists for consumer {request.consumer_id} and API {request.api_id}",
        )

    # Encrypt the credential value
    encrypted = CredentialMappingRepository.encrypt_credential(request.credential_value)

    mapping = CredentialMapping(
        consumer_id=request.consumer_id,
        api_id=request.api_id,
        tenant_id=tenant_id,
        auth_type=CredentialAuthType(request.auth_type.value),
        header_name=request.header_name,
        encrypted_value=encrypted,
        description=request.description,
        created_by=user.id,
    )
    mapping = await repo.create(mapping)
    await db.commit()

    logger.info(
        "Credential mapping created: tenant=%s consumer=%s api=%s by=%s",
        tenant_id,
        request.consumer_id,
        request.api_id,
        user.id,
    )
    return _to_response(mapping)


@router.get("", response_model=CredentialMappingListResponse)
async def list_credential_mappings(
    tenant_id: str,
    consumer_id: UUID | None = Query(None, description="Filter by consumer ID"),
    api_id: str | None = Query(None, description="Filter by API ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List credential mappings for a tenant."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = CredentialMappingRepository(db)
    items, total = await repo.list_by_tenant(
        tenant_id, consumer_id=consumer_id, api_id=api_id, page=page, page_size=page_size
    )

    return CredentialMappingListResponse(
        items=[_to_response(m) for m in items],
        total=total,
        page=page,
        page_size=page_size,
    )


# Sync endpoint MUST be declared before /{mapping_id} routes to avoid
# FastAPI matching "sync" as a UUID path parameter.
@router.get("/sync/{gateway_instance_id}", response_model=list[CredentialMappingSyncItem])
async def sync_credential_mappings(
    tenant_id: str,
    gateway_instance_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulk export active credential mappings for gateway sync (admin-only, decrypted)."""
    _require_admin_access(user)

    repo = CredentialMappingRepository(db)
    sync_items = await repo.list_active_for_sync(tenant_id)

    logger.info(
        "Credential mappings synced: tenant=%s gateway=%s count=%d by=%s",
        tenant_id,
        gateway_instance_id,
        len(sync_items),
        user.id,
    )
    return [CredentialMappingSyncItem(**item) for item in sync_items]


@router.get("/{mapping_id}", response_model=CredentialMappingResponse)
async def get_credential_mapping(
    tenant_id: str,
    mapping_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a credential mapping by ID."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = CredentialMappingRepository(db)
    mapping = await repo.get_by_id(mapping_id)
    if not mapping or mapping.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Credential mapping not found")

    return _to_response(mapping)


@router.put("/{mapping_id}", response_model=CredentialMappingResponse)
async def update_credential_mapping(
    tenant_id: str,
    mapping_id: UUID,
    request: CredentialMappingUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a credential mapping."""
    _require_write_access(user, tenant_id)

    repo = CredentialMappingRepository(db)
    mapping = await repo.get_by_id(mapping_id)
    if not mapping or mapping.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Credential mapping not found")

    if request.auth_type is not None:
        mapping.auth_type = CredentialAuthType(request.auth_type.value)  # type: ignore[assignment]
    if request.header_name is not None:
        mapping.header_name = request.header_name  # type: ignore[assignment]
    if request.credential_value is not None:
        mapping.encrypted_value = CredentialMappingRepository.encrypt_credential(request.credential_value)  # type: ignore[assignment]
    if request.description is not None:
        mapping.description = request.description  # type: ignore[assignment]
    if request.is_active is not None:
        mapping.is_active = request.is_active  # type: ignore[assignment]

    mapping = await repo.update(mapping)
    await db.commit()

    logger.info(
        "Credential mapping updated: %s tenant=%s by=%s",
        mapping_id,
        tenant_id,
        user.id,
    )
    return _to_response(mapping)


@router.delete("/{mapping_id}", status_code=204)
async def delete_credential_mapping(
    tenant_id: str,
    mapping_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a credential mapping (soft delete — sets is_active=false)."""
    _require_write_access(user, tenant_id)

    repo = CredentialMappingRepository(db)
    mapping = await repo.get_by_id(mapping_id)
    if not mapping or mapping.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Credential mapping not found")

    mapping.is_active = False  # type: ignore[assignment]
    await repo.update(mapping)
    await db.commit()

    logger.info(
        "Credential mapping deactivated: %s tenant=%s by=%s",
        mapping_id,
        tenant_id,
        user.id,
    )
