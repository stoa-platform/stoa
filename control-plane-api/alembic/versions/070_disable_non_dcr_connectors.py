"""Disable non-DCR connectors from the catalog.

GitHub, Slack, and Notion don't support MCP OAuth Dynamic Client Registration.
They require manual OAuth app setup (create app on provider, paste credentials),
which is confusing next to one-click connectors like Linear and Sentry.

Disable them until they add DCR support or we pre-configure platform OAuth apps.

Revision ID: 070_disable_non_dcr_connectors
Revises: 069_oauth_session_client_secret
Create Date: 2026-03-13
"""

import sqlalchemy as sa
from alembic import op

revision = "070_disable_non_dcr_connectors"
down_revision = "069_oauth_session_client_secret"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE mcp_connector_templates
            SET enabled = false
            WHERE slug IN ('github', 'slack', 'notion')
            AND oauth_registration_url IS NULL
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE mcp_connector_templates
            SET enabled = true
            WHERE slug IN ('github', 'slack', 'notion')
            """
        )
    )
