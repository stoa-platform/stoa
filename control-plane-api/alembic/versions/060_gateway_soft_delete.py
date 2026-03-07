"""add soft-delete and protection columns to gateway_instances

Revision ID: 060
Revises: 059
Create Date: 2026-03-07

CAB-1749: Gateway instance resilience — soft-delete, protection, audit trail.
Adds deleted_at, deleted_by, protected columns. Marks production gateways as protected.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "060"
down_revision: str | None = "059"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PROD_GATEWAY_NAMES = ["stoa-prod", "webmethods-prod", "kong-prod"]


def upgrade() -> None:
    op.add_column(
        "gateway_instances",
        sa.Column("protected", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "gateway_instances",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "gateway_instances",
        sa.Column("deleted_by", sa.String(255), nullable=True),
    )

    # Mark production gateways as protected
    conn = op.get_bind()
    for name in PROD_GATEWAY_NAMES:
        conn.execute(
            sa.text("UPDATE gateway_instances SET protected = true WHERE name = :name"),
            {"name": name},
        )


def downgrade() -> None:
    op.drop_column("gateway_instances", "deleted_by")
    op.drop_column("gateway_instances", "deleted_at")
    op.drop_column("gateway_instances", "protected")
