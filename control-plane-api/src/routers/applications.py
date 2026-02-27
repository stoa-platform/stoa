"""Applications router - Consumer applications management via Keycloak"""

import json
import logging
from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import Permission, User, get_current_user, require_permission, require_tenant_access
from ..database import get_db
from ..repositories.tenant import TenantRepository
from ..schemas.pagination import PaginatedResponse
from ..services.keycloak_service import keycloak_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/tenants/{tenant_id}/applications", tags=["Applications"])


class ApplicationCreate(BaseModel):
    name: str
    display_name: str
    description: str = ""
    redirect_uris: list[str] = []
    api_subscriptions: list[str] = []


class ApplicationResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    display_name: str
    description: str
    client_id: str
    status: str = "active"
    api_subscriptions: list[str] = []
    created_at: str
    updated_at: str


class ApplicationCredentials(BaseModel):
    client_id: str
    client_secret: str


def _kc_client_to_response(client: dict, tenant_id: str) -> ApplicationResponse:
    """Convert a Keycloak client dict to ApplicationResponse."""
    attrs = client.get("attributes", {})
    subs_raw = attrs.get("api_subscriptions", ["[]"])
    subs_val = subs_raw[0] if isinstance(subs_raw, list) else subs_raw
    created = attrs.get("created_at", [""])
    updated = attrs.get("updated_at", [""])
    return ApplicationResponse(
        id=client["id"],
        tenant_id=tenant_id,
        name=client.get("clientId", "").removeprefix(f"{tenant_id}-"),
        display_name=client.get("name", client.get("clientId", "")),
        description=client.get("description", ""),
        client_id=client.get("clientId", ""),
        status="active" if client.get("enabled", True) else "disabled",
        api_subscriptions=json.loads(subs_val),
        created_at=created[0] if isinstance(created, list) else created,
        updated_at=updated[0] if isinstance(updated, list) else updated,
    )


async def _get_tenant_client(app_id: str, tenant_id: str) -> dict:
    """Get a KC client by UUID, verify tenant ownership, or raise 404."""
    client = await keycloak_service.get_client_by_id(app_id)
    if not client:
        raise HTTPException(status_code=404, detail="Application not found")
    # Verify tenant ownership
    attrs = client.get("attributes", {})
    attr_tenant = attrs.get("tenant_id", [None])
    actual_tenant = attr_tenant[0] if isinstance(attr_tenant, list) else attr_tenant
    client_id = client.get("clientId", "")
    if actual_tenant != tenant_id and not client_id.startswith(f"{tenant_id}-"):
        raise HTTPException(status_code=404, detail="Application not found")
    return client


@router.get("", response_model=PaginatedResponse[ApplicationResponse])
@require_tenant_access
async def list_applications(
    tenant_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
):
    """List all applications for a tenant (paginated)."""
    clients = await keycloak_service.get_clients(tenant_id)
    items = [_kc_client_to_response(c, tenant_id) for c in clients]
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return PaginatedResponse(items=items[start:end], total=total, page=page, page_size=page_size)


@router.get("/{app_id}", response_model=ApplicationResponse)
@require_tenant_access
async def get_application(tenant_id: str, app_id: str, user: User = Depends(get_current_user)):
    """Get application by ID."""
    client = await _get_tenant_client(app_id, tenant_id)
    return _kc_client_to_response(client, tenant_id)


