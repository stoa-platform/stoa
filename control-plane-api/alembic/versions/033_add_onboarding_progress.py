"""Add onboarding_progress table (CAB-1325).

Revision ID: 033
Revises: 032
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "onboarding_progress",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("steps_completed", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("ttftc_seconds", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_onboarding_progress_tenant_id", "onboarding_progress", ["tenant_id"])
    op.create_index("ix_onboarding_progress_user_id", "onboarding_progress", ["user_id"])
    op.create_unique_constraint(
        "uq_onboarding_tenant_user",
        "onboarding_progress",
        ["tenant_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_onboarding_tenant_user", "onboarding_progress", type_="unique")
    op.drop_index("ix_onboarding_progress_user_id", table_name="onboarding_progress")
    op.drop_index("ix_onboarding_progress_tenant_id", table_name="onboarding_progress")
    op.drop_table("onboarding_progress")
