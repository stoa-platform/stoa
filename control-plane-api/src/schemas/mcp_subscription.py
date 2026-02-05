"""Pydantic schemas for MCP Server subscription endpoints.

Reference: PLAN-MCP-SUBSCRIPTIONS.md
"""
from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ============== Enums ==============

class MCPServerCategoryEnum(str, Enum):
    """MCP Server category for API responses."""
    PLATFORM = "platform"
    TENANT = "tenant"
    PUBLIC = "public"


class MCPServerStatusEnum(str, Enum):
    """MCP Server status for API responses."""
    ACTIVE = "active"
    MAINTENANCE = "maintenance"
    DEPRECATED = "deprecated"


class MCPSubscriptionStatusEnum(str, Enum):
    """MCP Subscription status for API responses."""
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    EXPIRED = "expired"


class MCPToolAccessStatusEnum(str, Enum):
    """Tool access status for API responses."""
    ENABLED = "enabled"
    DISABLED = "disabled"
    PENDING_APPROVAL = "pending_approval"


# ============== Server Schemas ==============

class MCPServerVisibility(BaseModel):
    """Visibility configuration for MCP Servers."""
    roles: list[str] | None = Field(None, description="Required roles to see this server")
    exclude_roles: list[str] | None = Field(None, description="Roles that cannot see this server")
    public: bool = Field(True, description="If true, visible to all authenticated users")


class MCPServerToolResponse(BaseModel):
    """Tool within an MCP Server."""
    id: UUID
    name: str
    display_name: str
    description: str
    input_schema: dict | None = None
    enabled: bool = True
    requires_approval: bool = False

    model_config = ConfigDict(from_attributes=True)


class MCPServerResponse(BaseModel):
    """MCP Server response."""
    id: UUID
    name: str
    display_name: str
    description: str
    icon: str | None = None
    category: MCPServerCategoryEnum
    tenant_id: str | None = None
    visibility: MCPServerVisibility
    requires_approval: bool = False
    status: MCPServerStatusEnum
    version: str | None = None
    documentation_url: str | None = None
    tools: list[MCPServerToolResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MCPServerListResponse(BaseModel):
    """Response for listing MCP servers."""
    servers: list[MCPServerResponse]
    total_count: int


class MCPServerCreate(BaseModel):
    """Schema for creating a new MCP Server (admin only)."""
    name: str = Field(..., min_length=1, max_length=255)
    display_name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    icon: str | None = Field(None, max_length=500)
    category: MCPServerCategoryEnum = MCPServerCategoryEnum.PUBLIC
    tenant_id: str | None = Field(None, max_length=255)
    visibility: MCPServerVisibility = MCPServerVisibility()
    requires_approval: bool = False
    auto_approve_roles: list[str] | None = None
    version: str | None = Field(None, max_length=50)
    documentation_url: str | None = Field(None, max_length=500)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "weather-api",
                "display_name": "Weather API",
                "description": "Get weather data from various sources",
                "category": "public",
                "visibility": {"public": True},
                "requires_approval": False
            }
        }
    )


class MCPServerToolCreate(BaseModel):
    """Schema for creating a tool within a server."""
    name: str = Field(..., min_length=1, max_length=255)
    display_name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    input_schema: dict | None = None
    enabled: bool = True
    requires_approval: bool = False


# ============== Subscription Schemas ==============

class MCPToolAccessResponse(BaseModel):
    """Per-tool access control within a subscription."""
    tool_id: UUID
    tool_name: str
    status: MCPToolAccessStatusEnum
    granted_at: datetime | None = None
    granted_by: str | None = None
    usage_count: int = 0
    last_used_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class MCPSubscriptionResponse(BaseModel):
    """MCP Server subscription response."""
    id: UUID
    server_id: UUID
    server: MCPServerResponse | None = None
    subscriber_id: str
    subscriber_email: str
    tenant_id: str
    plan: str
    api_key_prefix: str | None = None
    status: MCPSubscriptionStatusEnum
    status_reason: str | None = None
    tool_access: list[MCPToolAccessResponse] = []
    last_rotated_at: datetime | None = None
    rotation_count: int = 0
    has_active_grace_period: bool = False
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None = None
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    usage_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class MCPSubscriptionWithKeyResponse(MCPSubscriptionResponse):
    """Subscription response with full API key (shown only on creation)."""
    api_key: str = Field(..., description="Full API key - shown only once!")


class MCPSubscriptionListResponse(BaseModel):
    """Response for listing subscriptions."""
    items: list[MCPSubscriptionResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class MCPSubscriptionCreate(BaseModel):
    """Schema for creating a new MCP subscription."""
    server_id: UUID
    plan: str = Field("free", max_length=100)
    requested_tools: list[UUID] = Field(
        default_factory=list,
        description="Tool IDs to request access to (empty = all enabled tools)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "server_id": "550e8400-e29b-41d4-a716-446655440000",
                "plan": "free",
                "requested_tools": []
            }
        }
    )


class MCPSubscriptionApprove(BaseModel):
    """Schema for approving a subscription."""
    expires_at: datetime | None = Field(
        None,
        description="Optional expiration date for the subscription"
    )
    approved_tools: list[UUID] | None = Field(
        None,
        description="Tool IDs to approve (None = approve all requested)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "expires_at": "2026-12-31T23:59:59Z"
            }
        }
    )


class MCPSubscriptionRevoke(BaseModel):
    """Schema for revoking a subscription."""
    reason: str = Field(..., min_length=1, max_length=500)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "reason": "Violation of terms of service"
            }
        }
    )


class MCPToolAccessUpdate(BaseModel):
    """Schema for updating tool access within a subscription."""
    tool_ids: list[UUID]
    action: str = Field(..., description="Action: enable, disable, or request")


# ============== Key Rotation Schemas ==============

class MCPKeyRotationRequest(BaseModel):
    """Schema for requesting API key rotation."""
    grace_period_hours: int = Field(
        default=24,
        ge=1,
        le=168,  # Max 7 days
        description="Number of hours the old key remains valid (1-168)"
    )


class MCPKeyRotationResponse(BaseModel):
    """Schema for key rotation response."""
    subscription_id: UUID
    new_api_key: str = Field(..., description="New API key - shown only once!")
    new_api_key_prefix: str
    old_key_expires_at: datetime
    grace_period_hours: int
    rotation_count: int


# ============== Admin Schemas ==============

class MCPPendingApprovalResponse(BaseModel):
    """Response for pending approvals (admin view)."""
    subscription: MCPSubscriptionResponse
    server_name: str
    server_display_name: str
    requested_at: datetime
    subscriber_email: str


class MCPPendingApprovalsListResponse(BaseModel):
    """Response for listing pending approvals."""
    items: list[MCPPendingApprovalResponse]
    total: int


class MCPSubscriptionStatsResponse(BaseModel):
    """Statistics about MCP subscriptions."""
    total_servers: int
    total_subscriptions: int
    by_status: dict[str, int]
    by_server: dict[str, int]
    recent_24h: int


# ============== API Key Validation (for MCP Gateway) ==============

class MCPAPIKeyValidateRequest(BaseModel):
    """Request for API key validation."""
    api_key: str


class MCPAPIKeyValidateResponse(BaseModel):
    """Response for API key validation (used by MCP Gateway)."""
    valid: bool
    subscription_id: str | None = None
    server_id: str | None = None
    subscriber_id: str | None = None
    tenant_id: str | None = None
    plan: str | None = None
    enabled_tools: list[str] | None = None
    warning: str | None = None  # For grace period warnings
    using_previous_key: bool = False
    key_expires_at: datetime | None = None
