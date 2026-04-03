"""Add ui_url column to gateway_instances (CAB-1953)

Stores the web UI URL of third-party gateways managed by Link/Connect
instances (e.g. webMethods admin console at port 9072).

Revision ID: 088
Revises: 087
"""

import sqlalchemy as sa
from alembic import op

revision = "088"
down_revision = "087"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gateway_instances",
        sa.Column("ui_url", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("gateway_instances", "ui_url")
