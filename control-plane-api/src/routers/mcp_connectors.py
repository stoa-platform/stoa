"""MCP Connector Catalog Router — App Store pattern for pre-configured OAuth connectors.

Endpoints:
- GET    /v1/admin/mcp-connectors              — List catalog with connection status
- GET    /v1/admin/mcp-connectors/{slug}        — Template detail
- POST   /v1/admin/mcp-connectors/{slug}/authorize  — Initiate OAuth flow
- POST   /v1/admin/mcp-connectors/callback      — OAuth callback (code+state exchange)
- DELETE /v1/admin/mcp-connectors/{slug}/disconnect  — Disconnect connector
"""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import User, get_current_user
from ..config import settings
from ..database import get_db
from ..repositories.external_mcp_server import ExternalMCPServerRepository
from ..repositories.mcp_connector import (
    ConnectorServerRepository,
    ConnectorTemplateRepository,
    OAuthSessionRepository,
)
from ..schemas.mcp_connector import (
    AuthorizeRequest,
    AuthorizeResponse,
    CallbackRequest,
    CallbackResponse,
    ConnectorCatalogResponse,
    ConnectorTemplateResponse,
    DisconnectResponse,
)
from ..services.connector_oauth import ConnectorOAuthError, ConnectorOAuthService
from ..services.vault_client import get_vault_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/admin/mcp-connectors", tags=["MCP Connectors - Catalog"])


def _require_admin(user: User) -> None:
    """Check if user has admin access."""
    if "cpi-admin" not in user.roles and "tenant-admin" not in user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")


def _get_tenant_id(user: User, explicit_tenant_id: str | None = None) -> str | None:
    """Resolve the effective tenant_id for the request."""
    if "cpi-admin" in user.roles:
        return explicit_tenant_id
    return user.tenant_id


def _build_oauth_service(db: AsyncSession) -> ConnectorOAuthService:
    """Build ConnectorOAuthService with all repositories."""
    return ConnectorOAuthService(
        template_repo=ConnectorTemplateRepository(db),
        session_repo=OAuthSessionRepository(db),
        connector_server_repo=ConnectorServerRepository(db),
        server_repo=ExternalMCPServerRepository(db),
    )


def _build_redirect_uri() -> str:
    """Build the OAuth callback redirect URI from settings."""
    return f"https://console.{settings.BASE_DOMAIN}/mcp-connectors/callback"


def _has_client_id(template) -> bool:  # type: ignore[no-untyped-def]
    """Check if a connector template has a client_id configured (DB, env, or Vault)."""
    if template.oauth_client_id:
        return True
    env_key = f"MCP_OAUTH_{template.slug.upper()}_CLIENT_ID"
    return bool(os.environ.get(env_key, ""))


