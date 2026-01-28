# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""MCP Server models for server-based subscriptions.

Servers are grouped collections of tools with unified subscription management
and role-based visibility.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, Field
from sqlalchemy import Column, String, Boolean, DateTime, JSON, Enum as SQLEnum, ForeignKey, Table
from sqlalchemy.orm import relationship

from .subscription import Base


class ServerCategory(str, Enum):
    """Category of MCP Server."""
    PLATFORM = "platform"   # STOA platform tools (admin-only)
    TENANT = "tenant"       # Tenant-specific APIs
    PUBLIC = "public"       # Publicly available APIs


class ServerStatus(str, Enum):
    """Status of an MCP Server."""
    ACTIVE = "active"
    MAINTENANCE = "maintenance"
    DEPRECATED = "deprecated"


class ToolAccessStatus(str, Enum):
    """Status of tool access within a subscription."""
    ENABLED = "enabled"
    DISABLED = "disabled"
    PENDING_APPROVAL = "pending_approval"


class ServerSubscriptionStatus(str, Enum):
    """Status of a server subscription."""
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


# ============ SQLAlchemy Models ============

class MCPServerModel(Base):
    """SQLAlchemy model for MCP Servers."""
    __tablename__ = "mcp_servers"

    id = Column(String, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    display_name = Column(String, nullable=False)
    description = Column(String, nullable=False)
    icon = Column(String, nullable=True)
    category = Column(SQLEnum(ServerCategory), nullable=False, default=ServerCategory.TENANT)
    tenant_id = Column(String, nullable=True)  # For tenant-specific servers

    # Visibility control (JSON)
    visibility = Column(JSON, nullable=False, default={"public": True})

    status = Column(SQLEnum(ServerStatus), nullable=False, default=ServerStatus.ACTIVE)
    version = Column(String, nullable=True)
    documentation_url = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    tools = relationship("MCPServerToolModel", back_populates="server", cascade="all, delete-orphan")
    subscriptions = relationship("ServerSubscriptionModel", back_populates="server")


class MCPServerToolModel(Base):
    """SQLAlchemy model for tools within a server."""
    __tablename__ = "mcp_server_tools"

    id = Column(String, primary_key=True)
    server_id = Column(String, ForeignKey("mcp_servers.id"), nullable=False)
    name = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    description = Column(String, nullable=False)
    input_schema = Column(JSON, nullable=True)
    enabled = Column(Boolean, default=True)
    requires_approval = Column(Boolean, default=False)

    # Relationship
    server = relationship("MCPServerModel", back_populates="tools")


class ServerSubscriptionModel(Base):
    """SQLAlchemy model for server subscriptions."""
    __tablename__ = "server_subscriptions"

    id = Column(String, primary_key=True)
    server_id = Column(String, ForeignKey("mcp_servers.id"), nullable=False)
    tenant_id = Column(String, nullable=False)
    user_id = Column(String, nullable=False)
    status = Column(SQLEnum(ServerSubscriptionStatus), nullable=False, default=ServerSubscriptionStatus.PENDING)
    plan = Column(String, default="free")

    # API key (encrypted in production)
    api_key_hash = Column(String, nullable=True)
    api_key_prefix = Column(String, nullable=True)  # First 12 chars for display

    # Key rotation
    last_rotated_at = Column(DateTime, nullable=True)
    previous_key_expires_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)

    # Relationships
    server = relationship("MCPServerModel", back_populates="subscriptions")
    tool_access = relationship("ToolAccessModel", back_populates="subscription", cascade="all, delete-orphan")


class ToolAccessModel(Base):
    """SQLAlchemy model for per-tool access within a subscription."""
    __tablename__ = "tool_access"

    id = Column(String, primary_key=True)
    subscription_id = Column(String, ForeignKey("server_subscriptions.id"), nullable=False)
    tool_id = Column(String, nullable=False)
    tool_name = Column(String, nullable=False)
    status = Column(SQLEnum(ToolAccessStatus), nullable=False, default=ToolAccessStatus.ENABLED)
    granted_at = Column(DateTime, nullable=True)
    granted_by = Column(String, nullable=True)

    # Relationship
    subscription = relationship("ServerSubscriptionModel", back_populates="tool_access")


# ============ Pydantic Schemas ============

class MCPServerVisibility(BaseModel):
    """Visibility configuration for MCP Servers."""
    roles: Optional[List[str]] = Field(None, description="Required roles to see this server")
    exclude_roles: Optional[List[str]] = Field(None, description="Roles that cannot see this server")
    public: bool = Field(False, description="If true, visible to all authenticated users")


class MCPServerTool(BaseModel):
    """Tool within an MCP Server."""
    id: str
    name: str
    display_name: str = Field(..., alias="displayName")
    description: str
    input_schema: Optional[dict] = Field(None, alias="inputSchema")
    enabled: bool = True
    requires_approval: bool = False

    class Config:
        populate_by_name = True


class MCPServer(BaseModel):
    """MCP Server - a collection of related tools."""
    id: str
    name: str
    display_name: str = Field(..., alias="displayName")
    description: str
    icon: Optional[str] = None
    category: ServerCategory
    tenant_id: Optional[str] = None
    visibility: MCPServerVisibility
    tools: List[MCPServerTool] = []
    status: ServerStatus = ServerStatus.ACTIVE
    version: Optional[str] = None
    documentation_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True
        from_attributes = True


class ToolAccess(BaseModel):
    """Per-tool access control within a subscription."""
    tool_id: str
    tool_name: str
    status: ToolAccessStatus
    granted_at: Optional[datetime] = None
    granted_by: Optional[str] = None


class ServerSubscription(BaseModel):
    """Server subscription with per-tool access control."""
    id: str
    server_id: str
    server: Optional[MCPServer] = None
    tenant_id: str
    user_id: str
    status: ServerSubscriptionStatus
    plan: str = "free"
    tool_access: List[ToolAccess] = []
    api_key_prefix: Optional[str] = None
    last_rotated_at: Optional[datetime] = None
    has_active_grace_period: bool = False
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ServerSubscriptionWithKey(ServerSubscription):
    """Server subscription with full API key (shown only on creation)."""
    api_key: str


class ServerSubscriptionCreate(BaseModel):
    """Request to create a server subscription."""
    server_id: str
    plan: str = "free"
    requested_tools: List[str] = Field(..., description="Tool IDs to request access to")


class ToolAccessUpdate(BaseModel):
    """Request to update tool access within a subscription."""
    tool_ids: List[str]
    action: str = Field(..., description="Action: enable, disable, or request")


# ============ Response Models ============

class ListServersResponse(BaseModel):
    """Response for listing MCP servers."""
    servers: List[MCPServer]
    total_count: int


class ListServerSubscriptionsResponse(BaseModel):
    """Response for listing server subscriptions."""
    subscriptions: List[ServerSubscription]
    total_count: int
