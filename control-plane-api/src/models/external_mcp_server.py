# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""External MCP Server SQLAlchemy models.

Models for registering and managing external MCP servers
(Linear, GitHub, Slack, etc.) that STOA proxies with governance.

Reference: External MCP Server Registration Plan
"""
from sqlalchemy import (
    Column,
    String,
    DateTime,
    Enum as SQLEnum,
    Text,
    Index,
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


class ExternalMCPTransport(str, enum.Enum):
    """Transport protocol for external MCP server."""
    SSE = "sse"           # Server-Sent Events (Claude Desktop compatible)
    HTTP = "http"         # HTTP JSON-RPC
    WEBSOCKET = "websocket"  # WebSocket


class ExternalMCPAuthType(str, enum.Enum):
    """Authentication type for external MCP server."""
    NONE = "none"              # No authentication
    API_KEY = "api_key"        # API key in header
    BEARER_TOKEN = "bearer_token"  # Bearer token
    OAUTH2 = "oauth2"          # OAuth2 flow


class ExternalMCPHealthStatus(str, enum.Enum):
    """Health status of external MCP server."""
    UNKNOWN = "unknown"     # Not yet checked
    HEALTHY = "healthy"     # Connection successful
    DEGRADED = "degraded"   # Partial issues
    UNHEALTHY = "unhealthy"  # Connection failed


class ExternalMCPServer(Base):
    """External MCP Server model - registered external servers like Linear, GitHub."""
    __tablename__ = "external_mcp_servers"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Server identity
    name = Column(String(255), unique=True, nullable=False)  # Slug, e.g., "linear"
    display_name = Column(String(255), nullable=False)       # "Linear"
    description = Column(Text, nullable=True)
    icon = Column(String(500), nullable=True)  # URL to icon

    # Connection configuration
    base_url = Column(String(500), nullable=False)  # e.g., "https://mcp.linear.app/sse"
    transport = Column(
        SQLEnum(ExternalMCPTransport, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ExternalMCPTransport.SSE
    )

    # Authentication configuration
    auth_type = Column(
        SQLEnum(ExternalMCPAuthType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ExternalMCPAuthType.NONE
    )
    credential_vault_path = Column(String(500), nullable=True)  # Path to credentials in Vault

    # Tool configuration
    tool_prefix = Column(String(100), nullable=True)  # e.g., "linear" -> "linear__create_issue"

    # Status
    enabled = Column(Boolean, nullable=False, default=True)
    health_status = Column(
        SQLEnum(ExternalMCPHealthStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ExternalMCPHealthStatus.UNKNOWN
    )
    last_health_check = Column(DateTime, nullable=True)
    last_sync_at = Column(DateTime, nullable=True)
    sync_error = Column(Text, nullable=True)

    # Multi-tenancy (null = platform-wide)
    tenant_id = Column(String(255), nullable=True, index=True)

    # Timestamps and audit
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(255), nullable=True)  # Admin user ID

    # Relationships
    tools = relationship(
        "ExternalMCPServerTool",
        back_populates="server",
        cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index('ix_external_mcp_servers_tenant_enabled', 'tenant_id', 'enabled'),
    )

    def __repr__(self) -> str:
        return f"<ExternalMCPServer {self.name} url={self.base_url}>"


class ExternalMCPServerTool(Base):
    """Tool discovered from an external MCP server."""
    __tablename__ = "external_mcp_server_tools"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Server reference
    server_id = Column(
        UUID(as_uuid=True),
        ForeignKey("external_mcp_servers.id", ondelete="CASCADE"),
        nullable=False
    )

    # Tool identity
    name = Column(String(255), nullable=False)  # Original name from external server
    namespaced_name = Column(String(255), nullable=False)  # {prefix}__{name} or just {name}
    display_name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)

    # Tool configuration
    input_schema = Column(JSON, nullable=True)  # JSON Schema for tool inputs
    enabled = Column(Boolean, nullable=False, default=True)

    # Sync tracking
    synced_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationship
    server = relationship("ExternalMCPServer", back_populates="tools")

    # Indexes
    __table_args__ = (
        Index('ix_external_mcp_server_tools_server_name', 'server_id', 'name', unique=True),
        Index('ix_external_mcp_server_tools_namespaced', 'namespaced_name'),
    )

    def __repr__(self) -> str:
        return f"<ExternalMCPServerTool {self.namespaced_name} server_id={self.server_id}>"
