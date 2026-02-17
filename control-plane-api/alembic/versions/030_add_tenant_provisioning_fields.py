"""Add tenant provisioning fields

Revision ID: 030
Revises: 029
Create Date: 2026-02-17
"""

from alembic import op
import sqlalchemy as sa

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("provisioning_status", sa.String(32), server_default="pending", nullable=False))
    op.add_column("tenants", sa.Column("provisioning_error", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("provisioning_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tenants", sa.Column("kc_group_id", sa.String(255), nullable=True))
    op.add_column("tenants", sa.Column("provisioning_attempts", sa.Integer(), server_default="0", nullable=False))
    op.create_index("ix_tenants_provisioning_status", "tenants", ["provisioning_status"])


def downgrade() -> None:
    op.drop_index("ix_tenants_provisioning_status", table_name="tenants")
    op.drop_column("tenants", "provisioning_attempts")
    op.drop_column("tenants", "kc_group_id")
    op.drop_column("tenants", "provisioning_started_at")
    op.drop_column("tenants", "provisioning_error")
    op.drop_column("tenants", "provisioning_status")
