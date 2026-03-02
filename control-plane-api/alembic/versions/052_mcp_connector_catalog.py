"""MCP Connector Catalog — pre-configured OAuth connectors (App Store pattern).

Creates:
- mcp_connector_templates: seed data catalog of pre-configured providers
- oauth_pending_sessions: ephemeral CSRF-protected OAuth state
- Adds connector_template_id FK to external_mcp_servers

Seeds 5 connector templates: Linear, GitHub, Notion, Slack, Sentry.

Revision ID: 052_mcp_connector_catalog
Revises: 051_unique_personal_tenant_owner
Create Date: 2026-03-02
"""

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "052_mcp_connector_catalog"
down_revision = "051_unique_personal_tenant_owner"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- mcp_connector_templates ---
    op.create_table(
        "mcp_connector_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(100), unique=True, nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("icon_url", sa.String(500), nullable=True),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("mcp_base_url", sa.String(500), nullable=False),
        sa.Column("transport", sa.String(20), nullable=False, server_default="sse"),
        sa.Column("oauth_authorize_url", sa.String(500), nullable=False),
        sa.Column("oauth_token_url", sa.String(500), nullable=False),
        sa.Column("oauth_scopes", sa.String(500), nullable=True),
        sa.Column("oauth_pkce_required", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("documentation_url", sa.String(500), nullable=True),
        sa.Column("is_featured", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_mcp_connector_templates_slug", "mcp_connector_templates", ["slug"], unique=True)
    op.create_index("ix_mcp_connector_templates_category", "mcp_connector_templates", ["category"])
    op.create_index("ix_mcp_connector_templates_enabled", "mcp_connector_templates", ["enabled"])

    # --- oauth_pending_sessions ---
    op.create_table(
        "oauth_pending_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("state", sa.String(255), unique=True, nullable=False),
        sa.Column(
            "connector_template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mcp_connector_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=True),
        sa.Column("code_verifier", sa.String(128), nullable=True),
        sa.Column("redirect_after", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_oauth_pending_sessions_state", "oauth_pending_sessions", ["state"], unique=True)
    op.create_index("ix_oauth_pending_sessions_expires", "oauth_pending_sessions", ["expires_at"])

    # --- Add connector_template_id FK to external_mcp_servers ---
    op.add_column(
        "external_mcp_servers",
        sa.Column(
            "connector_template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mcp_connector_templates.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # --- Seed 5 connector templates ---
    templates = [
        {
            "id": str(uuid.uuid4()),
            "slug": "linear",
            "display_name": "Linear",
            "description": "Project management and issue tracking for software teams",
            "icon_url": "https://linear.app/favicon.ico",
            "category": "project-management",
            "mcp_base_url": "https://mcp.linear.app/sse",
            "transport": "sse",
            "oauth_authorize_url": "https://linear.app/oauth/authorize",
            "oauth_token_url": "https://api.linear.app/oauth/token",
            "oauth_scopes": "read write",
            "oauth_pkce_required": True,
            "documentation_url": "https://developers.linear.app/docs/oauth",
            "is_featured": True,
            "enabled": True,
            "sort_order": 1,
        },
        {
            "id": str(uuid.uuid4()),
            "slug": "github",
            "display_name": "GitHub",
            "description": "Code hosting, pull requests, and CI/CD for developers",
            "icon_url": "https://github.com/favicon.ico",
            "category": "development",
            "mcp_base_url": "https://api.githubcopilot.com/mcp/",
            "transport": "http",
            "oauth_authorize_url": "https://github.com/login/oauth/authorize",
            "oauth_token_url": "https://github.com/login/oauth/access_token",
            "oauth_scopes": "repo read:org",
            "oauth_pkce_required": False,
            "documentation_url": "https://docs.github.com/en/apps/oauth-apps",
            "is_featured": True,
            "enabled": True,
            "sort_order": 2,
        },
        {
            "id": str(uuid.uuid4()),
            "slug": "notion",
            "display_name": "Notion",
            "description": "All-in-one workspace for notes, docs, and knowledge management",
            "icon_url": "https://www.notion.so/favicon.ico",
            "category": "project-management",
            "mcp_base_url": "https://mcp.notion.so/sse",
            "transport": "sse",
            "oauth_authorize_url": "https://api.notion.com/v1/oauth/authorize",
            "oauth_token_url": "https://api.notion.com/v1/oauth/token",
            "oauth_scopes": "",
            "oauth_pkce_required": False,
            "documentation_url": "https://developers.notion.com/docs/authorization",
            "is_featured": True,
            "enabled": True,
            "sort_order": 3,
        },
        {
            "id": str(uuid.uuid4()),
            "slug": "slack",
            "display_name": "Slack",
            "description": "Team messaging, channels, and integrations for collaboration",
            "icon_url": "https://slack.com/favicon.ico",
            "category": "communication",
            "mcp_base_url": "https://mcp.slack.com/sse",
            "transport": "sse",
            "oauth_authorize_url": "https://slack.com/oauth/v2/authorize",
            "oauth_token_url": "https://slack.com/api/oauth.v2.access",
            "oauth_scopes": "channels:read chat:write",
            "oauth_pkce_required": False,
            "documentation_url": "https://api.slack.com/authentication/oauth-v2",
            "is_featured": False,
            "enabled": True,
            "sort_order": 4,
        },
        {
            "id": str(uuid.uuid4()),
            "slug": "sentry",
            "display_name": "Sentry",
            "description": "Error tracking and performance monitoring for applications",
            "icon_url": "https://sentry.io/favicon.ico",
            "category": "monitoring",
            "mcp_base_url": "https://mcp.sentry.dev/sse",
            "transport": "sse",
            "oauth_authorize_url": "https://sentry.io/oauth/authorize/",
            "oauth_token_url": "https://sentry.io/oauth/token/",
            "oauth_scopes": "project:read event:read",
            "oauth_pkce_required": False,
            "documentation_url": "https://docs.sentry.io/api/auth/",
            "is_featured": False,
            "enabled": True,
            "sort_order": 5,
        },
    ]

    mct = sa.table(
        "mcp_connector_templates",
        sa.column("id", postgresql.UUID),
        sa.column("slug", sa.String),
        sa.column("display_name", sa.String),
        sa.column("description", sa.Text),
        sa.column("icon_url", sa.String),
        sa.column("category", sa.String),
        sa.column("mcp_base_url", sa.String),
        sa.column("transport", sa.String),
        sa.column("oauth_authorize_url", sa.String),
        sa.column("oauth_token_url", sa.String),
        sa.column("oauth_scopes", sa.String),
        sa.column("oauth_pkce_required", sa.Boolean),
        sa.column("documentation_url", sa.String),
        sa.column("is_featured", sa.Boolean),
        sa.column("enabled", sa.Boolean),
        sa.column("sort_order", sa.Integer),
    )

    op.bulk_insert(mct, templates)


def downgrade() -> None:
    op.drop_column("external_mcp_servers", "connector_template_id")
    op.drop_index("ix_oauth_pending_sessions_expires", table_name="oauth_pending_sessions")
    op.drop_index("ix_oauth_pending_sessions_state", table_name="oauth_pending_sessions")
    op.drop_table("oauth_pending_sessions")
    op.drop_index("ix_mcp_connector_templates_enabled", table_name="mcp_connector_templates")
    op.drop_index("ix_mcp_connector_templates_category", table_name="mcp_connector_templates")
    op.drop_index("ix_mcp_connector_templates_slug", table_name="mcp_connector_templates")
    op.drop_table("mcp_connector_templates")
