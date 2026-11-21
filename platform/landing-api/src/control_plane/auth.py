"""Role and tenant checks for landing-api.

Access is denied unless the caller presents a known API key and the key's
role grants the permission. The presented key is hashed before lookup and
is never written to the log.
"""

import hmac
import logging
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.config import settings
from control_plane.database import get_db
from control_plane.models.api_key import ApiKey
from control_plane.services.api_key_service import hash_key

logger = logging.getLogger(__name__)

ROLE_CPI_ADMIN = "cpi-admin"
ROLE_TENANT_ADMIN = "tenant-admin"
ROLE_DEVOPS = "devops"
ROLE_VIEWER = "viewer"

PERM_LISTS_READ = "lists:read"
PERM_LISTS_WRITE = "lists:write"
PERM_KEYS_MANAGE = "keys:manage"

# devops is intentionally absent: deploy rights do not include personal data.
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    ROLE_CPI_ADMIN: frozenset({PERM_LISTS_READ, PERM_LISTS_WRITE, PERM_KEYS_MANAGE}),
    ROLE_TENANT_ADMIN: frozenset({PERM_LISTS_READ, PERM_LISTS_WRITE, PERM_KEYS_MANAGE}),
    ROLE_VIEWER: frozenset({PERM_LISTS_READ}),
    ROLE_DEVOPS: frozenset(),
}

ASSIGNABLE_ROLES = frozenset(ROLE_PERMISSIONS)


@dataclass(frozen=True, slots=True)
class Principal:
    """Authenticated caller. `key_id` is None for the bootstrap admin."""

    key_id: UUID | None
    tenant_id: str
    role: str

    def allows(self, permission: str) -> bool:
        return permission in ROLE_PERMISSIONS.get(self.role, frozenset())

    @property
    def is_platform_admin(self) -> bool:
        return self.role == ROLE_CPI_ADMIN


def _presented_key(request: Request) -> str | None:
    header = request.headers.get("x-api-key")
    if header and header.strip():
        return header.strip()
    authorization = request.headers.get("authorization")
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        return value.strip()
    return None


def _bootstrap_principal(raw_key: str) -> Principal | None:
    """Accept a key whose hash matches the configured digest. Empty disables it."""
    expected = settings.bootstrap_admin_key_hash.strip().lower()
    if len(expected) != 64:
        return None
    digest = hash_key(raw_key)
    if not hmac.compare_digest(digest, expected):
        return None
    tenant = settings.bootstrap_admin_tenant.strip() or "platform"
    return Principal(key_id=None, tenant_id=tenant, role=ROLE_CPI_ADMIN)


async def get_principal(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Principal:
    """Resolve the caller from `X-API-Key` or `Authorization: Bearer`."""
    raw = _presented_key(request)
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthenticated", "message": "Authentication required"},
        )

    digest = hash_key(raw)
    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == digest, ApiKey.revoked.is_(False))
    )
    record = result.scalar_one_or_none()
    if record is not None:
        return Principal(key_id=record.id, tenant_id=record.tenant_id, role=record.role)

    bootstrap = _bootstrap_principal(raw)
    if bootstrap is not None:
        return bootstrap

    logger.info("authentication rejected")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "invalid_api_key", "message": "Authentication required"},
    )


def require_permission(permission: str) -> Callable:
    """Dependency factory. Missing permission is 403, including unknown roles."""

    async def _dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.allows(permission):
            logger.info("access denied")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "forbidden", "message": "Insufficient role"},
            )
        return principal

    return _dependency


def assert_same_tenant(principal: Principal, resource_tenant: str) -> None:
    """Platform admins may cross tenants. Every other role may not."""
    if principal.is_platform_admin:
        return
    if principal.tenant_id != resource_tenant:
        logger.info("cross-tenant access denied")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "tenant_forbidden", "message": "Tenant access denied"},
        )


def resolve_tenant(principal: Principal, requested: str | None) -> str:
    """Pin non-admins to their own tenant. A foreign tenant is denied."""
    if principal.is_platform_admin:
        tenant = (requested or principal.tenant_id).strip()
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "tenant_required", "message": "Tenant is required"},
            )
        return tenant
    if requested and requested != principal.tenant_id:
        logger.info("cross-tenant access denied")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "tenant_forbidden", "message": "Tenant access denied"},
        )
    if not principal.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "tenant_forbidden", "message": "Tenant access denied"},
        )
    return principal.tenant_id
