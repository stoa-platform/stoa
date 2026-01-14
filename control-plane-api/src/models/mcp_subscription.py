"""MCP Server Subscription SQLAlchemy models.

Models for MCP Server subscriptions with per-tool access control
and admin approval workflow.

Reference: PLAN-MCP-SUBSCRIPTIONS.md
"""
from sqlalchemy import (
    Column,
    String,
    DateTime,
    Enum as SQLEnum,
    Text,
    Index,
    Integer,
    Boolean,
    ForeignKey,
    JSON,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from src.database import Base


class MCPServerCategory(str, enum.Enum):
    """Category of MCP Server."""
    PLATFORM = "platform"   # STOA platform tools (admin-only)
    TENANT = "tenant"       # Tenant-specific APIs
    PUBLIC = "public"       # Publicly available APIs


class MCPServerStatus(str, enum.Enum):
    """Status of an MCP Server."""
    ACTIVE = "active"
    MAINTENANCE = "maintenance"
    DEPRECATED = "deprecated"


class MCPSubscriptionStatus(str, enum.Enum):
    """MCP Subscription status enum."""
    PENDING = "pending"       # Awaiting approval (if required)
    ACTIVE = "active"         # Active subscription
    SUSPENDED = "suspended"   # Temporarily suspended
    REVOKED = "revoked"       # Permanently revoked
    EXPIRED = "expired"       # Auto-expired


class MCPToolAccessStatus(str, enum.Enum):
    """Status of tool access within a subscription."""
    ENABLED = "enabled"
    DISABLED = "disabled"
    PENDING_APPROVAL = "pending_approval"


class MCPServer(Base):
    """MCP Server model - a collection of related tools."""
    __tablename__ = "mcp_servers"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Server identity
    name = Column(String(255), unique=True, nullable=False)
    display_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    icon = Column(String(500), nullable=True)

    # Categorization
    category = Column(
        SQLEnum(MCPServerCategory, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=MCPServerCategory.PUBLIC
    )
    tenant_id = Column(String(255), nullable=True, index=True)  # For tenant-specific servers

    # Visibility control (JSON with roles configuration)
    visibility = Column(JSON, nullable=False, default={"public": True})

    # Subscription settings
    requires_approval = Column(Boolean, nullable=False, default=False)
    auto_approve_roles = Column(JSON, nullable=True)  # Roles that get auto-approved

    # Status
    status = Column(
        SQLEnum(MCPServerStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=MCPServerStatus.ACTIVE
    )
    version = Column(String(50), nullable=True)
    documentation_url = Column(String(500), nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    tools = relationship("MCPServerTool", back_populates="server", cascade="all, delete-orphan")
    subscriptions = relationship("MCPServerSubscription", back_populates="server")

    # Indexes
    __table_args__ = (
        Index('ix_mcp_servers_category_status', 'category', 'status'),
        Index('ix_mcp_servers_tenant_status', 'tenant_id', 'status'),
    )

    def __repr__(self) -> str:
        return f"<MCPServer {self.name} category={self.category.value}>"


class MCPServerTool(Base):
    """Tool within an MCP Server."""
    __tablename__ = "mcp_server_tools"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Server reference
    server_id = Column(UUID(as_uuid=True), ForeignKey("mcp_servers.id"), nullable=False)

    # Tool identity
    name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)

    # Tool configuration
    input_schema = Column(JSON, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    requires_approval = Column(Boolean, nullable=False, default=False)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    server = relationship("MCPServer", back_populates="tools")

    # Indexes
    __table_args__ = (
        Index('ix_mcp_server_tools_server_name', 'server_id', 'name', unique=True),
    )

    def __repr__(self) -> str:
        return f"<MCPServerTool {self.name} server_id={self.server_id}>"


class MCPServerSubscription(Base):
    """MCP Server subscription model with approval workflow."""
    __tablename__ = "mcp_server_subscriptions"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Server reference
    server_id = Column(UUID(as_uuid=True), ForeignKey("mcp_servers.id"), nullable=False, index=True)

    # Subscriber info
    subscriber_id = Column(String(255), nullable=False, index=True)  # Keycloak user ID
    subscriber_email = Column(String(255), nullable=False)
    tenant_id = Column(String(255), nullable=False, index=True)

    # Subscription plan
    plan = Column(String(100), nullable=False, default="free")

    # API Key (hashed for security - actual key in Vault)
    api_key_hash = Column(String(512), nullable=True, unique=True)
    api_key_prefix = Column(String(16), nullable=True)  # stoa_mcp_ + first 8 chars

    # Vault reference for API key
    vault_path = Column(String(500), nullable=True)

    # Key rotation with grace period
    previous_api_key_hash = Column(String(512), nullable=True, index=True)
    previous_key_expires_at = Column(DateTime, nullable=True)
    last_rotated_at = Column(DateTime, nullable=True)
    rotation_count = Column(Integer, nullable=False, default=0)

    # Status and approval
    status = Column(
        SQLEnum(MCPSubscriptionStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=MCPSubscriptionStatus.PENDING
    )
    status_reason = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    approved_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)

    # Audit fields
    approved_by = Column(String(255), nullable=True)  # Admin user ID who approved
    revoked_by = Column(String(255), nullable=True)   # Admin user ID who revoked

    # Usage tracking
    usage_count = Column(Integer, nullable=False, default=0)

    # Relationships
    server = relationship("MCPServer", back_populates="subscriptions")
    tool_access = relationship("MCPToolAccess", back_populates="subscription", cascade="all, delete-orphan")

    # Indexes for common queries
    __table_args__ = (
        Index('ix_mcp_subs_subscriber_server', 'subscriber_id', 'server_id'),
        Index('ix_mcp_subs_tenant_status', 'tenant_id', 'status'),
        Index('ix_mcp_subs_server_status', 'server_id', 'status'),
    )

    def __repr__(self) -> str:
        return f"<MCPServerSubscription {self.id} user={self.subscriber_id} server={self.server_id}>"


class MCPToolAccess(Base):
    """Per-tool access control within a subscription."""
    __tablename__ = "mcp_tool_access"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Subscription reference
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("mcp_server_subscriptions.id"), nullable=False)

    # Tool reference (by name, as tools can be from different servers)
    tool_id = Column(UUID(as_uuid=True), nullable=False)
    tool_name = Column(String(255), nullable=False)

    # Access status
    status = Column(
        SQLEnum(MCPToolAccessStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=MCPToolAccessStatus.ENABLED
    )

    # Approval tracking
    granted_at = Column(DateTime, nullable=True)
    granted_by = Column(String(255), nullable=True)

    # Usage tracking
    usage_count = Column(Integer, nullable=False, default=0)
    last_used_at = Column(DateTime, nullable=True)

    # Relationship
    subscription = relationship("MCPServerSubscription", back_populates="tool_access")

    # Indexes
    __table_args__ = (
        Index('ix_mcp_tool_access_sub_tool', 'subscription_id', 'tool_id', unique=True),
    )

    def __repr__(self) -> str:
        return f"<MCPToolAccess {self.tool_name} status={self.status.value}>"
