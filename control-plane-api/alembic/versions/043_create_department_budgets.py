"""Create department_budgets table for chargeback and budget enforcement (CAB-1457).

Revision ID: 043_department_budgets
Revises: 042_usage_summaries
Create Date: 2026-02-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "043_department_budgets"
down_revision = "042_usage_summaries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enforcement enum
    enforcement_enum = sa.Enum(
        "enabled", "disabled", "warn_only",
        name="budget_enforcement_enum",
        create_type=True,
    )
    enforcement_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "department_budgets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("department_id", sa.String(255), nullable=False),
        sa.Column("department_name", sa.String(255), nullable=True),
        sa.Column("period", sa.String(20), nullable=False, server_default="monthly"),
        sa.Column("budget_limit_microcents", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("current_spend_microcents", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("period_start", sa.DateTime, nullable=False),
        sa.Column("warning_threshold_pct", sa.BigInteger, nullable=False, server_default="80"),
        sa.Column("critical_threshold_pct", sa.BigInteger, nullable=False, server_default="95"),
        sa.Column("enforcement", enforcement_enum, nullable=False, server_default="disabled"),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # Indexes
    op.create_index("ix_dept_budgets_tenant_dept", "department_budgets", ["tenant_id", "department_id"])
    op.create_index("ix_dept_budgets_tenant_id", "department_budgets", ["tenant_id"])
    op.create_index("ix_dept_budgets_dept_id", "department_budgets", ["department_id"])
    op.create_index("ix_dept_budgets_period_start", "department_budgets", ["period_start"])


def downgrade() -> None:
    op.drop_index("ix_dept_budgets_period_start")
    op.drop_index("ix_dept_budgets_dept_id")
    op.drop_index("ix_dept_budgets_tenant_id")
    op.drop_index("ix_dept_budgets_tenant_dept")
    op.drop_table("department_budgets")

    sa.Enum(name="budget_enforcement_enum").drop(op.get_bind(), checkfirst=True)
