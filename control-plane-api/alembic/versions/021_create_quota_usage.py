"""create quota_usage table

Revision ID: 021
Revises: 020
Create Date: 2026-02-09

CAB-1121 Phase 4: Quota Enforcement — daily/monthly request tracking
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "021"
down_revision: str | None = "020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create quota_usage table with indexes."""
    op.create_table(
        "quota_usage",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "consumer_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("consumers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subscription_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscriptions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("request_count_daily", sa.Integer, nullable=False, server_default="0"),
        sa.Column("request_count_monthly", sa.Integer, nullable=False, server_default="0"),
        sa.Column("bandwidth_bytes_daily", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("bandwidth_bytes_monthly", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("period_start_daily", sa.Date, nullable=False),
        sa.Column("period_start_monthly", sa.Date, nullable=False),
        sa.Column("last_reset_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_index(
        "ix_quota_usage_consumer_tenant_daily",
        "quota_usage",
        ["consumer_id", "tenant_id", "period_start_daily"],
        unique=True,
    )
    op.create_index("ix_quota_usage_tenant", "quota_usage", ["tenant_id"])


def downgrade() -> None:
    """Drop quota_usage table."""
    op.drop_index("ix_quota_usage_tenant", table_name="quota_usage")
    op.drop_index("ix_quota_usage_consumer_tenant_daily", table_name="quota_usage")
    op.drop_table("quota_usage")
