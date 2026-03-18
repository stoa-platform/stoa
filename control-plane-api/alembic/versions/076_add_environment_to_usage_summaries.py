"""Add environment column to usage_summaries (CAB-1665).

Revision ID: 076_add_environment_to_usage_summaries
Revises: 075_seed_traffic_seeder_apis
Create Date: 2026-03-18
"""

import sqlalchemy as sa
from alembic import op

revision = "076_add_environment_to_usage_summaries"
down_revision = "075_seed_traffic_seeder_apis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("usage_summaries", sa.Column("environment", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("usage_summaries", "environment")
