"""Add ttl_extensions column to mcp_server_subscriptions (CAB-86)

Revision ID: 031
Revises: 030
Create Date: 2026-02-18
"""

import sqlalchemy as sa
from alembic import op

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mcp_server_subscriptions",
        sa.Column("ttl_extensions", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("mcp_server_subscriptions", "ttl_extensions")
