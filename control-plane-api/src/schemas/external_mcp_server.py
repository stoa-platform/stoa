# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Pydantic schemas for External MCP Server endpoints.

Reference: External MCP Server Registration Plan
"""
from pydantic import BaseModel, Field, ConfigDict, HttpUrl
from typing import Optional, List, Any
from datetime import datetime
from uuid import UUID
from enum import Enum


# ============== Enums ==============

class TransportTypeEnum(str, Enum):
    """Transport protocol for external MCP server."""
    SSE = "sse"
    HTTP = "http"
    WEBSOCKET = "websocket"


class AuthTypeEnum(str, Enum):
    """Authentication type for external MCP server."""
    NONE = "none"
    API_KEY = "api_key"
    BEARER_TOKEN = "bearer_token"
    OAUTH2 = "oauth2"


class HealthStatusEnum(str, Enum):
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
    scope: Optional[str] = Field(None, description="OAuth2 scopes")


class CredentialsInput(BaseModel):
    """Credentials input for server registration."""
    api_key: Optional[str] = Field(None, description="API key for api_key auth")
    bearer_token: Optional[str] = Field(None, description="Bearer token for bearer_token auth")
    oauth2: Optional[OAuth2Credentials] = Field(None, description="OAuth2 configuration")


# ============== Tool Schemas ==============

class ExternalMCPServerToolResponse(BaseModel):
    """Tool discovered from an external MCP server."""
    id: UUID
    name: str = Field(..., description="Original tool name from external server")
    namespaced_name: str = Field(..., description="Prefixed tool name (e.g., linear__create_issue)")
    display_name: Optional[str] = None
    description: Optional[str] = None
    input_schema: Optional[dict] = None
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
    description: Optional[str] = Field(None, description="Server description")
    icon: Optional[str] = Field(None, max_length=500, description="URL to server icon")
    base_url: str = Field(..., description="Base URL of the MCP server")
    transport: TransportTypeEnum = Field(TransportTypeEnum.SSE, description="Transport protocol")
    auth_type: AuthTypeEnum = Field(AuthTypeEnum.NONE, description="Authentication type")
    credentials: Optional[CredentialsInput] = Field(None, description="Credentials (stored in Vault)")
    tool_prefix: Optional[str] = Field(None, max_length=100, description="Prefix for tool names")
    tenant_id: Optional[str] = Field(None, max_length=255, description="Tenant ID (null = platform-wide)")

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
                "tool_prefix": "linear"
            }
        }
    )


class ExternalMCPServerUpdate(BaseModel):
    """Schema for updating an external MCP server."""
    display_name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    icon: Optional[str] = Field(None, max_length=500)
    base_url: Optional[str] = None
    transport: Optional[TransportTypeEnum] = None
    auth_type: Optional[AuthTypeEnum] = None
    credentials: Optional[CredentialsInput] = Field(None, description="New credentials (updates Vault)")
    tool_prefix: Optional[str] = Field(None, max_length=100)
    enabled: Optional[bool] = None


class ExternalMCPServerResponse(BaseModel):
    """External MCP server response."""
    id: UUID
    name: str
    display_name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    base_url: str
    transport: TransportTypeEnum
    auth_type: AuthTypeEnum
    tool_prefix: Optional[str] = None
    enabled: bool = True
    health_status: HealthStatusEnum = HealthStatusEnum.UNKNOWN
    last_health_check: Optional[datetime] = None
    last_sync_at: Optional[datetime] = None
    sync_error: Optional[str] = None
    tenant_id: Optional[str] = None
    tools_count: int = 0
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ExternalMCPServerDetailResponse(ExternalMCPServerResponse):
    """External MCP server detail response with tools."""
    tools: List[ExternalMCPServerToolResponse] = []


class ExternalMCPServerListResponse(BaseModel):
    """Response for listing external MCP servers."""
    servers: List[ExternalMCPServerResponse]
    total_count: int
    page: int
    page_size: int


# ============== Test Connection Schemas ==============

class TestConnectionResponse(BaseModel):
    """Response from test-connection endpoint."""
    success: bool
    latency_ms: Optional[int] = None
    error: Optional[str] = None
    server_info: Optional[dict] = None
    tools_discovered: Optional[int] = None


# ============== Sync Tools Schemas ==============

class SyncToolsResponse(BaseModel):
    """Response from sync-tools endpoint."""
    synced_count: int
    removed_count: int
    tools: List[ExternalMCPServerToolResponse] = []


# ============== Gateway Internal Schemas ==============

class ExternalMCPServerForGateway(BaseModel):
    """External MCP server with credentials for gateway use."""
    id: UUID
    name: str
    base_url: str
    transport: TransportTypeEnum
    auth_type: AuthTypeEnum
    credentials: Optional[dict] = None  # Decrypted credentials from Vault
    tool_prefix: Optional[str] = None
    tenant_id: Optional[str] = None
    tools: List[ExternalMCPServerToolResponse] = []

    model_config = ConfigDict(from_attributes=True)


class ExternalMCPServersForGatewayResponse(BaseModel):
    """Response for gateway internal endpoint."""
    servers: List[ExternalMCPServerForGateway]
