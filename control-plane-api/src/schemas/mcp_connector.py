"""Pydantic schemas for MCP Connector Catalog endpoints.

App Store pattern: browse catalog, authorize via OAuth, auto-configure server.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ============== Template Schemas ==============


class ConnectorTemplateResponse(BaseModel):
    """A pre-configured MCP connector template."""

    id: UUID
    slug: str
    display_name: str
    description: str | None = None
    icon_url: str | None = None
    category: str
    mcp_base_url: str
    transport: str
    oauth_scopes: str | None = None
    oauth_pkce_required: bool = False
    documentation_url: str | None = None
    is_featured: bool = False
    enabled: bool = True
    sort_order: int = 0
    # Connection status (populated per-request based on tenant)
    is_connected: bool = False
    connected_server_id: UUID | None = None
    connection_health: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ConnectorCatalogResponse(BaseModel):
    """Response for the connector catalog listing."""

    connectors: list[ConnectorTemplateResponse]
    total_count: int


# ============== Authorize Schemas ==============


class AuthorizeRequest(BaseModel):
    """Request to initiate an OAuth authorization flow."""

    tenant_id: str | None = Field(None, description="Tenant to connect for (null = personal)")
    redirect_after: str | None = Field(None, description="UI URL to redirect after callback")


class AuthorizeResponse(BaseModel):
    """Response with the OAuth authorize URL to redirect the user to."""

    authorize_url: str = Field(..., description="Full OAuth authorize URL with state, scope, etc.")
    state: str = Field(..., description="CSRF state token (for reference)")


# ============== Callback Schemas ==============


class CallbackRequest(BaseModel):
    """Request from the OAuth callback (code + state exchange)."""

    code: str = Field(..., description="Authorization code from the provider")
    state: str = Field(..., description="CSRF state token to validate")


class CallbackResponse(BaseModel):
    """Response after successful OAuth callback — the created server."""

    server_id: UUID
    server_name: str
    display_name: str
    slug: str
    tools_sync_triggered: bool = False
    redirect_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


# ============== Disconnect Schema ==============


class DisconnectResponse(BaseModel):
    """Response after disconnecting a connector."""

    slug: str
    disconnected: bool = True
    server_id: UUID | None = None
