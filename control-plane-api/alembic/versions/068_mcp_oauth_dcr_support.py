"""Add MCP OAuth DCR (Dynamic Client Registration) support.

Providers like Linear and Sentry expose RFC 7591 registration endpoints
via MCP OAuth discovery (RFC 9728 + RFC 8414). This enables one-click
connect without manual OAuth app creation.

Changes:
- Add oauth_registration_url column to mcp_connector_templates
- Update Linear and Sentry templates with MCP OAuth endpoints (discovered
  from their .well-known metadata)

Revision ID: 068_mcp_oauth_dcr_support
Revises: 067_connector_oauth_client_id
Create Date: 2026-03-13
"""

import sqlalchemy as sa
from alembic import op

revision = "068_mcp_oauth_dcr_support"
down_revision = "067_connector_oauth_client_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add registration_url column for DCR-capable providers
    op.add_column(
        "mcp_connector_templates",
        sa.Column("oauth_registration_url", sa.String(500), nullable=True),
    )

    # Update Linear: use MCP OAuth endpoints (discovered from mcp.linear.app)
    op.execute(
        sa.text(
            """
            UPDATE mcp_connector_templates SET
                oauth_authorize_url = 'https://mcp.linear.app/authorize',
                oauth_token_url = 'https://mcp.linear.app/token',
                oauth_registration_url = 'https://mcp.linear.app/register',
                oauth_scopes = NULL
            WHERE slug = 'linear'
            """
        )
    )

    # Update Sentry: use MCP OAuth endpoints (discovered from mcp.sentry.dev)
    op.execute(
        sa.text(
            """
            UPDATE mcp_connector_templates SET
                oauth_authorize_url = 'https://mcp.sentry.dev/oauth/authorize',
                oauth_token_url = 'https://mcp.sentry.dev/oauth/token',
                oauth_registration_url = 'https://mcp.sentry.dev/oauth/register',
                oauth_scopes = NULL
            WHERE slug = 'sentry'
            """
        )
    )

    # Update Slack: use MCP OAuth endpoints (no DCR but correct URLs)
    op.execute(
        sa.text(
            """
            UPDATE mcp_connector_templates SET
                oauth_authorize_url = 'https://slack.com/oauth/v2_user/authorize',
                oauth_token_url = 'https://slack.com/api/oauth.v2.user.access'
            WHERE slug = 'slack'
            """
        )
    )


def downgrade() -> None:
    # Restore original OAuth URLs
    op.execute(
        sa.text(
            """
            UPDATE mcp_connector_templates SET
                oauth_authorize_url = 'https://linear.app/oauth/authorize',
                oauth_token_url = 'https://api.linear.app/oauth/token',
                oauth_scopes = 'read write'
            WHERE slug = 'linear'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE mcp_connector_templates SET
                oauth_authorize_url = 'https://sentry.io/oauth/authorize/',
                oauth_token_url = 'https://sentry.io/oauth/token/',
                oauth_scopes = 'project:read event:read'
            WHERE slug = 'sentry'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE mcp_connector_templates SET
                oauth_authorize_url = 'https://slack.com/oauth/v2/authorize',
                oauth_token_url = 'https://slack.com/api/oauth.v2.access'
            WHERE slug = 'slack'
            """
        )
    )
    op.drop_column("mcp_connector_templates", "oauth_registration_url")
