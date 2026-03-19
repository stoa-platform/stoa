"""Create api_gateway_assignments table (CAB-1888).

Default gateway targets per API/environment for auto-deploy on promotion.

Revision ID: 077_create_api_gateway_assignments
Revises: 076_add_environment_to_usage_summaries
Create Date: 2026-03-19
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "077_create_api_gateway_assignments"
down_revision = "076_add_environment_to_usage_summaries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_gateway_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "api_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("api_catalog.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "gateway_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gateway_instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("environment", sa.String(50), nullable=False),
        sa.Column("auto_deploy", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("api_id", "gateway_id", "environment", name="uq_api_gateway_env"),
    )
    op.create_index("ix_api_gw_assign_api_env", "api_gateway_assignments", ["api_id", "environment"])
    op.create_index("ix_api_gw_assign_gateway", "api_gateway_assignments", ["gateway_id"])


def downgrade() -> None:
    op.drop_index("ix_api_gw_assign_gateway", table_name="api_gateway_assignments")
    op.drop_index("ix_api_gw_assign_api_env", table_name="api_gateway_assignments")
    op.drop_table("api_gateway_assignments")
