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
from ..models.portal_application import PortalApplication, PortalAppStatus
from ..repositories.portal_application import PortalApplicationRepository
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
    client_id: str | None = None
    client_secret: str | None = None  # Only returned on create
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
    redirect_uris: list[str] = []
    tenant_id: str | None = None  # If not specified, uses user's default tenant


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


def _app_to_response(app: PortalApplication, client_secret: str | None = None) -> ApplicationResponse:
    """Convert a PortalApplication model to API response."""
    return ApplicationResponse(
        id=str(app.id),
        name=app.name,
        display_name=app.display_name,
        description=app.description or "",
        client_id=app.keycloak_client_id,
        client_secret=client_secret,
        tenant_id=app.tenant_id,
        status=app.status.value if app.status else "active",
        redirect_uris=app.redirect_uris or [],
        api_subscriptions=[],
        created_at=app.created_at.isoformat() + "Z" if app.created_at else "",
        updated_at=app.updated_at.isoformat() + "Z" if app.updated_at else "",
    )


def _check_ownership(app: PortalApplication, user: User) -> None:
    """Raise 403 if user does not own the application."""
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

    Returns the application with client_secret (only shown once!).
    Creates a corresponding Keycloak OAuth client if KC is available.
    """
    repo = PortalApplicationRepository(db)

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
        status=PortalAppStatus.ACTIVE,
    )

    # Try Keycloak client creation (graceful degradation)
    client_secret = None
    try:
        kc_result = await keycloak_service.create_client(
            tenant_id=data.tenant_id or "default",
            name=data.name,
            display_name=data.display_name,
            redirect_uris=data.redirect_uris,
            description=data.description,
        )
        app.keycloak_client_id = kc_result.get("client_id")
        app.keycloak_client_uuid = kc_result.get("id")
        client_secret = kc_result.get("client_secret")
    except Exception as e:
        logger.warning(f"Keycloak client creation failed (app will be created without KC): {e}")

    app = await repo.create(app)
    await db.commit()

    logger.info(f"User {user.username} created application {data.name} (ID: {app.id})")
    return _app_to_response(app, client_secret=client_secret)


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
