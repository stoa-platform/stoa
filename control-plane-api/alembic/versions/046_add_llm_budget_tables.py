"""Create llm_providers and llm_budgets tables (CAB-1491).

Revision ID: 046_llm_budget_tables
Revises: 045
Create Date: 2026-02-26
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "046_llm_budget_tables"
down_revision = "045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_providers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("provider_name", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("default_model", sa.String(100), nullable=True),
        sa.Column("cost_per_input_token", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("cost_per_output_token", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column(
            "status",
            sa.Enum("active", "inactive", "rate_limited", name="llm_provider_status_enum", create_type=True),
            nullable=False,
            server_default="active",
        ),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_llm_providers_tenant_id", "llm_providers", ["tenant_id"])
    op.create_index(
        "ix_llm_providers_tenant_provider",
        "llm_providers",
        ["tenant_id", "provider_name"],
        unique=True,
    )

    op.create_table(
        "llm_budgets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False, unique=True),
        sa.Column("monthly_limit_usd", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("current_spend_usd", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("alert_threshold_pct", sa.Integer, nullable=False, server_default="80"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_llm_budgets_tenant_id", "llm_budgets", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_llm_budgets_tenant_id", table_name="llm_budgets")
    op.drop_table("llm_budgets")
    op.drop_index("ix_llm_providers_tenant_provider", table_name="llm_providers")
    op.drop_index("ix_llm_providers_tenant_id", table_name="llm_providers")
    op.drop_table("llm_providers")
    op.execute("DROP TYPE IF EXISTS llm_provider_status_enum")
