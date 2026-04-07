"""Portal Applications Router - User's applications management.

Provides endpoints for managing consumer applications (OAuth clients)
from the Portal perspective. These endpoints work across tenants based
on user's access.

The source of truth for applications is Keycloak (OAuth clients).
Portal stores metadata + Keycloak client references in PostgreSQL.
"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import User, get_current_user
from ..database import get_db
from ..models.portal_application import PortalApplication, PortalAppStatus, SecurityProfile
from ..repositories.portal_application import PortalApplicationRepository
from ..services.api_key import api_key_service
from ..services.jwks_utils import parse_jwks_input
from ..services.keycloak_service import keycloak_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/applications", tags=["Portal Applications"])


# ============================================================================
# Response Models
# ============================================================================


class ApplicationResponse(BaseModel):
    """Application response for Portal."""

    id: str
    name: str
    display_name: str
    description: str
    security_profile: str = "oauth2_public"
    client_id: str | None = None
    client_secret: str | None = None  # Only returned on create
    owner_id: str | None = None
    api_key: str | None = None  # Only returned on create for api_key profile
    api_key_prefix: str | None = None
    jwks_uri: str | None = None
    jwks_data: dict | None = None
    tenant_id: str | None = None
    status: str = "active"
    redirect_uris: list[str] = []
    api_subscriptions: list[str] = []
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class ApplicationsListResponse(BaseModel):
    """Paginated applications list response."""

    items: list[ApplicationResponse]
    total: int
    page: int
    pageSize: int
    totalPages: int


class ApplicationCreateRequest(BaseModel):
    """Request to create an application."""

    name: str
    display_name: str
    description: str = ""
    security_profile: SecurityProfile = SecurityProfile.OAUTH2_PUBLIC
    redirect_uris: list[str] = []
    jwks_uri: str | None = None  # FAPI: URL to JWKS endpoint
    jwks: str | None = None  # FAPI: inline PEM public key or JWK/JWKS JSON
    tenant_id: str | None = None  # If not specified, uses user's default tenant
    environment: str | None = None  # Multi-env registry (CAB-1667)


class ApplicationUpdateRequest(BaseModel):
    """Request to update an application."""

    display_name: str | None = None
    description: str | None = None
    redirect_uris: list[str] | None = None


class RegenerateSecretResponse(BaseModel):
    """Response for regenerate secret."""

    clientSecret: str


# ============================================================================
# Helpers
# ============================================================================


def _app_to_response(
    app: PortalApplication,
    client_secret: str | None = None,
    api_key: str | None = None,
) -> ApplicationResponse:
    """Convert a PortalApplication model to API response."""
    return ApplicationResponse(
        id=str(app.id),
        name=app.name,
        display_name=app.display_name,
        description=app.description or "",
        security_profile=app.security_profile.value if app.security_profile else "oauth2_public",
        client_id=app.keycloak_client_id,
        client_secret=client_secret,
        api_key=api_key,
        api_key_prefix=app.api_key_prefix,
        jwks_uri=app.jwks_uri,
        jwks_data=app.jwks_data,
        owner_id=app.owner_id,
        tenant_id=app.tenant_id,
        status=app.status.value if app.status else "active",
        redirect_uris=app.redirect_uris or [],
        api_subscriptions=[],
        created_at=app.created_at.isoformat() + "Z" if app.created_at else "",
        updated_at=app.updated_at.isoformat() + "Z" if app.updated_at else "",
    )


_ADMIN_ROLES = {"cpi-admin", "tenant-admin"}


def _is_admin(user: User) -> bool:
    """Check if user has an admin role (cpi-admin or tenant-admin)."""
    return bool(set(user.roles) & _ADMIN_ROLES)


def _check_ownership(app: PortalApplication, user: User) -> None:
    """Raise 403 if user does not own the application (admins bypass)."""
    if _is_admin(user):
        return
    if app.owner_id != user.id and app.owner_id != user.username:
        raise HTTPException(status_code=403, detail="Access denied")


# ============================================================================
# Endpoints
# ============================================================================


@router.get("", response_model=ApplicationsListResponse)
async def list_applications(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="page_size"),
    status: str | None = Query(None),
    environment: str | None = Query(None, description="Filter by environment"),
):
    """
    List user's applications.

    Returns all applications owned by the current user across all tenants
    they have access to.
    """
    repo = PortalApplicationRepository(db)
    status_filter = PortalAppStatus(status) if status else None
    items, total = await repo.list_by_owner(
        owner_id=user.id,
        status=status_filter,
        page=page,
        page_size=page_size,
        environment=environment,
        is_admin=_is_admin(user),
    )

    return ApplicationsListResponse(
        items=[_app_to_response(app) for app in items],
        total=total,
        page=page,
        pageSize=page_size,
        totalPages=(total + page_size - 1) // page_size if total > 0 else 0,
    )


@router.get("/{app_id}", response_model=ApplicationResponse)
async def get_application(
    app_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get application by ID."""
    repo = PortalApplicationRepository(db)
    app = await repo.get_by_id(UUID(app_id))
    if not app:
        raise HTTPException(status_code=404, detail=f"Application {app_id} not found")

    _check_ownership(app, user)
    return _app_to_response(app)


