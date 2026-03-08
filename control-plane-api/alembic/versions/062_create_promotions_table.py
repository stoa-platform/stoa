"""Create promotions table for GitOps promotion flow (CAB-1706)

Revision ID: 062
Revises: 061
Create Date: 2026-03-08
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "062"
down_revision = "061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "promotions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False, index=True),
        sa.Column("api_id", sa.String(255), nullable=False),
        sa.Column("source_environment", sa.String(50), nullable=False),
        sa.Column("target_environment", sa.String(50), nullable=False),
        sa.Column("source_deployment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_deployment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("spec_diff", postgresql.JSONB(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.String(255), nullable=False),
        sa.Column("approved_by", sa.String(255), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Composite indexes for query performance
    op.create_index(
        "ix_promotions_tenant_api", "promotions", ["tenant_id", "api_id"]
    )
    op.create_index(
        "ix_promotions_api_target_status",
        "promotions",
        ["api_id", "target_environment", "status"],
    )

    # Partial unique index: prevent concurrent promotions to same target
    op.execute(
        "CREATE UNIQUE INDEX uq_promotions_active_per_target "
        "ON promotions (api_id, target_environment) "
        "WHERE status IN ('pending', 'promoting')"
    )


def downgrade() -> None:
    op.drop_index("uq_promotions_active_per_target", table_name="promotions")
    op.drop_index("ix_promotions_api_target_status", table_name="promotions")
    op.drop_index("ix_promotions_tenant_api", table_name="promotions")
    op.drop_table("promotions")
