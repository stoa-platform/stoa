"""Add llm_spend_events audit table (CAB-1487).

Per-request LLM spend tracking with provider/model metadata for analytics,
anomaly detection, and cost dashboard.

Revision ID: 050_llm_spend_events
Revises: 049_cache_token_columns
Create Date: 2026-03-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "050_llm_spend_events"
down_revision = "049_cache_token_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_spend_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("provider_name", sa.String(100), nullable=False),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("latency_seconds", sa.Numeric(8, 4), nullable=True),
        sa.Column("cached", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_llm_spend_events_tenant_id",
        "llm_spend_events",
        ["tenant_id"],
    )
    op.create_index(
        "ix_llm_spend_events_created_at",
        "llm_spend_events",
        ["created_at"],
    )
    op.create_index(
        "ix_llm_spend_events_tenant_created",
        "llm_spend_events",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_llm_spend_events_tenant_created", table_name="llm_spend_events")
    op.drop_index("ix_llm_spend_events_created_at", table_name="llm_spend_events")
    op.drop_index("ix_llm_spend_events_tenant_id", table_name="llm_spend_events")
    op.drop_table("llm_spend_events")
