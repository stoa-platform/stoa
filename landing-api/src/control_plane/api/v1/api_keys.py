"""API key endpoints.

The plaintext key is returned only by the create endpoint. Later reads
return metadata (id, name, role, tenant, prefix) and nothing else.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.auth import (
    ASSIGNABLE_ROLES,
    PERM_KEYS_MANAGE,
    ROLE_CPI_ADMIN,
    Principal,
    assert_same_tenant,
    require_permission,
    resolve_tenant,
)
from control_plane.database import get_db
from control_plane.models.api_key import ApiKey
from control_plane.schemas.api_key import (
    ApiKeyCreate,
    ApiKeyCreatedResponse,
    ApiKeyListResponse,
    ApiKeyPublic,
)
from control_plane.services import api_key_service

router = APIRouter(prefix="/api-keys", tags=["api-keys"])
logger = logging.getLogger(__name__)


def _public(record: ApiKey) -> ApiKeyPublic:
    return ApiKeyPublic(
        id=record.id,
        name=record.name,
        role=record.role,
        tenant_id=record.tenant_id,
        key_prefix=record.key_prefix,
        created_at=record.created_at,
    )


@router.post(
    "",
    response_model=ApiKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an API key",
    description="Issue an API key. The secret is returned once and stored as a hash.",
)
async def create_key(
    payload: ApiKeyCreate,
    principal: Principal = Depends(require_permission(PERM_KEYS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyCreatedResponse:
    """Issue a key for an allowed role inside the caller's tenant."""
    if payload.role not in ASSIGNABLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_role", "message": "Unknown role"},
        )
    if payload.role == ROLE_CPI_ADMIN and not principal.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "forbidden", "message": "Insufficient role"},
        )

    tenant_id = resolve_tenant(principal, payload.tenant_id)
    record, raw_key = await api_key_service.create_api_key(
        db,
        name=payload.name,
        role=payload.role,
        tenant_id=tenant_id,
    )
    logger.info("api key created id=%s", record.id)
    return ApiKeyCreatedResponse(**_public(record).model_dump(), api_key=raw_key)


@router.get(
    "",
    response_model=ApiKeyListResponse,
    summary="List API keys",
    description="List key metadata for the caller's tenant. Secrets are not included.",
)
async def list_keys(
    principal: Principal = Depends(require_permission(PERM_KEYS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyListResponse:
    """List keys. Platform admins see every tenant; others see their own."""
    query = select(ApiKey).order_by(ApiKey.created_at.desc())
    if not principal.is_platform_admin:
        query = query.where(ApiKey.tenant_id == principal.tenant_id)
    result = await db.execute(query)
    records = list(result.scalars().all())
    return ApiKeyListResponse(
        api_keys=[_public(record) for record in records],
        total=len(records),
    )


@router.get(
    "/{key_id}",
    response_model=ApiKeyPublic,
    summary="Get API key metadata",
    description="Return key metadata. The secret is never included.",
)
async def get_key(
    key_id: UUID,
    principal: Principal = Depends(require_permission(PERM_KEYS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyPublic:
    """Return one key's metadata after a tenant check."""
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id))
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "api_key_not_found", "message": "API key not found"},
        )
    assert_same_tenant(principal, record.tenant_id)
    return _public(record)
