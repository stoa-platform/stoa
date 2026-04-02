"""Add sync_steps JSONB column to gateway_deployments (CAB-1945)

Stores an ordered list of sync step records for deployment pipeline
observability. Each step has: name, status, started_at, completed_at, detail.

Revision ID: 086
Revises: 085
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "086"
down_revision = "085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("gateway_deployments", sa.Column("sync_steps", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("gateway_deployments", "sync_steps")
