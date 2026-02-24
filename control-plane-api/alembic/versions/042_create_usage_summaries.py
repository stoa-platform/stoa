"""Create usage_summaries table for metering pipeline (CAB-1334).

Revision ID: 042_usage_summaries
Revises: 041_mcp_generated_tools
Create Date: 2026-02-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "042_usage_summaries"
down_revision = "041_mcp_generated_tools"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create the enum type first
    usage_period_enum = sa.Enum("daily", "monthly", name="usage_period_enum", create_type=True)
    usage_period_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "usage_summaries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("api_id", UUID(as_uuid=True), nullable=False),
        sa.Column("consumer_id", UUID(as_uuid=True), nullable=True),
        sa.Column("period", usage_period_enum, nullable=False),
        sa.Column("period_start", sa.DateTime, nullable=False),
        sa.Column("request_count", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("error_count", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("total_latency_ms", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("p99_latency_ms", sa.Integer, nullable=True),
        sa.Column("total_tokens", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # Composite index for common tenant+api+period queries
    op.create_index(
        "ix_usage_summaries_tenant_api_period",
        "usage_summaries",
        ["tenant_id", "api_id", "period", "period_start"],
    )
    op.create_index("ix_usage_summaries_tenant_id", "usage_summaries", ["tenant_id"])
    op.create_index("ix_usage_summaries_api_id", "usage_summaries", ["api_id"])
    op.create_index("ix_usage_summaries_period_start", "usage_summaries", ["period_start"])


def downgrade() -> None:
    op.drop_index("ix_usage_summaries_period_start")
    op.drop_index("ix_usage_summaries_api_id")
    op.drop_index("ix_usage_summaries_tenant_id")
    op.drop_index("ix_usage_summaries_tenant_api_period")
    op.drop_table("usage_summaries")

    # Drop the enum type
    sa.Enum(name="usage_period_enum").drop(op.get_bind(), checkfirst=True)
