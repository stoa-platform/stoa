"""Tenant tool permissions CRUD router (CAB-1980).

Endpoints:
- GET    /v1/tenants/{tenant_id}/tool-permissions — list permissions
- POST   /v1/tenants/{tenant_id}/tool-permissions — create/upsert permission
- DELETE /v1/tenants/{tenant_id}/tool-permissions/{permission_id} — delete

RBAC: stoa:read for list, stoa:write for create/delete. Tenant-scoped.
"""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import User, get_current_user, require_role
from ..database import get_db
from ..models.tenant_tool_permission import TenantToolPermission
from ..schemas.tenant_tool_permission import (
    TenantToolPermissionCreate,
    TenantToolPermissionListResponse,
    TenantToolPermissionResponse,
)
from ..services.cache_service import TTLCache

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/tenants/{tenant_id}/tool-permissions",
    tags=["Tenant Tool Permissions"],
)

# In-memory cache: key = "tenant:{tenant_id}" → dict[tuple(server_id, tool_name), bool]
_permission_cache = TTLCache(default_ttl_seconds=60, max_size=5000)


async def _invalidate_cache(tenant_id: str) -> None:
    """Invalidate cached permissions for a tenant."""
    await _permission_cache.delete(f"tenant:{tenant_id}")


async def _load_permission_cache(
    tenant_id: str, db: AsyncSession
) -> dict[tuple[str, str], bool]:
    """Load all permissions for a tenant into cache."""
    cache_key = f"tenant:{tenant_id}"
    cached = await _permission_cache.get(cache_key)
    if cached is not None:
        return cached

    result = await db.execute(
        select(TenantToolPermission).where(
            TenantToolPermission.tenant_id == tenant_id
        )
    )
    permissions = result.scalars().all()

    permission_map: dict[tuple[str, str], bool] = {}
    for perm in permissions:
        permission_map[(str(perm.mcp_server_id), perm.tool_name)] = perm.allowed

    await _permission_cache.set(cache_key, permission_map, ttl_seconds=60)
    return permission_map


async def check_tool_allowed(
    tenant_id: str,
    tool_name: str,
    db: AsyncSession,
    mcp_server_id: uuid.UUID | None = None,
) -> bool:
    """Check if a tool is allowed for a tenant. Returns True if allowed.

    Uses in-memory cache with 60s TTL. Default-allow: if no permission
    row exists, the tool is allowed.

    If mcp_server_id is provided, checks the specific (server, tool) pair.
    If not, checks if ANY server has this tool denied for the tenant.
    """
    permission_map = await _load_permission_cache(tenant_id, db)

    if mcp_server_id:
        return permission_map.get((str(mcp_server_id), tool_name), True)

    # No server_id — check all servers for this tool_name
    return all(
        allowed or tname != tool_name
        for (_sid, tname), allowed in permission_map.items()
    )


def _ensure_tenant_access(user: User, tenant_id: str) -> None:
    """Verify user has access to the tenant."""
    if "cpi-admin" in user.roles:
        return
    if user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to this tenant")


@router.get(
    "",
    response_model=TenantToolPermissionListResponse,
    summary="List tool permissions for tenant",
)
async def list_permissions(
    tenant_id: str,
    mcp_server_id: uuid.UUID | None = Query(None, description="Filter by MCP server"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TenantToolPermissionListResponse:
    """List tool permissions for a tenant. Requires stoa:read."""
    _ensure_tenant_access(user, tenant_id)

    query = select(TenantToolPermission).where(
        TenantToolPermission.tenant_id == tenant_id
    )
    count_query = select(TenantToolPermission).where(
        TenantToolPermission.tenant_id == tenant_id
    )

    if mcp_server_id:
        query = query.where(TenantToolPermission.mcp_server_id == mcp_server_id)
        count_query = count_query.where(
            TenantToolPermission.mcp_server_id == mcp_server_id
        )

    # Count total
    from sqlalchemy import func

    total_result = await db.execute(
        count_query.with_only_columns(func.count(TenantToolPermission.id))
    )
    total = total_result.scalar() or 0

    # Paginate
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = result.scalars().all()

    return TenantToolPermissionListResponse(
        items=[TenantToolPermissionResponse.model_validate(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=TenantToolPermissionResponse,
    status_code=201,
    summary="Create or update a tool permission",
)
async def create_permission(
    tenant_id: str,
    body: TenantToolPermissionCreate,
    user: User = Depends(require_role(["cpi-admin", "tenant-admin"])),
    db: AsyncSession = Depends(get_db),
) -> TenantToolPermissionResponse:
    """Create or update a tool permission (upsert). Requires stoa:write."""
    _ensure_tenant_access(user, tenant_id)

    now = datetime.now(UTC)

    # Check for existing permission (upsert)
    result = await db.execute(
        select(TenantToolPermission).where(
            TenantToolPermission.tenant_id == tenant_id,
            TenantToolPermission.mcp_server_id == body.mcp_server_id,
            TenantToolPermission.tool_name == body.tool_name,
        )
    )
    existing = result.scalars().first()

    if existing:
        existing.allowed = body.allowed
        existing.updated_at = now
        permission = existing
    else:
        permission = TenantToolPermission(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            mcp_server_id=body.mcp_server_id,
            tool_name=body.tool_name,
            allowed=body.allowed,
            created_by=user.id,
            created_at=now,
            updated_at=now,
        )
        db.add(permission)

    await db.commit()
    await db.refresh(permission)

    await _invalidate_cache(tenant_id)

    logger.info(
        "Tool permission upserted: tenant=%s server=%s tool=%s allowed=%s by=%s",
        tenant_id,
        body.mcp_server_id,
        body.tool_name,
        body.allowed,
        user.email,
    )

    return TenantToolPermissionResponse.model_validate(permission)


@router.delete(
    "/{permission_id}",
    status_code=204,
    summary="Delete a tool permission",
)
async def delete_permission(
    tenant_id: str,
    permission_id: uuid.UUID,
    user: User = Depends(require_role(["cpi-admin", "tenant-admin"])),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a tool permission (reverts to default-allow). Requires stoa:write."""
    _ensure_tenant_access(user, tenant_id)

    result = await db.execute(
        select(TenantToolPermission).where(
            TenantToolPermission.id == permission_id,
            TenantToolPermission.tenant_id == tenant_id,
        )
    )
    permission = result.scalars().first()

    if not permission:
        raise HTTPException(status_code=404, detail="Permission not found")

    await db.execute(
        delete(TenantToolPermission).where(
            TenantToolPermission.id == permission_id
        )
    )
    await db.commit()
    await _invalidate_cache(tenant_id)

    logger.info(
        "Tool permission deleted: tenant=%s tool=%s by=%s",
        tenant_id,
        permission.tool_name,
        user.email,
    )
