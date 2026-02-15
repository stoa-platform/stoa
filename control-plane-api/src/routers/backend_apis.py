"""Backend APIs router — SaaS self-service API registration + scoped keys (CAB-1188/CAB-1249)."""

import hashlib
import logging
import secrets
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import User, get_current_user
from ..database import get_db
from ..models.backend_api import BackendApi, BackendApiStatus
from ..models.saas_api_key import SaasApiKey, SaasApiKeyStatus
from ..repositories.backend_api import BackendApiRepository, SaasApiKeyRepository
from ..schemas.backend_api import (
    BackendApiCreate,
    BackendApiListResponse,
    BackendApiResponse,
    BackendApiUpdate,
    SaasApiKeyCreate,
    SaasApiKeyCreatedResponse,
    SaasApiKeyListResponse,
    SaasApiKeyResponse,
)
from ..services.encryption_service import encrypt_auth_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/tenants/{tenant_id}/backend-apis", tags=["Backend APIs"])
keys_router = APIRouter(prefix="/v1/tenants/{tenant_id}/saas-keys", tags=["SaaS API Keys"])


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


def _to_response(api: BackendApi) -> BackendApiResponse:
    """Convert BackendApi model to response (never expose encrypted credentials)."""
    return BackendApiResponse(
        id=api.id,
        tenant_id=api.tenant_id,
        name=api.name,
        display_name=api.display_name,
        description=api.description,
        backend_url=api.backend_url,
        openapi_spec_url=api.openapi_spec_url,
        auth_type=api.auth_type,
        has_credentials=api.auth_config_encrypted is not None,
        status=api.status,
        tool_count=api.tool_count,
        spec_hash=api.spec_hash,
        last_synced_at=api.last_synced_at,
        created_at=api.created_at,
        updated_at=api.updated_at,
        created_by=api.created_by,
    )


# ============== Backend API Endpoints ==============


