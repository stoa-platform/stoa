"""Pydantic schemas for External MCP Server endpoints.

Reference: External MCP Server Registration Plan
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ============== Enums ==============


class TransportTypeEnum(StrEnum):
    """Transport protocol for external MCP server."""

    SSE = "sse"
    HTTP = "http"
    WEBSOCKET = "websocket"


class AuthTypeEnum(StrEnum):
    """Authentication type for external MCP server."""

    NONE = "none"
    API_KEY = "api_key"
    BEARER_TOKEN = "bearer_token"
    OAUTH2 = "oauth2"


class HealthStatusEnum(StrEnum):
    """Health status of external MCP server."""

    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


# ============== Credential Schemas ==============


class OAuth2Credentials(BaseModel):
    """OAuth2 credential configuration."""

    client_id: str = Field(..., description="OAuth2 client ID")
    client_secret: str = Field(..., description="OAuth2 client secret")
    token_url: str = Field(..., description="OAuth2 token endpoint URL")
    scope: str | None = Field(None, description="OAuth2 scopes")


class CredentialsInput(BaseModel):
    """Credentials input for server registration."""

    api_key: str | None = Field(None, description="API key for api_key auth")
    bearer_token: str | None = Field(None, description="Bearer token for bearer_token auth")
    oauth2: OAuth2Credentials | None = Field(None, description="OAuth2 configuration")


# ============== Tool Schemas ==============


class ExternalMCPServerToolResponse(BaseModel):
    """Tool discovered from an external MCP server."""

    id: UUID
    name: str = Field(..., description="Original tool name from external server")
    namespaced_name: str = Field(..., description="Prefixed tool name (e.g., linear__create_issue)")
    display_name: str | None = None
    description: str | None = None
    input_schema: dict | None = None
    enabled: bool = True
    synced_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExternalMCPServerToolUpdate(BaseModel):
    """Schema for updating a tool."""

    enabled: bool = Field(..., description="Enable or disable the tool")


# ============== Server Schemas ==============


class ExternalMCPServerCreate(BaseModel):
    """Schema for creating a new external MCP server."""

    name: str = Field(..., min_length=1, max_length=255, description="Unique server name (slug)")
    display_name: str = Field(..., min_length=1, max_length=255, description="Display name")
    description: str | None = Field(None, description="Server description")
    icon: str | None = Field(None, max_length=500, description="URL to server icon")
    base_url: str = Field(..., description="Base URL of the MCP server")
    transport: TransportTypeEnum = Field(TransportTypeEnum.SSE, description="Transport protocol")
    auth_type: AuthTypeEnum = Field(AuthTypeEnum.NONE, description="Authentication type")
    credentials: CredentialsInput | None = Field(None, description="Credentials (stored securely)")
    tool_prefix: str | None = Field(None, max_length=100, description="Prefix for tool names")
    tenant_id: str | None = Field(None, max_length=255, description="Tenant ID (null = platform-wide)")
    environment: str = Field("dev", max_length=50, description="Target environment (dev/staging/production)")
    gateway_instance_id: UUID | None = Field(None, description="Bound gateway instance for dataplane routing")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "linear",
                "display_name": "Linear",
                "description": "Linear issue tracking integration",
                "base_url": "https://mcp.linear.app/sse",
                "transport": "sse",
                "auth_type": "bearer_token",
                "credentials": {"bearer_token": "lin_api_xxx"},
                "tool_prefix": "linear",
                "environment": "dev",
            }
        }
    )


class ExternalMCPServerUpdate(BaseModel):
    """Schema for updating an external MCP server."""

    display_name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    icon: str | None = Field(None, max_length=500)
    base_url: str | None = None
    transport: TransportTypeEnum | None = None
    auth_type: AuthTypeEnum | None = None
    credentials: CredentialsInput | None = Field(None, description="New credentials (updates securely)")
    tool_prefix: str | None = Field(None, max_length=100)
    enabled: bool | None = None
    environment: str | None = Field(None, max_length=50, description="Target environment")
    gateway_instance_id: UUID | None = Field(None, description="Bound gateway instance")


class ExternalMCPServerResponse(BaseModel):
    """External MCP server response."""

    id: UUID
    name: str
    display_name: str
    description: str | None = None
    icon: str | None = None
    base_url: str
    transport: TransportTypeEnum
    auth_type: AuthTypeEnum
    tool_prefix: str | None = None
    enabled: bool = True
    health_status: HealthStatusEnum = HealthStatusEnum.UNKNOWN
    last_health_check: datetime | None = None
    last_sync_at: datetime | None = None
    sync_error: str | None = None
    tenant_id: str | None = None
    environment: str | None = "dev"
    gateway_instance_id: UUID | None = None
    tools_count: int = 0
    created_at: datetime
    updated_at: datetime
    created_by: str | None = None

    model_config = ConfigDict(from_attributes=True)


class TenantMCPServerResponse(BaseModel):
    """Tenant-scoped MCP server response (no vault path, has_credentials instead)."""

    id: UUID
    name: str
    display_name: str
    description: str | None = None
    icon: str | None = None
    base_url: str
    transport: TransportTypeEnum
    auth_type: AuthTypeEnum
    has_credentials: bool = False
    tool_prefix: str | None = None
    enabled: bool = True
    health_status: HealthStatusEnum = HealthStatusEnum.UNKNOWN
    last_health_check: datetime | None = None
    last_sync_at: datetime | None = None
    sync_error: str | None = None
    environment: str | None = "dev"
    gateway_instance_id: UUID | None = None
    tools_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TenantMCPServerDetailResponse(TenantMCPServerResponse):
    """Tenant-scoped MCP server detail response with tools."""

    tools: list[ExternalMCPServerToolResponse] = []


class TenantMCPServerListResponse(BaseModel):
    """Response for listing tenant-scoped MCP servers."""

    servers: list[TenantMCPServerResponse]
    total_count: int
    page: int
    page_size: int


class TenantMCPServerCreate(BaseModel):
    """Schema for tenant self-service MCP server registration."""

    display_name: str = Field(..., min_length=1, max_length=255, description="Display name")
    description: str | None = Field(None, description="Server description")
    icon: str | None = Field(None, max_length=500, description="URL to server icon")
    base_url: str = Field(..., description="Base URL of the MCP server")
    transport: TransportTypeEnum = Field(TransportTypeEnum.SSE, description="Transport protocol")
    auth_type: AuthTypeEnum = Field(AuthTypeEnum.NONE, description="Authentication type")
    credentials: CredentialsInput | None = Field(None, description="Credentials (stored securely)")
    tool_prefix: str | None = Field(None, max_length=100, description="Prefix for tool names")
    environment: str = Field("dev", max_length=50, description="Target environment (dev/staging/production)")
    gateway_instance_id: UUID | None = Field(None, description="Bound gateway instance for dataplane routing")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "display_name": "My Linear",
                "description": "Team's Linear integration",
                "base_url": "https://mcp.linear.app/sse",
                "transport": "sse",
                "auth_type": "bearer_token",
                "credentials": {"bearer_token": "lin_api_xxx"},
                "tool_prefix": "linear",
                "environment": "dev",
            }
        }
    )


class TenantMCPServerUpdate(BaseModel):
    """Schema for updating a tenant-scoped MCP server."""

    display_name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    icon: str | None = Field(None, max_length=500)
    base_url: str | None = None
    transport: TransportTypeEnum | None = None
    auth_type: AuthTypeEnum | None = None
    credentials: CredentialsInput | None = Field(None, description="New credentials (stored securely)")
    tool_prefix: str | None = Field(None, max_length=100)
    enabled: bool | None = None
    environment: str | None = Field(None, max_length=50, description="Target environment")
    gateway_instance_id: UUID | None = Field(None, description="Bound gateway instance")


class ExternalMCPServerDetailResponse(ExternalMCPServerResponse):
    """External MCP server detail response with tools."""

    tools: list[ExternalMCPServerToolResponse] = []


class ExternalMCPServerListResponse(BaseModel):
    """Response for listing external MCP servers."""

    servers: list[ExternalMCPServerResponse]
    total_count: int
    page: int
    page_size: int


# ============== Test Connection Schemas ==============


class TestConnectionResponse(BaseModel):
    """Response from test-connection endpoint."""

    success: bool
    latency_ms: int | None = None
    error: str | None = None
    server_info: dict | None = None
    tools_discovered: int | None = None


# ============== Sync Tools Schemas ==============


class SyncToolsResponse(BaseModel):
    """Response from sync-tools endpoint."""

    synced_count: int
    removed_count: int
    tools: list[ExternalMCPServerToolResponse] = []


# ============== Gateway Internal Schemas ==============


class ExternalMCPServerForGateway(BaseModel):
    """External MCP server with credentials for gateway use."""

    id: UUID
    name: str
    base_url: str
    transport: TransportTypeEnum
    auth_type: AuthTypeEnum
    credentials: dict | None = None  # Decrypted credentials
    tool_prefix: str | None = None
    tenant_id: str | None = None
    environment: str | None = "dev"
    gateway_instance_id: UUID | None = None
    tools: list[ExternalMCPServerToolResponse] = []

    model_config = ConfigDict(from_attributes=True)


class ExternalMCPServersForGatewayResponse(BaseModel):
    """Response for gateway internal endpoint."""

    servers: list[ExternalMCPServerForGateway]


# ============== Tool Observability Schemas (CAB-1821) ==============


class ToolObservabilityItem(BaseModel):
    """Per-tool observability data: metadata + gateway binding."""

    id: UUID
    name: str = Field(..., description="Original tool name")
    namespaced_name: str = Field(..., description="Prefixed tool name")
    display_name: str | None = None
    description: str | None = None
    enabled: bool = True
    synced_at: datetime
    input_schema: dict | None = None

    model_config = ConfigDict(from_attributes=True)


class GatewayBindingInfo(BaseModel):
    """Gateway instance binding information for an MCP server."""

    gateway_instance_id: UUID | None = None
    gateway_name: str | None = Field(None, description="Gateway instance display name")
    gateway_type: str | None = Field(None, description="Gateway type (stoa, kong, etc.)")
    gateway_environment: str | None = Field(None, description="Gateway environment")
    gateway_status: str | None = Field(None, description="Gateway health status")


class ToolsObservabilityResponse(BaseModel):
    """Response for tools-summary endpoint — tool metadata + gateway binding (CAB-1821)."""

    server_id: UUID
    server_name: str
    server_display_name: str
    environment: str | None = "dev"
    health_status: HealthStatusEnum = HealthStatusEnum.UNKNOWN
    last_health_check: datetime | None = None
    last_sync_at: datetime | None = None
    gateway: GatewayBindingInfo
    tools: list[ToolObservabilityItem] = []
    tools_count: int = 0
    enabled_count: int = 0
