"""Portal Applications Router - User's applications management.

Provides endpoints for managing consumer applications (OAuth clients)
from the Portal perspective. These endpoints work across tenants based
on user's access.

The source of truth for applications is Keycloak (OAuth clients).
"""
import logging
import secrets
from typing import List, Optional
from datetime import datetime
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..auth.dependencies import get_current_user, User
from ..database import get_db as get_async_db

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
    client_id: str
    client_secret: Optional[str] = None  # Only returned on create
    tenant_id: Optional[str] = None
    status: str = "active"
    redirect_uris: List[str] = []
    api_subscriptions: List[str] = []
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class ApplicationsListResponse(BaseModel):
    """Paginated applications list response."""
    items: List[ApplicationResponse]
    total: int
    page: int
    pageSize: int
    totalPages: int


class ApplicationCreateRequest(BaseModel):
    """Request to create an application."""
    name: str
    display_name: str
    description: str = ""
    redirect_uris: List[str] = []
    tenant_id: Optional[str] = None  # If not specified, uses user's default tenant


class ApplicationUpdateRequest(BaseModel):
    """Request to update an application."""
    display_name: Optional[str] = None
    description: Optional[str] = None
    redirect_uris: Optional[List[str]] = None


class RegenerateSecretResponse(BaseModel):
    """Response for regenerate secret."""
    clientSecret: str


# ============================================================================
# In-memory storage (to be replaced with Keycloak integration)
# ============================================================================

# Temporary in-memory storage for demo purposes
# TODO: Replace with Keycloak client management
_applications: dict[str, dict] = {}


def _get_user_applications(user: User) -> List[dict]:
    """Get all applications owned by the user."""
    return [
        app for app in _applications.values()
        if app.get("owner_id") == user.sub or app.get("owner_id") == user.username
    ]


# ============================================================================
# Endpoints
# ============================================================================

@router.get("", response_model=ApplicationsListResponse)
async def list_applications(
    user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="page_size"),
    status: Optional[str] = Query(None),
):
    """
    List user's applications.

    Returns all applications owned by the current user across all tenants
    they have access to.
    """
    try:
        # Get user's applications
        all_apps = _get_user_applications(user)

        # Filter by status if specified
        if status:
            all_apps = [a for a in all_apps if a.get("status") == status]

        # Sort by created_at descending
        all_apps.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        # Paginate
        total = len(all_apps)
        start = (page - 1) * page_size
        end = start + page_size
        paginated = all_apps[start:end]

        return ApplicationsListResponse(
            items=[
                ApplicationResponse(
                    id=app["id"],
                    name=app["name"],
                    display_name=app["display_name"],
                    description=app.get("description", ""),
                    client_id=app["client_id"],
                    tenant_id=app.get("tenant_id"),
                    status=app.get("status", "active"),
                    redirect_uris=app.get("redirect_uris", []),
                    api_subscriptions=app.get("api_subscriptions", []),
                    created_at=app["created_at"],
                    updated_at=app.get("updated_at", app["created_at"]),
                )
                for app in paginated
            ],
            total=total,
            page=page,
            pageSize=page_size,
            totalPages=(total + page_size - 1) // page_size if total > 0 else 0,
        )

    except Exception as e:
        logger.error(f"Failed to list applications: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list applications: {str(e)}")


@router.get("/{app_id}", response_model=ApplicationResponse)
async def get_application(
    app_id: str,
    user: User = Depends(get_current_user),
):
    """
    Get application by ID.
    """
    app = _applications.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application {app_id} not found")

    # Check ownership
    if app.get("owner_id") not in [user.sub, user.username]:
        raise HTTPException(status_code=403, detail="Access denied")

    return ApplicationResponse(
        id=app["id"],
        name=app["name"],
        display_name=app["display_name"],
        description=app.get("description", ""),
        client_id=app["client_id"],
        tenant_id=app.get("tenant_id"),
        status=app.get("status", "active"),
        redirect_uris=app.get("redirect_uris", []),
        api_subscriptions=app.get("api_subscriptions", []),
        created_at=app["created_at"],
        updated_at=app.get("updated_at", app["created_at"]),
    )


