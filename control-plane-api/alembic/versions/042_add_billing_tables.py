"""042 — Create billing_ledger and department_budgets tables (CAB-1457).

Revision ID: 042_add_billing_tables
Revises: 041_mcp_generated_tools
Create Date: 2026-02-24
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "042_add_billing_tables"
down_revision = "041_mcp_generated_tools"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- billing_ledger --
    op.create_table(
        "billing_ledger",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("department_id", sa.String(100), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tool_name", sa.String(255), nullable=False),
        sa.Column("period_month", sa.String(7), nullable=False),
        sa.Column("tool_calls", sa.Integer(), server_default="0", nullable=False),
        sa.Column("token_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("cost_microcents", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "department_id",
            "tool_name",
            "period_month",
            name="uq_billing_ledger_dept_tool_month",
        ),
    )
    op.create_index(
        "ix_billing_ledger_dept_month",
        "billing_ledger",
        ["department_id", "period_month"],
    )

    # -- department_budgets --
    op.create_table(
        "department_budgets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("department_id", sa.String(100), nullable=False),
        sa.Column("monthly_budget_usd", sa.Numeric(10, 2), nullable=False),
        sa.Column("alert_webhook_url", sa.Text(), nullable=True),
        sa.Column(
            "alert_thresholds",
            postgresql.JSON(),
            server_default='{"50": false, "80": true, "100": true}',
            nullable=False,
        ),
        sa.Column(
            "alerts_fired_this_month",
            postgresql.JSON(),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("period_month", sa.String(7), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "department_id",
            name="uq_department_budgets_tenant_dept",
        ),
    )


def downgrade() -> None:
    op.drop_table("department_budgets")
    op.drop_index("ix_billing_ledger_dept_month", table_name="billing_ledger")
    op.drop_table("billing_ledger")
