"""RBAC permissions and middleware"""
from functools import wraps

from fastapi import Depends, HTTPException

from .dependencies import get_current_user


class Role:
    """Role constants matching Keycloak realm roles"""
    CPI_ADMIN = "cpi-admin"
    TENANT_ADMIN = "tenant-admin"
    DEVOPS = "devops"
    VIEWER = "viewer"


class Permission:
    TENANTS_CREATE = "tenants:create"
    TENANTS_READ = "tenants:read"
    TENANTS_UPDATE = "tenants:update"
    TENANTS_DELETE = "tenants:delete"
    APIS_CREATE = "apis:create"
    APIS_READ = "apis:read"
    APIS_UPDATE = "apis:update"
    APIS_DELETE = "apis:delete"
    APIS_DEPLOY = "apis:deploy"
    APIS_PROMOTE = "apis:promote"
    APPS_CREATE = "apps:create"
    APPS_READ = "apps:read"
    APPS_UPDATE = "apps:update"
    APPS_DELETE = "apps:delete"
    USERS_MANAGE = "users:manage"
    AUDIT_READ = "audit:read"
    WORKFLOWS_READ = "workflows:read"
    WORKFLOWS_MANAGE = "workflows:manage"

ROLE_PERMISSIONS = {
    "cpi-admin": [
        Permission.TENANTS_CREATE, Permission.TENANTS_READ,
        Permission.TENANTS_UPDATE, Permission.TENANTS_DELETE,
        Permission.APIS_CREATE, Permission.APIS_READ,
        Permission.APIS_UPDATE, Permission.APIS_DELETE,
        Permission.APIS_DEPLOY, Permission.APIS_PROMOTE,
        Permission.APPS_CREATE, Permission.APPS_READ,
        Permission.APPS_UPDATE, Permission.APPS_DELETE,
        Permission.USERS_MANAGE, Permission.AUDIT_READ,
        Permission.WORKFLOWS_READ, Permission.WORKFLOWS_MANAGE,
    ],
    "tenant-admin": [
        Permission.TENANTS_READ,
        Permission.APIS_CREATE, Permission.APIS_READ,
        Permission.APIS_UPDATE, Permission.APIS_DELETE,
        Permission.APIS_DEPLOY, Permission.APIS_PROMOTE,
        Permission.APPS_CREATE, Permission.APPS_READ,
        Permission.APPS_UPDATE, Permission.APPS_DELETE,
        Permission.USERS_MANAGE, Permission.AUDIT_READ,
        Permission.WORKFLOWS_READ, Permission.WORKFLOWS_MANAGE,
    ],
    "devops": [
        Permission.TENANTS_READ,
        Permission.APIS_CREATE, Permission.APIS_READ, Permission.APIS_UPDATE,
        Permission.APIS_DEPLOY, Permission.APIS_PROMOTE,
        Permission.APPS_CREATE, Permission.APPS_READ, Permission.APPS_UPDATE,
        Permission.AUDIT_READ,
        Permission.WORKFLOWS_READ,
    ],
    "viewer": [
        Permission.TENANTS_READ,
        Permission.APIS_READ,
        Permission.APPS_READ,
        Permission.AUDIT_READ,
        Permission.WORKFLOWS_READ,
    ],
    # Additive persona roles (CAB-1634) — standalone permission sets
    "stoa.security": [
        Permission.TENANTS_READ,
        Permission.APIS_READ,
        Permission.APPS_READ,
        Permission.AUDIT_READ,
        Permission.WORKFLOWS_READ,
    ],
    "stoa.agent": [
        Permission.APIS_READ,
        Permission.APPS_READ,
    ],
}


# ---------------------------------------------------------------------------
# Persona role alias resolution (CAB-1634)
# ---------------------------------------------------------------------------

ROLE_ALIASES: dict[str, str] = {
    "stoa.admin": "cpi-admin",
    "stoa.product_owner": "tenant-admin",
    "stoa.developer": "devops",
    "stoa.consumer": "viewer",
}