@router.post("", response_model=ApplicationResponse)
async def create_application(
    data: ApplicationCreateRequest,
    user: User = Depends(get_current_user),
):
    """
    Create a new application.

    Returns the application with client_secret (only shown once!).

    TODO: Integrate with Keycloak to create actual OAuth client.
    """
    try:
        app_id = str(uuid4())
        client_id = f"app-{secrets.token_hex(8)}"
        client_secret = secrets.token_urlsafe(32)
        now = datetime.utcnow().isoformat() + "Z"

        app = {
            "id": app_id,
            "name": data.name,
            "display_name": data.display_name,
            "description": data.description,
            "client_id": client_id,
            "client_secret_hash": "hashed",  # In real impl, store hash
            "tenant_id": data.tenant_id,
            "owner_id": user.sub or user.username,
            "status": "active",
            "redirect_uris": data.redirect_uris,
            "api_subscriptions": [],
            "created_at": now,
            "updated_at": now,
        }

        _applications[app_id] = app

        logger.info(f"User {user.username} created application {data.name} (ID: {app_id})")

        return ApplicationResponse(
            id=app_id,
            name=data.name,
            display_name=data.display_name,
            description=data.description,
            client_id=client_id,
            client_secret=client_secret,  # Only returned on create!
            tenant_id=data.tenant_id,
            status="active",
            redirect_uris=data.redirect_uris,
            api_subscriptions=[],
            created_at=now,
            updated_at=now,
        )

    except Exception as e:
        logger.error(f"Failed to create application: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create application: {str(e)}")


@router.patch("/{app_id}", response_model=ApplicationResponse)
async def update_application(
    app_id: str,
    data: ApplicationUpdateRequest,
    user: User = Depends(get_current_user),
):
    """
    Update an application.
    """
    app = _applications.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application {app_id} not found")

    # Check ownership
    if app.get("owner_id") not in [user.sub, user.username]:
        raise HTTPException(status_code=403, detail="Access denied")

    # Update fields
    if data.display_name is not None:
        app["display_name"] = data.display_name
    if data.description is not None:
        app["description"] = data.description
    if data.redirect_uris is not None:
        app["redirect_uris"] = data.redirect_uris

    app["updated_at"] = datetime.utcnow().isoformat() + "Z"

    logger.info(f"User {user.username} updated application {app_id}")

    return ApplicationResponse(
        id=app["id"],
        name=app["name"],
        display_name=app["display_name"],
        description=app.get("description", ""),
        client_id=app["client_id"],
        tenant_id=app.get("tenant_id"),
        status=app.get("status", "active"),
        redirect_uris=app.get("redirect_uris", []),
        api_subscriptions=app.get("api_subscriptions", []),
        created_at=app["created_at"],
        updated_at=app["updated_at"],
    )


@router.delete("/{app_id}")
async def delete_application(
    app_id: str,
    user: User = Depends(get_current_user),
):
    """
    Delete an application.
    """
    app = _applications.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application {app_id} not found")

    # Check ownership
    if app.get("owner_id") not in [user.sub, user.username]:
        raise HTTPException(status_code=403, detail="Access denied")

    del _applications[app_id]

    logger.info(f"User {user.username} deleted application {app_id}")

    return {"message": "Application deleted"}


@router.post("/{app_id}/regenerate-secret", response_model=RegenerateSecretResponse)
async def regenerate_secret(
    app_id: str,
    user: User = Depends(get_current_user),
):
    """
    Regenerate application client secret.

    Returns the new client_secret (only shown once!).

    TODO: Integrate with Keycloak to regenerate actual client secret.
    """
    app = _applications.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application {app_id} not found")

    # Check ownership
    if app.get("owner_id") not in [user.sub, user.username]:
        raise HTTPException(status_code=403, detail="Access denied")

    # Generate new secret
    new_secret = secrets.token_urlsafe(32)
    app["client_secret_hash"] = "hashed"  # In real impl, store hash
    app["updated_at"] = datetime.utcnow().isoformat() + "Z"

    logger.info(f"User {user.username} regenerated secret for application {app_id}")

    return RegenerateSecretResponse(clientSecret=new_secret)
