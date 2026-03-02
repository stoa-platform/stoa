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
    # Create tenants table if it doesn't exist (previously managed via GitOps only)
    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT to_regclass('public.tenants')"))
    if result.scalar() is None:
        op.create_table(
            "tenants",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("status", sa.String(32), server_default="active", nullable=False),
            sa.Column("settings", sa.JSON(), server_default="{}", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

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
