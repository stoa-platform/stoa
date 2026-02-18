"""add onboarding_progress table

Revision ID: 033
Revises: 032
Create Date: 2026-02-19

CAB-1325: Zero-touch trial onboarding progress tracking.
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
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False, index=True),
        sa.Column("user_id", sa.String(255), nullable=False, index=True),
        sa.Column("steps_completed", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("ttftc_seconds", sa.Integer(), nullable=True),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_onboarding_tenant_user"),
    )


def downgrade() -> None:
    op.drop_table("onboarding_progress")