def normalize_roles(raw_roles: list[str]) -> list[str]:
    """Resolve persona aliases while keeping originals for display.

    Example: ["stoa.admin"] → ["cpi-admin", "stoa.admin"]
    """
    result = set(raw_roles)
    for role in raw_roles:
        aliased = ROLE_ALIASES.get(role)
        if aliased:
            result.add(aliased)
    return sorted(result)


# ---------------------------------------------------------------------------
# Role metadata — human-readable display names (CAB-1634)
# ---------------------------------------------------------------------------

ROLE_METADATA: dict[str, dict] = {
    # Core roles
    "cpi-admin": {
        "display_name": "Platform Admin",
        "description": "Full platform access across all tenants",
        "scope": "platform",
        "category": "core",
    },
    "tenant-admin": {
        "display_name": "Workspace Admin",
        "description": "Full access within own tenant workspace",
        "scope": "tenant",
        "category": "core",
    },
    "devops": {
        "display_name": "DevOps Engineer",
        "description": "Deploy and manage APIs and applications",
        "scope": "tenant",
        "category": "core",
    },
    "viewer": {
        "display_name": "Viewer",
        "description": "Read-only access to APIs and applications",
        "scope": "tenant",
        "category": "core",
    },
    # Persona roles (aliases to core roles)
    "stoa.admin": {
        "display_name": "STOA Admin",
        "description": "Platform administrator (maps to Platform Admin)",
        "scope": "platform",
        "category": "persona",
        "inherits_from": "cpi-admin",
    },
    "stoa.product_owner": {
        "display_name": "Product Owner",
        "description": "API product lifecycle owner (maps to Workspace Admin)",
        "scope": "tenant",
        "category": "persona",
        "inherits_from": "tenant-admin",
    },
    "stoa.developer": {
        "display_name": "Developer",
        "description": "Build and deploy APIs (maps to DevOps)",
        "scope": "tenant",
        "category": "persona",
        "inherits_from": "devops",
    },
    "stoa.consumer": {
        "display_name": "Consumer",
        "description": "Consume and subscribe to APIs (maps to Viewer)",
        "scope": "tenant",
        "category": "persona",
        "inherits_from": "viewer",
    },
    # Additive roles (standalone permission sets)
    "stoa.security": {
        "display_name": "Security Auditor",
        "description": "Read-only audit and security monitoring",
        "scope": "tenant",
        "category": "additive",
    },
    "stoa.agent": {
        "display_name": "AI Agent",
        "description": "Machine-to-machine API and app discovery",
        "scope": "tenant",
        "category": "additive",
    },
}


def get_user_permissions(roles: list[str]) -> list[str]:
    permissions = set()
    for role in roles:
        if role in ROLE_PERMISSIONS:
            permissions.update(ROLE_PERMISSIONS[role])
    return list(permissions)

def require_permission(permission: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, user=Depends(get_current_user), **kwargs):
            user_permissions = get_user_permissions(user.roles)
            if permission not in user_permissions:
                raise HTTPException(
                    status_code=403,
                    detail=f"Permission denied: {permission} required"
                )
            return await func(*args, user=user, **kwargs)
        return wrapper
    return decorator

def require_tenant_access(func):
    @wraps(func)
    async def wrapper(*args, tenant_id: str, user=Depends(get_current_user), **kwargs):
        if "cpi-admin" in user.roles:
            return await func(*args, tenant_id=tenant_id, user=user, **kwargs)
        if user.tenant_id != tenant_id:
            raise HTTPException(
                status_code=403,
                detail="Access denied to this tenant"
            )
        return await func(*args, tenant_id=tenant_id, user=user, **kwargs)
    return wrapper


def require_role(allowed_roles: list[str]):
    """
    Dependency factory that checks if the user has one of the allowed roles.

    Usage:
        @router.post("/sync")
        async def trigger_sync(user: User = Depends(require_role(["cpi-admin", "devops"]))):
            ...
    """
    from .dependencies import User, get_current_user

    async def role_checker(user: User = Depends(get_current_user)) -> User:
        if not any(role in user.roles for role in allowed_roles):
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Required roles: {allowed_roles}"
            )
        return user

    return role_checker
