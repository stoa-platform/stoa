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


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :table AND column_name = :col)"
        ),
        {"table": table, "col": column},
    )
    return bool(result.scalar())


def upgrade() -> None:
    if not _column_exists("subscriptions", "ttl_extension_count"):
        op.add_column(
            "subscriptions",
            sa.Column("ttl_extension_count", sa.Integer(), nullable=False, server_default="0"),
        )
    if not _column_exists("subscriptions", "ttl_total_extended_days"):
        op.add_column(
            "subscriptions",
            sa.Column("ttl_total_extended_days", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    op.drop_column("subscriptions", "ttl_total_extended_days")
    op.drop_column("subscriptions", "ttl_extension_count")
