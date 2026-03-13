"""Add 5 new DCR-capable MCP connectors to the catalog.

Discovered via RFC 9728 / RFC 8414 OAuth metadata probing:
- Cloudflare (mcp.cloudflare.com) — DNS, Workers, KV, R2
- Asana (mcp.asana.com) — project management
- Stripe (mcp.stripe.com) — payments, billing
- Vercel (mcp.vercel.com) — deployments, hosting
- Notion (mcp.notion.com) — notes, knowledge base (corrected URL from .so)

Also re-enables Notion with correct MCP URL (mcp.notion.com, not mcp.notion.so)
and updates it to use DCR endpoints.

All 5 providers support full DCR (RFC 7591) with PKCE S256 and
token_endpoint_auth_methods: ["none"] — enabling one-click connect
without manual OAuth app creation.

Revision ID: 071_add_dcr_connectors
Revises: 070_disable_non_dcr_connectors
Create Date: 2026-03-13
"""

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "071_add_dcr_connectors"
down_revision = "070_disable_non_dcr_connectors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Update Notion: fix MCP URL (.com not .so) + add DCR endpoints + re-enable ---
    op.execute(
        sa.text(
            """
            UPDATE mcp_connector_templates SET
                mcp_base_url = 'https://mcp.notion.com/sse',
                oauth_authorize_url = 'https://mcp.notion.com/authorize',
                oauth_token_url = 'https://mcp.notion.com/token',
                oauth_registration_url = 'https://mcp.notion.com/register',
                oauth_scopes = NULL,
                oauth_pkce_required = true,
                enabled = true,
                is_featured = true
            WHERE slug = 'notion'
            """
        )
    )

    # --- Insert 4 new DCR-capable connectors ---
    templates = [
        {
            "id": str(uuid.uuid4()),
            "slug": "cloudflare",
            "display_name": "Cloudflare",
            "description": "DNS management, Workers, KV storage, R2 buckets, and edge computing",
            "icon_url": "https://www.cloudflare.com/favicon.ico",
            "category": "infrastructure",
            "mcp_base_url": "https://mcp.cloudflare.com/sse",
            "transport": "sse",
            "oauth_authorize_url": "https://mcp.cloudflare.com/authorize",
            "oauth_token_url": "https://mcp.cloudflare.com/token",
            "oauth_scopes": None,
            "oauth_pkce_required": True,
            "oauth_registration_url": "https://mcp.cloudflare.com/register",
            "documentation_url": "https://developers.cloudflare.com/agents/model-context-protocol/",
            "is_featured": True,
            "enabled": True,
            "sort_order": 6,
        },
        {
            "id": str(uuid.uuid4()),
            "slug": "asana",
            "display_name": "Asana",
            "description": "Work management and project tracking for teams",
            "icon_url": "https://asana.com/favicon.ico",
            "category": "project-management",
            "mcp_base_url": "https://mcp.asana.com/sse",
            "transport": "sse",
            "oauth_authorize_url": "https://mcp.asana.com/authorize",
            "oauth_token_url": "https://mcp.asana.com/token",
            "oauth_scopes": "default",
            "oauth_pkce_required": True,
            "oauth_registration_url": "https://mcp.asana.com/register",
            "documentation_url": "https://developers.asana.com/docs/mcp-server",
            "is_featured": False,
            "enabled": True,
            "sort_order": 7,
        },
        {
            "id": str(uuid.uuid4()),
            "slug": "stripe",
            "display_name": "Stripe",
            "description": "Payment processing, billing, and financial infrastructure",
            "icon_url": "https://stripe.com/favicon.ico",
            "category": "finance",
            "mcp_base_url": "https://mcp.stripe.com/sse",
            "transport": "sse",
            "oauth_authorize_url": "https://access.stripe.com/mcp/oauth2/authorize",
            "oauth_token_url": "https://access.stripe.com/mcp/oauth2/token",
            "oauth_scopes": None,
            "oauth_pkce_required": True,
            "oauth_registration_url": "https://access.stripe.com/mcp/oauth2/register",
            "documentation_url": "https://docs.stripe.com/mcp",
            "is_featured": True,
            "enabled": True,
            "sort_order": 8,
        },
        {
            "id": str(uuid.uuid4()),
            "slug": "vercel",
            "display_name": "Vercel",
            "description": "Frontend deployment, hosting, and serverless functions",
            "icon_url": "https://vercel.com/favicon.ico",
            "category": "infrastructure",
            "mcp_base_url": "https://mcp.vercel.com/sse",
            "transport": "sse",
            "oauth_authorize_url": "https://vercel.com/oauth/authorize",
            "oauth_token_url": "https://vercel.com/api/login/oauth/token",
            "oauth_scopes": "openid email offline_access profile",
            "oauth_pkce_required": True,
            "oauth_registration_url": "https://vercel.com/api/login/oauth/register",
            "documentation_url": "https://vercel.com/docs/mcp/vercel-mcp",
            "is_featured": False,
            "enabled": True,
            "sort_order": 9,
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
        sa.column("oauth_registration_url", sa.String),
        sa.column("documentation_url", sa.String),
        sa.column("is_featured", sa.Boolean),
        sa.column("enabled", sa.Boolean),
        sa.column("sort_order", sa.Integer),
    )

    op.bulk_insert(mct, templates)


def downgrade() -> None:
    # Remove the 4 new connectors
    op.execute(
        sa.text(
            """
            DELETE FROM mcp_connector_templates
            WHERE slug IN ('cloudflare', 'asana', 'stripe', 'vercel')
            """
        )
    )

    # Restore Notion to original state (disabled, old URLs)
    op.execute(
        sa.text(
            """
            UPDATE mcp_connector_templates SET
                mcp_base_url = 'https://mcp.notion.so/sse',
                oauth_authorize_url = 'https://api.notion.com/v1/oauth/authorize',
                oauth_token_url = 'https://api.notion.com/v1/oauth/token',
                oauth_registration_url = NULL,
                oauth_scopes = '',
                oauth_pkce_required = false,
                enabled = false,
                is_featured = true
            WHERE slug = 'notion'
            """
        )
    )