@router.post("", response_model=ApplicationResponse, status_code=201)
@require_permission(Permission.APPS_CREATE)
@require_tenant_access
async def create_application(
    tenant_id: str, app: ApplicationCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Create a new application (Keycloak client)."""
    # Check tenant application limit (CAB-1549)
    from ..routers.tenants import get_tenant_limits

    repo = TenantRepository(db)
    tenant = await repo.get_by_id(tenant_id)
    if tenant:
        _, max_apps = get_tenant_limits(tenant)
        current_apps = await keycloak_service.get_clients(tenant_id)
        if len(current_apps) >= max_apps:
            raise HTTPException(status_code=429, detail=f"Application limit reached ({max_apps})")

    from datetime import datetime

    result = await keycloak_service.create_client(
        tenant_id=tenant_id,
        name=app.name,
        display_name=app.display_name,
        redirect_uris=app.redirect_uris,
        description=app.description,
    )
    now = datetime.now(UTC).isoformat()
    # Store extra attributes
    await keycloak_service.update_client(
        result["id"],
        {
            "attributes": {
                "tenant_id": tenant_id,
                "api_subscriptions": json.dumps(app.api_subscriptions),
                "created_at": now,
                "updated_at": now,
            }
        },
    )
    client = await keycloak_service.get_client_by_id(result["id"])
    return _kc_client_to_response(client, tenant_id)


@router.put("/{app_id}", response_model=ApplicationResponse)
@require_permission(Permission.APPS_UPDATE)
@require_tenant_access
async def update_application(
    tenant_id: str, app_id: str, app: ApplicationCreate, user: User = Depends(get_current_user)
):
    """Update application."""
    from datetime import datetime

    client = await _get_tenant_client(app_id, tenant_id)
    now = datetime.now(UTC).isoformat()
    attrs = client.get("attributes", {})
    attrs["updated_at"] = now
    await keycloak_service.update_client(
        app_id,
        {
            "name": app.display_name,
            "description": app.description,
            "redirectUris": app.redirect_uris,
            "attributes": attrs,
        },
    )
    updated = await keycloak_service.get_client_by_id(app_id)
    return _kc_client_to_response(updated, tenant_id)


@router.delete("/{app_id}", status_code=204)
@require_permission(Permission.APPS_DELETE)
@require_tenant_access
async def delete_application(tenant_id: str, app_id: str, user: User = Depends(get_current_user)):
    """Delete application."""
    await _get_tenant_client(app_id, tenant_id)
    await keycloak_service.delete_client(app_id)


@router.post("/{app_id}/regenerate-secret", response_model=ApplicationCredentials)
@require_permission(Permission.APPS_UPDATE)
@require_tenant_access
async def regenerate_secret(tenant_id: str, app_id: str, user: User = Depends(get_current_user)):
    """Regenerate application client secret."""
    client = await _get_tenant_client(app_id, tenant_id)
    new_secret = await keycloak_service.regenerate_client_secret(app_id)
    return ApplicationCredentials(
        client_id=client.get("clientId", ""),
        client_secret=new_secret,
    )


@router.post("/{app_id}/subscribe/{api_id}")
@require_permission(Permission.APPS_UPDATE)
@require_tenant_access
async def subscribe_to_api(tenant_id: str, app_id: str, api_id: str, user: User = Depends(get_current_user)):
    """Subscribe application to an API."""
    client = await _get_tenant_client(app_id, tenant_id)
    attrs = client.get("attributes", {})
    subs_raw = attrs.get("api_subscriptions", ["[]"])
    subs_val = subs_raw[0] if isinstance(subs_raw, list) else subs_raw
    subs = json.loads(subs_val)
    if api_id in subs:
        raise HTTPException(status_code=409, detail="Already subscribed")
    subs.append(api_id)
    attrs["api_subscriptions"] = json.dumps(subs)
    await keycloak_service.update_client(app_id, {"attributes": attrs})
    return {"message": f"Application subscribed to API {api_id}"}


@router.delete("/{app_id}/subscribe/{api_id}")
@require_permission(Permission.APPS_UPDATE)
@require_tenant_access
async def unsubscribe_from_api(tenant_id: str, app_id: str, api_id: str, user: User = Depends(get_current_user)):
    """Unsubscribe application from an API."""
    client = await _get_tenant_client(app_id, tenant_id)
    attrs = client.get("attributes", {})
    subs_raw = attrs.get("api_subscriptions", ["[]"])
    subs_val = subs_raw[0] if isinstance(subs_raw, list) else subs_raw
    subs = json.loads(subs_val)
    if api_id not in subs:
        raise HTTPException(status_code=404, detail="Not subscribed to this API")
    subs.remove(api_id)
    attrs["api_subscriptions"] = json.dumps(subs)
    await keycloak_service.update_client(app_id, {"attributes": attrs})
    return {"message": f"Application unsubscribed from API {api_id}"}
