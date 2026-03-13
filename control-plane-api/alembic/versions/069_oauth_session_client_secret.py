"""Add client_secret to OAuthPendingSession for non-DCR connectors.

Non-DCR connectors (GitHub, Slack, Notion) receive client_secret from the
UI setup dialog during the authorize step. This secret must be available
during the callback step (a separate HTTP request). Previously it was only
stored in Vault, which fails silently if Vault is unavailable.

Storing client_secret in the ephemeral pending session (10min TTL, single-use,
deleted immediately after callback) provides a reliable fallback.

Revision ID: 069_oauth_session_client_secret
Revises: 068_mcp_oauth_dcr_support
Create Date: 2026-03-13
"""

import sqlalchemy as sa
from alembic import op

revision = "069_oauth_session_client_secret"
down_revision = "068_mcp_oauth_dcr_support"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "oauth_pending_sessions",
        sa.Column("client_secret", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("oauth_pending_sessions", "client_secret")