@router.post("", response_model=BackendApiResponse, status_code=201)
async def create_backend_api(
    tenant_id: str,
    request: BackendApiCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a new backend API for MCP exposure."""
    _require_write_access(user, tenant_id)
    repo = BackendApiRepository(db)

    existing = await repo.get_by_tenant_and_name(tenant_id, request.name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Backend API '{request.name}' already exists")

    encrypted_config = None
    if request.auth_config:
        encrypted_config = encrypt_auth_config(request.auth_config)

    api = BackendApi(
        tenant_id=tenant_id,
        name=request.name,
        display_name=request.display_name,
        description=request.description,
        backend_url=request.backend_url,
        openapi_spec_url=request.openapi_spec_url,
        auth_type=request.auth_type,
        auth_config_encrypted=encrypted_config,
        status=BackendApiStatus.DRAFT,
        created_by=user.id,
    )
    api = await repo.create(api)
    await db.commit()

    logger.info("Backend API created: %s/%s by %s", tenant_id, request.name, user.id)
    return _to_response(api)


@router.get("", response_model=BackendApiListResponse)
async def list_backend_apis(
    tenant_id: str,
    status: str | None = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List backend APIs for a tenant."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = BackendApiRepository(db)
    status_filter = BackendApiStatus(status) if status else None
    items, total = await repo.list_by_tenant(tenant_id, status=status_filter, page=page, page_size=page_size)

    return BackendApiListResponse(
        items=[_to_response(api) for api in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{api_id}", response_model=BackendApiResponse)
async def get_backend_api(
    tenant_id: str,
    api_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a backend API by ID."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = BackendApiRepository(db)
    api = await repo.get_by_id(api_id)
    if not api or api.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Backend API not found")

    return _to_response(api)


@router.patch("/{api_id}", response_model=BackendApiResponse)
async def update_backend_api(
    tenant_id: str,
    api_id: UUID,
    request: BackendApiUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a backend API."""
    _require_write_access(user, tenant_id)

    repo = BackendApiRepository(db)
    api = await repo.get_by_id(api_id)
    if not api or api.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Backend API not found")

    update_data = request.model_dump(exclude_unset=True)

    if "auth_config" in update_data:
        auth_config = update_data.pop("auth_config")
        if auth_config is not None:
            api.auth_config_encrypted = encrypt_auth_config(auth_config)
        else:
            api.auth_config_encrypted = None

    for field, value in update_data.items():
        setattr(api, field, value)

    api.updated_at = datetime.utcnow()
    api = await repo.update(api)
    await db.commit()

    logger.info("Backend API updated: %s/%s by %s", tenant_id, api.name, user.id)
    return _to_response(api)


@router.delete("/{api_id}", status_code=204)
async def delete_backend_api(
    tenant_id: str,
    api_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a backend API."""
    _require_write_access(user, tenant_id)

    repo = BackendApiRepository(db)
    api = await repo.get_by_id(api_id)
    if not api or api.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Backend API not found")

    await repo.delete(api)
    await db.commit()

    logger.info("Backend API deleted: %s/%s by %s", tenant_id, api.name, user.id)


# ============== Scoped API Key Endpoints ==============


def _generate_api_key() -> tuple[str, str, str]:
    """Generate a scoped API key.

    Returns:
        (plaintext_key, key_hash, key_prefix)
    """
    random_part = secrets.token_hex(32)
    prefix_hex = secrets.token_hex(2)
    prefix = f"stoa_saas_{prefix_hex}"
    plaintext = f"{prefix}_{random_part}"
    key_hash = hashlib.sha256(plaintext.encode()).hexdigest()
    return plaintext, key_hash, prefix


@keys_router.post("", response_model=SaasApiKeyCreatedResponse, status_code=201)
async def create_saas_api_key(
    tenant_id: str,
    request: SaasApiKeyCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a scoped API key. The plaintext key is returned only once."""
    _require_write_access(user, tenant_id)

    # Validate that all referenced backend APIs exist and belong to this tenant
    api_repo = BackendApiRepository(db)
    for backend_api_id in request.allowed_backend_api_ids:
        api = await api_repo.get_by_id(backend_api_id)
        if not api or api.tenant_id != tenant_id:
            raise HTTPException(
                status_code=400,
                detail=f"Backend API {backend_api_id} not found in this tenant",
            )

    key_repo = SaasApiKeyRepository(db)

    # Check name uniqueness
    items, _ = await key_repo.list_by_tenant(tenant_id, page=1, page_size=1000)
    if any(k.name == request.name for k in items):
        raise HTTPException(status_code=409, detail=f"API key name '{request.name}' already exists")

    plaintext, key_hash, prefix = _generate_api_key()

    api_key = SaasApiKey(
        tenant_id=tenant_id,
        name=request.name,
        description=request.description,
        key_hash=key_hash,
        key_prefix=prefix,
        allowed_backend_api_ids=[str(uid) for uid in request.allowed_backend_api_ids],
        rate_limit_rpm=request.rate_limit_rpm,
        expires_at=request.expires_at,
        created_by=user.id,
    )
    api_key = await key_repo.create(api_key)
    await db.commit()

    logger.info("SaaS API key created: %s/%s by %s", tenant_id, request.name, user.id)
    return SaasApiKeyCreatedResponse(
        id=api_key.id,
        name=api_key.name,
        key=plaintext,
        key_prefix=prefix,
    )


@keys_router.get("", response_model=SaasApiKeyListResponse)
async def list_saas_api_keys(
    tenant_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List scoped API keys for a tenant."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = SaasApiKeyRepository(db)
    items, total = await repo.list_by_tenant(tenant_id, page=page, page_size=page_size)

    return SaasApiKeyListResponse(
        items=[SaasApiKeyResponse.model_validate(k) for k in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@keys_router.get("/{key_id}", response_model=SaasApiKeyResponse)
async def get_saas_api_key(
    tenant_id: str,
    key_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a scoped API key by ID."""
    if not _has_tenant_access(user, tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    repo = SaasApiKeyRepository(db)
    api_key = await repo.get_by_id(key_id)
    if not api_key or api_key.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="API key not found")

    return SaasApiKeyResponse.model_validate(api_key)


@keys_router.delete("/{key_id}", status_code=204)
async def revoke_saas_api_key(
    tenant_id: str,
    key_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a scoped API key."""
    _require_write_access(user, tenant_id)

    repo = SaasApiKeyRepository(db)
    api_key = await repo.get_by_id(key_id)
    if not api_key or api_key.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="API key not found")

    api_key.status = SaasApiKeyStatus.REVOKED
    api_key.revoked_at = datetime.utcnow()
    api_key.updated_at = datetime.utcnow()
    await repo.update(api_key)
    await db.commit()

    logger.info("SaaS API key revoked: %s/%s by %s", tenant_id, api_key.name, user.id)
