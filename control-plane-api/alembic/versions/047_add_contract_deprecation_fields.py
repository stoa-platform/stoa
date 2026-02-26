"""Add contract deprecation and lifecycle management fields (CAB-1335).

Revision ID: 047_contract_deprecation
Revises: 046_llm_budget_tables
Create Date: 2026-02-26
"""

from alembic import op
import sqlalchemy as sa

revision = "047_contract_deprecation"
down_revision = "046_llm_budget_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contracts", sa.Column("deprecated_at", sa.DateTime, nullable=True))
    op.add_column("contracts", sa.Column("sunset_at", sa.DateTime, nullable=True))
    op.add_column(
        "contracts",
        sa.Column("replacement_contract_id", sa.String(36), nullable=True),
    )
    op.add_column(
        "contracts",
        sa.Column("deprecation_reason", sa.Text, nullable=True),
    )
    op.add_column(
        "contracts",
        sa.Column("grace_period_days", sa.Integer, nullable=True),
    )
    # Index for finding deprecated contracts with upcoming sunset dates
    op.create_index(
        "ix_contracts_sunset_at",
        "contracts",
        ["sunset_at"],
        postgresql_where=sa.text("sunset_at IS NOT NULL"),
    )
    # Index for finding contracts by name across versions
    op.create_index(
        "ix_contracts_name_version",
        "contracts",
        ["tenant_id", "name", "version"],
    )


def downgrade() -> None:
    op.drop_index("ix_contracts_name_version", table_name="contracts")
    op.drop_index("ix_contracts_sunset_at", table_name="contracts")
    op.drop_column("contracts", "grace_period_days")
    op.drop_column("contracts", "deprecation_reason")
    op.drop_column("contracts", "replacement_contract_id")
    op.drop_column("contracts", "sunset_at")
    op.drop_column("contracts", "deprecated_at")
