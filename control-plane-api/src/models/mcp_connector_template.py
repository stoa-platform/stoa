"""MCP Connector Template and OAuth Pending Session models.

Pre-configured connector catalog for one-click OAuth integrations
(App Store pattern: browse, click Connect, authorize, done).
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from src.database import Base


class MCPConnectorTemplate(Base):
    """Pre-configured MCP connector template (seed data for the catalog)."""

    __tablename__ = "mcp_connector_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    icon_url = Column(String(500), nullable=True)
    category = Column(String(100), nullable=False)

    # MCP connection
    mcp_base_url = Column(String(500), nullable=False)
    transport = Column(String(20), nullable=False, default="sse")

    # OAuth configuration
    oauth_authorize_url = Column(String(500), nullable=False)
    oauth_token_url = Column(String(500), nullable=False)
    oauth_scopes = Column(String(500), nullable=True)
    oauth_pkce_required = Column(Boolean, nullable=False, default=False)
    oauth_client_id = Column(String(255), nullable=True)  # Public OAuth app client_id (not a secret)
    oauth_registration_url = Column(String(500), nullable=True)  # RFC 7591 DCR endpoint (one-click connect)

    # Metadata
    documentation_url = Column(String(500), nullable=True)
    is_featured = Column(Boolean, nullable=False, default=False)
    enabled = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<MCPConnectorTemplate {self.slug}>"


class OAuthPendingSession(Base):
    """Ephemeral OAuth session for CSRF protection during the authorize flow."""

    __tablename__ = "oauth_pending_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    state = Column(String(255), unique=True, nullable=False, index=True)
    connector_template_id = Column(
        UUID(as_uuid=True),
        ForeignKey("mcp_connector_templates.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(String(255), nullable=False)
    tenant_id = Column(String(255), nullable=True)
    code_verifier = Column(String(128), nullable=True)
    client_secret = Column(String(500), nullable=True)  # Non-DCR providers: passed through from setup dialog
    redirect_after = Column(String(500), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)

    def __repr__(self) -> str:
        return f"<OAuthPendingSession state={self.state[:8]}...>"