@router.get("", response_model=ConnectorCatalogResponse)
async def list_connectors(
    tenant_id: str | None = Query(None, description="Tenant to check connection status for"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the connector catalog with per-tenant connection status."""
    _require_admin(user)

    effective_tenant_id = _get_tenant_id(user, tenant_id)

    template_repo = ConnectorTemplateRepository(db)
    connector_server_repo = ConnectorServerRepository(db)

    templates = await template_repo.list_all(enabled_only=True)

    # Get connection status for the tenant
    connected_map = await connector_server_repo.list_connected_template_ids(effective_tenant_id)

    result = []
    for t in templates:
        connected_info = connected_map.get(t.id)
        result.append(
            ConnectorTemplateResponse(
                id=t.id,
                slug=t.slug,
                display_name=t.display_name,
                description=t.description,
                icon_url=t.icon_url,
                category=t.category,
                mcp_base_url=t.mcp_base_url,
                transport=t.transport,
                oauth_scopes=t.oauth_scopes,
                oauth_pkce_required=t.oauth_pkce_required,
                documentation_url=t.documentation_url,
                is_featured=t.is_featured,
                enabled=t.enabled,
                sort_order=t.sort_order,
                is_connected=connected_info is not None,
                connected_server_id=connected_info[0] if connected_info else None,
                connection_health=connected_info[1] if connected_info else None,
                needs_setup=not _has_client_id(t),
            )
        )

    return ConnectorCatalogResponse(connectors=result, total_count=len(result))


@router.get("/{slug}", response_model=ConnectorTemplateResponse)
async def get_connector(
    slug: str,
    tenant_id: str | None = Query(None, description="Tenant to check connection status for"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single connector template with connection status."""
    _require_admin(user)

    effective_tenant_id = _get_tenant_id(user, tenant_id)

    template_repo = ConnectorTemplateRepository(db)
    template = await template_repo.get_by_slug(slug)
    if not template:
        raise HTTPException(status_code=404, detail=f"Connector '{slug}' not found")

    connector_server_repo = ConnectorServerRepository(db)
    connected_map = await connector_server_repo.list_connected_template_ids(effective_tenant_id)
    connected_info = connected_map.get(template.id)

    return ConnectorTemplateResponse(
        id=template.id,
        slug=template.slug,
        display_name=template.display_name,
        description=template.description,
        icon_url=template.icon_url,
        category=template.category,
        mcp_base_url=template.mcp_base_url,
        transport=template.transport,
        oauth_scopes=template.oauth_scopes,
        oauth_pkce_required=template.oauth_pkce_required,
        documentation_url=template.documentation_url,
        is_featured=template.is_featured,
        enabled=template.enabled,
        sort_order=template.sort_order,
        is_connected=connected_info is not None,
        connected_server_id=connected_info[0] if connected_info else None,
        connection_health=connected_info[1] if connected_info else None,
    )


@router.post("/{slug}/authorize", response_model=AuthorizeResponse)
async def authorize_connector(
    slug: str,
    request: AuthorizeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Initiate OAuth authorization for a connector.

    Returns the authorize URL to redirect the user to the provider's consent page.
    """
    _require_admin(user)

    effective_tenant_id = _get_tenant_id(user, request.tenant_id)

    template_repo = ConnectorTemplateRepository(db)
    template = await template_repo.get_by_slug(slug)
    if not template:
        raise HTTPException(status_code=404, detail=f"Connector '{slug}' not found")

    if not template.enabled:
        raise HTTPException(status_code=400, detail=f"Connector '{slug}' is disabled")

    # Save client credentials if provided (first-time setup from UI)
    if request.client_id:
        template.oauth_client_id = request.client_id
        db.add(template)
        if request.client_secret:
            try:
                vault = get_vault_client()
                if vault.enabled:
                    vault._ensure_unsealed()
                    client = vault._get_client()
                    client.secrets.kv.v2.create_or_update_secret(
                        path=f"mcp-connector-templates/{slug}",
                        secret={"client_id": request.client_id, "client_secret": request.client_secret},
                        mount_point=vault.mount_point,
                    )
                    logger.info("Stored provider credentials in Vault for '%s'", slug)
            except Exception as e:
                logger.warning("Failed to store client_secret in Vault for '%s': %s", slug, e)

    service = _build_oauth_service(db)
    redirect_uri = _build_redirect_uri()

    try:
        authorize_url, state = await service.initiate_authorize(
            template=template,
            user_id=user.id,
            tenant_id=effective_tenant_id,
            redirect_after=request.redirect_after,
            redirect_uri=redirect_uri,
        )
        await db.commit()
    except ConnectorOAuthError as e:
        if e.status_code == 409:
            raise HTTPException(status_code=409, detail=e.message)
        raise HTTPException(status_code=e.status_code, detail=e.message)

    return AuthorizeResponse(authorize_url=authorize_url, state=state)


@router.post("/callback", response_model=CallbackResponse)
async def oauth_callback(
    request: CallbackRequest,
    db: AsyncSession = Depends(get_db),
):
    """Handle the OAuth callback — exchange code for tokens and create the MCP server.

    This endpoint does NOT require authentication because it is called by the
    browser redirect from the OAuth provider. The CSRF state token provides
    security by linking the callback to the original authorized session.
    """
    service = _build_oauth_service(db)
    redirect_uri = _build_redirect_uri()

    try:
        server, redirect_after = await service.handle_callback(
            code=request.code,
            state=request.state,
            redirect_uri=redirect_uri,
        )
        await db.commit()
    except ConnectorOAuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    return CallbackResponse(
        server_id=server.id,
        server_name=server.name,
        display_name=server.display_name,
        slug=server.tool_prefix or server.name,
        redirect_url=redirect_after,
    )


@router.delete("/{slug}/disconnect", response_model=DisconnectResponse)
async def disconnect_connector(
    slug: str,
    tenant_id: str | None = Query(None, description="Tenant to disconnect for"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect a connector — remove the server and Vault credentials."""
    _require_admin(user)

    effective_tenant_id = _get_tenant_id(user, tenant_id)

    template_repo = ConnectorTemplateRepository(db)
    template = await template_repo.get_by_slug(slug)
    if not template:
        raise HTTPException(status_code=404, detail=f"Connector '{slug}' not found")

    service = _build_oauth_service(db)

    try:
        server_id = await service.disconnect(template, effective_tenant_id)
        await db.commit()
    except ConnectorOAuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    if not server_id:
        raise HTTPException(
            status_code=404,
            detail=f"Connector '{slug}' is not connected for this tenant",
        )

    return DisconnectResponse(slug=slug, disconnected=True, server_id=server_id)
