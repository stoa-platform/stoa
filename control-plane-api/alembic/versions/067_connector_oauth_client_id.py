"""Add oauth_client_id to mcp_connector_templates.

Store OAuth client_id directly in the template row so the authorize flow
works without a manual Vault seed step.  For PKCE-only providers (e.g. Linear)
this is all that's needed; for confidential clients the client_secret comes
from an env var (MCP_OAUTH_{SLUG}_SECRET) injected via Infisical → K8s Secret.

Revision ID: 067_connector_oauth_client_id
Revises: 066_reset_offline_external_gateways
Create Date: 2026-03-13
"""

import sqlalchemy as sa
from alembic import op

revision = "067_connector_oauth_client_id"
down_revision = "066_reset_offline_external_gateways"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mcp_connector_templates",
        sa.Column("oauth_client_id", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("mcp_connector_templates", "oauth_client_id")
