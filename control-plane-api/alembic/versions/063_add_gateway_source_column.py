"""Add source column to gateway_instances for reconciliation tracking

Revision ID: 063
Revises: 062
Create Date: 2026-03-11
"""

import sqlalchemy as sa
from alembic import op

revision = "063"
down_revision = "062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gateway_instances",
        sa.Column(
            "source",
            sa.String(50),
            nullable=False,
            server_default="self_register",
        ),
    )
    op.create_index("ix_gw_instances_source", "gateway_instances", ["source"])


def downgrade() -> None:
    op.drop_index("ix_gw_instances_source", table_name="gateway_instances")
    op.drop_column("gateway_instances", "source")
