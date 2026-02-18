"""User profile and permissions endpoint.

CAB-XXX: Single source of truth for user permissions.
This endpoint allows frontends (Portal, Console) to fetch calculated
permissions without duplicating the role-to-permission mapping logic.
"""

import hashlib
import logging
import re
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import User, get_current_user
from ..auth.rbac import get_user_permissions
from ..database import get_db
from ..models.saas_api_key import SaasApiKey
from ..models.tenant import Tenant, TenantStatus
from ..repositories.backend_api import SaasApiKeyRepository
from ..repositories.tenant import TenantRepository
from ..services.kafka_service import kafka_service
from ..services.keycloak_service import keycloak_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["Users"])


class UserPermissionsResponse(BaseModel):
    """Permissions calculated for the authenticated user.

    This is the single source of truth for Portal and Console.
    """

    user_id: str
    email: str
    username: str
    tenant_id: str | None
    roles: list[str]
    permissions: list[str]
    effective_scopes: list[str]

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                "email": "user@tenant.com",
                "username": "john.doe",
                "tenant_id": "acme",
                "roles": ["tenant-admin"],
                "permissions": [
                    "apis:create",
                    "apis:read",
                    "apis:update",
                    "apis:delete",
                    "apis:deploy",
                    "apis:promote",
                    "apps:create",
                    "apps:read",
                    "apps:update",
                    "apps:delete",
                    "audit:read",
                    "tenants:read",
                    "users:manage",
                ],
                "effective_scopes": [
                    "stoa:catalog:read",
                    "stoa:catalog:write",
                    "stoa:subscriptions:read",
                    "stoa:subscriptions:write",
                    "stoa:metrics:read",
                    "stoa:logs:functional",
                    "stoa:logs:technical",
                ],
            }
        }


# Mapping legacy roles to OAuth2 scopes (aligned with mcp-gateway/src/policy/scopes.py)
ROLE_TO_SCOPES = {
    "cpi-admin": [
        "stoa:platform:read",
        "stoa:platform:write",
        "stoa:catalog:read",
        "stoa:catalog:write",
        "stoa:subscriptions:read",
        "stoa:subscriptions:write",
        "stoa:metrics:read",
        "stoa:logs:technical",
        "stoa:logs:functional",
        "stoa:logs:full",
        "stoa:security:read",
        "stoa:security:write",
        "stoa:admin:read",
        "stoa:admin:write",
        "stoa:tools:read",
        "stoa:tools:execute",
        "stoa:observability:read",
        "stoa:observability:write",
    ],
    "tenant-admin": [
        "stoa:catalog:read",
        "stoa:catalog:write",
        "stoa:subscriptions:read",
        "stoa:subscriptions:write",
        "stoa:metrics:read",
        "stoa:logs:technical",
        "stoa:logs:functional",
        "stoa:tools:read",
        "stoa:tools:execute",
        "stoa:observability:read",
    ],
    "devops": [
        "stoa:catalog:read",
        "stoa:catalog:write",
        "stoa:subscriptions:read",
        "stoa:metrics:read",
        "stoa:logs:technical",
        "stoa:tools:read",
        "stoa:tools:execute",
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
        "stoa:catalog:read",
        "stoa:catalog:write",
        "stoa:subscription:read",
        "stoa:subscription:write",
        "stoa:observability:read",
        "stoa:observability:write",
        "stoa:tools:read",
        "stoa:tools:execute",
        "stoa:admin:read",
        "stoa:admin:write",
        "stoa:security:read",
        "stoa:security:write",
    ],
    "stoa.product_owner": [
        "stoa:catalog:read",
        "stoa:catalog:write",
        "stoa:subscription:read",
        "stoa:observability:read",
        "stoa:tools:read",
    ],
    "stoa.developer": [
        "stoa:catalog:read",
        "stoa:subscription:read",
        "stoa:subscription:write",
        "stoa:observability:read",
        "stoa:tools:read",
        "stoa:tools:execute",
    ],
    "stoa.consumer": [
        "stoa:catalog:read",
        "stoa:subscription:read",
        "stoa:subscription:write",
        "stoa:tools:read",
        "stoa:tools:execute",
    ],
    "stoa.security": [
        "stoa:catalog:read",
        "stoa:subscription:read",
        "stoa:observability:read",
        "stoa:security:read",
        "stoa:security:write",
        "stoa:admin:read",
        "stoa:tools:read",
    ],
    "stoa.agent": [
        "stoa:catalog:read",
        "stoa:tools:read",
        "stoa:tools:execute",
    ],
}


def get_effective_scopes(roles: list[str]) -> list[str]:
    """Calculate effective OAuth2 scopes from user roles.

    This aligns with mcp-gateway's get_scopes_for_roles() to ensure
    consistent authorization across all services.
    """
    scopes = set()
    for role in roles:
        if role in ROLE_TO_SCOPES:
            scopes.update(ROLE_TO_SCOPES[role])
    return sorted(scopes)


