"""Add deployments table

Revision ID: 026
Revises: 025
Create Date: 2026-02-16
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deployments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("api_id", sa.String(255), nullable=False),
        sa.Column("api_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("environment", sa.String(50), nullable=False),
        sa.Column("version", sa.String(100), nullable=False, server_default="1.0.0"),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("deployed_by", sa.String(255), nullable=False),
        sa.Column("gateway_id", sa.String(255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("spec_hash", sa.String(64), nullable=True),
        sa.Column("commit_sha", sa.String(40), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rollback_of", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rollback_version", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_deployments_tenant_id", "deployments", ["tenant_id"])
    op.create_index("ix_deployments_tenant_api", "deployments", ["tenant_id", "api_id"])
    op.create_index("ix_deployments_tenant_env", "deployments", ["tenant_id", "environment"])
    op.create_index("ix_deployments_tenant_status", "deployments", ["tenant_id", "status"])
    op.create_index("ix_deployments_tenant_created", "deployments", ["tenant_id", "created_at"])

    # Extend webhook event type enum with deployment events.
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block,
    # so we commit the current transaction and start a new one.
    op.execute("COMMIT")
    op.execute("ALTER TYPE webhookeventtype ADD VALUE IF NOT EXISTS 'deployment.started'")
    op.execute("ALTER TYPE webhookeventtype ADD VALUE IF NOT EXISTS 'deployment.succeeded'")
    op.execute("ALTER TYPE webhookeventtype ADD VALUE IF NOT EXISTS 'deployment.failed'")
    op.execute("ALTER TYPE webhookeventtype ADD VALUE IF NOT EXISTS 'deployment.rolled_back'")
    op.execute("BEGIN")


def downgrade() -> None:
    op.drop_index("ix_deployments_tenant_created", table_name="deployments")
    op.drop_index("ix_deployments_tenant_status", table_name="deployments")
    op.drop_index("ix_deployments_tenant_env", table_name="deployments")
    op.drop_index("ix_deployments_tenant_api", table_name="deployments")
    op.drop_index("ix_deployments_tenant_id", table_name="deployments")
    op.drop_table("deployments")
    # Note: PostgreSQL does not support removing values from enums.
    # The deployment.* values will remain in webhookeventtype after downgrade.
