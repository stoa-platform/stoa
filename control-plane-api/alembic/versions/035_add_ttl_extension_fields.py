"""add TTL extension tracking fields to subscriptions

Revision ID: 035
Revises: 034
Create Date: 2026-02-22

CAB-86: Self-service TTL extension endpoint.
Tracks extension count and total days extended.
"""

import sqlalchemy as sa
from alembic import op

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("ttl_extension_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "subscriptions",
        sa.Column("ttl_total_extended_days", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("subscriptions", "ttl_total_extended_days")
    op.drop_column("subscriptions", "ttl_extension_count")
