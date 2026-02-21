"""create execution_logs table

Revision ID: 034
Revises: 033
Create Date: 2026-02-19

CAB-1318: Consumer execution view with error taxonomy.
"""

import sqlalchemy as sa
from alembic import op

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enums
    executionstatus = sa.Enum("success", "error", "timeout", name="executionstatus")
    errorcategory = sa.Enum(
        "auth", "rate_limit", "backend", "timeout", "validation", name="errorcategory"
    )
    executionstatus.create(op.get_bind(), checkfirst=True)
    errorcategory.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "execution_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("consumer_id", sa.String(36), nullable=True),
        sa.Column("api_id", sa.String(255), nullable=True),
        sa.Column("api_name", sa.String(255), nullable=True),
        sa.Column("tool_name", sa.String(255), nullable=True),
        sa.Column("request_id", sa.String(255), nullable=False, unique=True),
        sa.Column("method", sa.String(10), nullable=True),
        sa.Column("path", sa.String(1024), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("status", executionstatus, nullable=False),
        sa.Column("error_category", errorcategory, nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("request_headers", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("response_summary", sa.dialects.postgresql.JSONB(), nullable=True),
    )

    op.create_index("idx_exec_tenant_started", "execution_logs", ["tenant_id", "started_at"])
    op.create_index("idx_exec_consumer_started", "execution_logs", ["consumer_id", "started_at"])
    op.create_index("idx_exec_error_category", "execution_logs", ["error_category", "started_at"])
    op.create_index("idx_exec_status", "execution_logs", ["status"])
    op.create_index("idx_exec_request_id", "execution_logs", ["request_id"])


def downgrade() -> None:
    op.drop_table("execution_logs")
    op.execute("DROP TYPE IF EXISTS executionstatus")
    op.execute("DROP TYPE IF EXISTS errorcategory")
