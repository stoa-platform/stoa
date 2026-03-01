"""Create deployment_logs table (CAB-1420)

Revision ID: 036_deployment_logs
Revises: 035_add_ttl_extension_fields
Create Date: 2026-02-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "036_deployment_logs"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deployment_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("deployment_id", UUID(as_uuid=True), sa.ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("level", sa.String(10), nullable=False, server_default="info"),
        sa.Column("step", sa.String(100), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_deployment_logs_deployment_id", "deployment_logs", ["deployment_id"])
    op.create_index("ix_deployment_logs_tenant_id", "deployment_logs", ["tenant_id"])
    op.create_index("ix_deployment_logs_deploy_seq", "deployment_logs", ["deployment_id", "seq"])


def downgrade() -> None:
    op.drop_index("ix_deployment_logs_deploy_seq", table_name="deployment_logs")
    op.drop_index("ix_deployment_logs_tenant_id", table_name="deployment_logs")
    op.drop_index("ix_deployment_logs_deployment_id", table_name="deployment_logs")
    op.drop_table("deployment_logs")
