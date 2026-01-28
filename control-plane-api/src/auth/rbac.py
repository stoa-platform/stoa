# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""RBAC permissions and middleware"""
from functools import wraps
from fastapi import HTTPException, Depends
from typing import List
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
    ],
    "tenant-admin": [
        Permission.TENANTS_READ,
        Permission.APIS_CREATE, Permission.APIS_READ,
        Permission.APIS_UPDATE, Permission.APIS_DELETE,
        Permission.APIS_DEPLOY, Permission.APIS_PROMOTE,
        Permission.APPS_CREATE, Permission.APPS_READ,
        Permission.APPS_UPDATE, Permission.APPS_DELETE,
        Permission.USERS_MANAGE, Permission.AUDIT_READ,
    ],
    "devops": [
        Permission.TENANTS_READ,
        Permission.APIS_CREATE, Permission.APIS_READ, Permission.APIS_UPDATE,
        Permission.APIS_DEPLOY, Permission.APIS_PROMOTE,
        Permission.APPS_CREATE, Permission.APPS_READ, Permission.APPS_UPDATE,
        Permission.AUDIT_READ,
    ],
    "viewer": [
        Permission.TENANTS_READ,
        Permission.APIS_READ,
        Permission.APPS_READ,
        Permission.AUDIT_READ,
    ],
}

def get_user_permissions(roles: List[str]) -> List[str]:
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


def require_role(allowed_roles: List[str]):
    """
    Dependency factory that checks if the user has one of the allowed roles.

    Usage:
        @router.post("/sync")
        async def trigger_sync(user: User = Depends(require_role(["cpi-admin", "devops"]))):
            ...
    """
    from .dependencies import get_current_user, User

    async def role_checker(user: User = Depends(get_current_user)) -> User:
        if not any(role in user.roles for role in allowed_roles):
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Required roles: {allowed_roles}"
            )
        return user

    return role_checker
