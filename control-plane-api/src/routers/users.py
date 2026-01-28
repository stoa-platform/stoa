# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""User profile and permissions endpoint.

CAB-XXX: Single source of truth for user permissions.
This endpoint allows frontends (Portal, Console) to fetch calculated
permissions without duplicating the role-to-permission mapping logic.
"""
from fastapi import APIRouter, Depends
from typing import List, Optional
from pydantic import BaseModel

from ..auth.dependencies import get_current_user, User
from ..auth.rbac import ROLE_PERMISSIONS, get_user_permissions

router = APIRouter(prefix="/v1", tags=["Users"])


class UserPermissionsResponse(BaseModel):
    """Permissions calculated for the authenticated user.

    This is the single source of truth for Portal and Console.
    """
    user_id: str
    email: str
    username: str
    tenant_id: Optional[str]
    roles: List[str]
    permissions: List[str]
    effective_scopes: List[str]

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                "email": "user@tenant.com",
                "username": "john.doe",
                "tenant_id": "acme",
                "roles": ["tenant-admin"],
                "permissions": [
                    "apis:create", "apis:read", "apis:update", "apis:delete",
                    "apis:deploy", "apis:promote", "apps:create", "apps:read",
                    "apps:update", "apps:delete", "audit:read", "tenants:read",
                    "users:manage"
                ],
                "effective_scopes": [
                    "stoa:catalog:read", "stoa:catalog:write",
                    "stoa:subscriptions:read", "stoa:subscriptions:write",
                    "stoa:metrics:read", "stoa:logs:functional", "stoa:logs:technical"
                ]
            }
        }


# Mapping legacy roles to OAuth2 scopes (aligned with mcp-gateway/src/policy/scopes.py)
ROLE_TO_SCOPES = {
    "cpi-admin": [
        "stoa:platform:read", "stoa:platform:write",
        "stoa:catalog:read", "stoa:catalog:write",
        "stoa:subscriptions:read", "stoa:subscriptions:write",
        "stoa:metrics:read",
        "stoa:logs:technical", "stoa:logs:functional", "stoa:logs:full",
        "stoa:security:read", "stoa:security:write",
        "stoa:admin:read", "stoa:admin:write",
        "stoa:tools:read", "stoa:tools:execute",
        "stoa:observability:read", "stoa:observability:write",
    ],
    "tenant-admin": [
        "stoa:catalog:read", "stoa:catalog:write",
        "stoa:subscriptions:read", "stoa:subscriptions:write",
        "stoa:metrics:read",
        "stoa:logs:technical", "stoa:logs:functional",
        "stoa:tools:read", "stoa:tools:execute",
        "stoa:observability:read",
    ],
    "devops": [
        "stoa:catalog:read", "stoa:catalog:write",
        "stoa:subscriptions:read",
        "stoa:metrics:read",
        "stoa:logs:technical",
        "stoa:tools:read", "stoa:tools:execute",
        "stoa:observability:read",
    ],
    "viewer": [
        "stoa:catalog:read",
        "stoa:subscriptions:read",
        "stoa:metrics:read",
        "stoa:tools:read",
    ],
    # New persona roles (CAB-604)
    "stoa.admin": [
        "stoa:catalog:read", "stoa:catalog:write",
        "stoa:subscription:read", "stoa:subscription:write",
        "stoa:observability:read", "stoa:observability:write",
        "stoa:tools:read", "stoa:tools:execute",
        "stoa:admin:read", "stoa:admin:write",
        "stoa:security:read", "stoa:security:write",
    ],
    "stoa.product_owner": [
        "stoa:catalog:read", "stoa:catalog:write",
        "stoa:subscription:read",
        "stoa:observability:read",
        "stoa:tools:read",
    ],
    "stoa.developer": [
        "stoa:catalog:read",
        "stoa:subscription:read", "stoa:subscription:write",
        "stoa:observability:read",
        "stoa:tools:read", "stoa:tools:execute",
    ],
    "stoa.consumer": [
        "stoa:catalog:read",
        "stoa:subscription:read", "stoa:subscription:write",
        "stoa:tools:read", "stoa:tools:execute",
    ],
    "stoa.security": [
        "stoa:catalog:read",
        "stoa:subscription:read",
        "stoa:observability:read",
        "stoa:security:read", "stoa:security:write",
        "stoa:admin:read",
        "stoa:tools:read",
    ],
    "stoa.agent": [
        "stoa:catalog:read",
        "stoa:tools:read", "stoa:tools:execute",
    ],
}


def get_effective_scopes(roles: List[str]) -> List[str]:
    """Calculate effective OAuth2 scopes from user roles.

    This aligns with mcp-gateway's get_scopes_for_roles() to ensure
    consistent authorization across all services.
    """
    scopes = set()
    for role in roles:
        if role in ROLE_TO_SCOPES:
            scopes.update(ROLE_TO_SCOPES[role])
    return sorted(list(scopes))


def filter_system_roles(roles: List[str]) -> List[str]:
    """Filter out Keycloak system roles."""
    system_prefixes = (
        "default-roles-",
        "offline_access",
        "uma_authorization",
    )
    return [r for r in roles if not r.startswith(system_prefixes)]


@router.get("/me", response_model=UserPermissionsResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
):
    """
    Get current user information and calculated permissions.

    This endpoint is the **single source of truth** for user permissions.
    Frontend applications (Portal, Console) should call this endpoint
    after authentication to get the user's permissions and scopes.

    **Response includes:**
    - `user_id`: Keycloak subject ID
    - `email`: User email
    - `username`: Preferred username
    - `tenant_id`: Associated tenant (may be null for platform admins)
    - `roles`: Keycloak realm roles (filtered, no system roles)
    - `permissions`: Granular permissions derived from roles (e.g., apis:read)
    - `effective_scopes`: OAuth2 scopes derived from roles (e.g., stoa:catalog:read)

    **Usage in Frontend:**
    ```typescript
    const { data } = await api.get('/v1/me');
    // Check permission: data.permissions.includes('apis:create')
    // Check scope: data.effective_scopes.includes('stoa:catalog:write')
    ```
    """
    # Filter system roles
    user_roles = filter_system_roles(current_user.roles)

    # Calculate permissions from roles
    permissions = get_user_permissions(user_roles)

    # Calculate OAuth2 scopes from roles
    scopes = get_effective_scopes(user_roles)

    return UserPermissionsResponse(
        user_id=current_user.id,
        email=current_user.email,
        username=current_user.username,
        tenant_id=current_user.tenant_id,
        roles=user_roles,
        permissions=sorted(permissions),
        effective_scopes=scopes,
    )