@router.post("", response_model=ApplicationResponse)
async def create_application(
    data: ApplicationCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new application.

    Returns the application with credentials (only shown once!).
    Behavior varies by security_profile:
    - api_key: generates API key, no Keycloak client
    - oauth2_public: public KC client with PKCE
    - oauth2_confidential: confidential KC client with client_secret
    - fapi_baseline: confidential KC client + FAPI 2.0 Security Profile
    - fapi_advanced: confidential KC client + FAPI 2.0 + DPoP
    """
    repo = PortalApplicationRepository(db)
    profile = data.security_profile

    # Validate profile-specific requirements
    if profile in (SecurityProfile.FAPI_BASELINE, SecurityProfile.FAPI_ADVANCED):
        if not data.jwks_uri and not data.jwks:
            raise HTTPException(
                status_code=422,
                detail="FAPI profiles require either jwks_uri (URL) or jwks (inline PEM/JWK)",
            )
        if data.jwks_uri and data.jwks:
            raise HTTPException(
                status_code=422,
                detail="Provide either jwks_uri or jwks, not both",
            )

    # Parse inline JWKS if provided (PEM, JWK JSON, or JWKS JSON)
    jwks_data = None
    if data.jwks:
        try:
            jwks_data = parse_jwks_input(data.jwks)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=f"Invalid JWKS input: {e}")

    # Check for duplicate name
    existing = await repo.get_by_owner_and_name(user.id, data.name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Application with name '{data.name}' already exists")

    # Build model
    app = PortalApplication(
        name=data.name,
        display_name=data.display_name,
        description=data.description,
        owner_id=user.id,
        tenant_id=data.tenant_id,
        redirect_uris=data.redirect_uris,
        security_profile=profile,
        jwks_uri=data.jwks_uri,
        jwks_data=jwks_data,
        status=PortalAppStatus.ACTIVE,
        environment=data.environment,
    )

    client_secret = None
    api_key_full = None

    if profile == SecurityProfile.API_KEY:
        # API Key profile — no Keycloak client, generate API key
        api_key_full, key_hash, key_prefix = api_key_service.generate_key()
        app.api_key_hash = key_hash
        app.api_key_prefix = key_prefix
    else:
        # All OAuth2/FAPI profiles — create Keycloak client
        try:
            kc_result = await keycloak_service.create_client(
                tenant_id=data.tenant_id or "default",
                name=data.name,
                display_name=data.display_name,
                redirect_uris=data.redirect_uris,
                description=data.description,
                security_profile=profile.value,
                jwks_data=jwks_data,
            )
            app.keycloak_client_id = kc_result.get("client_id")
            app.keycloak_client_uuid = kc_result.get("id")
            client_secret = kc_result.get("client_secret")
        except Exception as e:
            logger.warning(f"Keycloak client creation failed (app will be created without KC): {e}")

    app = await repo.create(app)
    await db.commit()

    logger.info(f"User {user.username} created application {data.name} (profile={profile.value}, ID: {app.id})")
    return _app_to_response(app, client_secret=client_secret, api_key=api_key_full)


@router.patch("/{app_id}", response_model=ApplicationResponse)
async def update_application(
    app_id: str,
    data: ApplicationUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an application."""
    repo = PortalApplicationRepository(db)
    app = await repo.get_by_id(UUID(app_id))
    if not app:
        raise HTTPException(status_code=404, detail=f"Application {app_id} not found")

    _check_ownership(app, user)

    # Update fields
    if data.display_name is not None:
        app.display_name = data.display_name
    if data.description is not None:
        app.description = data.description
    if data.redirect_uris is not None:
        app.redirect_uris = data.redirect_uris

    app.updated_at = datetime.utcnow()
    app = await repo.update(app)
    await db.commit()

    logger.info(f"User {user.username} updated application {app_id}")
    return _app_to_response(app)


@router.delete("/{app_id}")
async def delete_application(
    app_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an application."""
    repo = PortalApplicationRepository(db)
    app = await repo.get_by_id(UUID(app_id))
    if not app:
        raise HTTPException(status_code=404, detail=f"Application {app_id} not found")

    _check_ownership(app, user)

    # Try Keycloak client deletion (graceful degradation)
    if app.keycloak_client_uuid:
        try:
            await keycloak_service.delete_client(app.keycloak_client_uuid)
        except Exception as e:
            logger.warning(f"Keycloak client deletion failed: {e}")

    await repo.delete(app)
    await db.commit()

    logger.info(f"User {user.username} deleted application {app_id}")
    return {"message": "Application deleted"}


@router.post("/{app_id}/regenerate-secret", response_model=RegenerateSecretResponse)
async def regenerate_secret(
    app_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Regenerate application client secret.

    Returns the new client_secret (only shown once!).
    Requires Keycloak client to be linked.
    """
    repo = PortalApplicationRepository(db)
    app = await repo.get_by_id(UUID(app_id))
    if not app:
        raise HTTPException(status_code=404, detail=f"Application {app_id} not found")

    _check_ownership(app, user)

    if not app.keycloak_client_uuid:
        raise HTTPException(status_code=400, detail="Application has no Keycloak client linked")

    new_secret = await keycloak_service.regenerate_client_secret(app.keycloak_client_uuid)
    app.updated_at = datetime.utcnow()
    await repo.update(app)
    await db.commit()

    logger.info(f"User {user.username} regenerated secret for application {app_id}")
    return RegenerateSecretResponse(clientSecret=new_secret)