def filter_system_roles(roles: list[str]) -> list[str]:
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

    # Self-registered users have no STOA role — default to viewer (read-only access)
    known_roles = set(ROLE_TO_SCOPES.keys())
    if not any(r in known_roles for r in user_roles):
        user_roles = ["viewer"]

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


class PersonalTenantResponse(BaseModel):
    """Response for personal tenant provisioning."""

    tenant_id: str
    display_name: str
    created: bool
    trial_api_key: str | None = None  # Plaintext returned once (CAB-1325)


def _sanitize_slug(username: str) -> str:
    """Convert username to a valid tenant slug."""
    slug = username.lower().strip()
    slug = re.sub(r"[^a-z0-9-]", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:50] if slug else "user"


@router.post("/me/tenant", response_model=PersonalTenantResponse, status_code=201)
async def provision_personal_tenant(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Provision a personal tenant for a self-registered user.

    No permission required — any authenticated user without a tenant can call this.
    Idempotent: returns existing tenant if user already has one.
    """
    repo = TenantRepository(db)

    # Idempotent: if user already has a tenant, return it
    if current_user.tenant_id:
        existing = await repo.get_by_id(current_user.tenant_id)
        if existing:
            return PersonalTenantResponse(
                tenant_id=existing.id,
                display_name=existing.name,
                created=False,
            )

    # Generate slug from username
    base_slug = f"free-{_sanitize_slug(current_user.username)}"
    tenant_id = base_slug

    # Handle slug collisions (up to 3 retries)
    for _ in range(3):
        existing = await repo.get_by_id(tenant_id)
        if not existing:
            break
        tenant_id = f"{base_slug}-{secrets.token_hex(2)}"
    else:
        raise HTTPException(status_code=409, detail="Could not generate unique tenant ID")

    # Create tenant in DB
    tenant = Tenant(
        id=tenant_id,
        name=f"{current_user.username}'s workspace",
        description="Personal tenant (auto-provisioned)",
        status=TenantStatus.ACTIVE.value,
        settings={
            "personal": True,
            "owner_user_id": current_user.id,
            "owner_email": current_user.email,
        },
    )
    tenant = await repo.create(tenant)

    # Keycloak: create group + assign user + assign viewer role
    try:
        await keycloak_service.setup_tenant_group(tenant_id, tenant.name)
    except Exception as e:
        logger.warning(f"Failed to create KC group for {tenant_id}: {e}")

    try:
        await keycloak_service.add_user_to_tenant(current_user.id, tenant_id)
    except Exception as e:
        logger.warning(f"Failed to add user to tenant {tenant_id}: {e}")

    try:
        await keycloak_service.assign_role(current_user.id, "viewer")
    except Exception as e:
        logger.warning(f"Failed to assign viewer role: {e}")

    # Audit event (non-blocking)
    try:
        await kafka_service.emit_audit_event(
            tenant_id=tenant_id,
            action="create",
            resource_type="tenant",
            resource_id=tenant_id,
            user_id=current_user.id,
            details={"personal": True, "trigger": "self-registration"},
        )
    except Exception as e:
        logger.warning(f"Failed to emit audit event: {e}")

    # Best-effort trial API key generation (CAB-1325)
    trial_key_plaintext: str | None = None
    try:
        key_repo = SaasApiKeyRepository(db)
        # Check if trial key already exists (idempotent)
        existing_keys, _ = await key_repo.list_by_tenant(tenant_id, page=1, page_size=100)
        has_trial = any(k.name == "trial-key" for k in existing_keys)

        if not has_trial:
            random_part = secrets.token_hex(32)
            prefix_hex = secrets.token_hex(2)
            prefix = f"stoa_trial_{prefix_hex}"
            trial_key_plaintext = f"{prefix}_{random_part}"
            key_hash = hashlib.sha256(trial_key_plaintext.encode()).hexdigest()
            now = datetime.now(UTC)

            trial_key = SaasApiKey(
                tenant_id=tenant_id,
                name="trial-key",
                description="Auto-generated trial key (30-day, 100 RPM)",
                key_hash=key_hash,
                key_prefix=prefix,
                allowed_backend_api_ids=[],
                rate_limit_rpm=100,
                expires_at=now + timedelta(days=30),
                created_by=current_user.id,
            )
            await key_repo.create(trial_key)
            logger.info("Trial API key generated for tenant %s", tenant_id)
    except Exception as e:
        logger.warning(f"Failed to generate trial key for {tenant_id}: {e}")
        trial_key_plaintext = None

    return PersonalTenantResponse(
        tenant_id=tenant_id,
        display_name=tenant.name,
        created=True,
        trial_api_key=trial_key_plaintext,
    )
