"""Create audit_events table for compliance-grade audit trail (CAB-1475).

Revision ID: 044_audit_events
Revises: 043_department_budgets
Create Date: 2026-02-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "044_audit_events"
down_revision = "043_department_budgets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        # Actor
        sa.Column("actor_id", sa.String(255), nullable=True),
        sa.Column("actor_email", sa.String(255), nullable=True),
        sa.Column("actor_type", sa.String(50), nullable=False, server_default="user"),
        # Action
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("path", sa.String(1024), nullable=False),
        # Resource
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("resource_name", sa.String(255), nullable=True),
        # Outcome
        sa.Column("outcome", sa.String(20), nullable=False, server_default="success"),
        sa.Column("status_code", sa.Integer, nullable=True),
        # Context
        sa.Column("client_ip", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("correlation_id", sa.String(36), nullable=True),
        # Payload
        sa.Column("details", JSONB, nullable=True),
        sa.Column("diff", JSONB, nullable=True),
        # Duration
        sa.Column("duration_ms", sa.Integer, nullable=True),
        # Timestamp
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Indexes
    op.create_index("idx_audit_tenant_created", "audit_events", ["tenant_id", "created_at"])
    op.create_index("idx_audit_actor_created", "audit_events", ["actor_id", "created_at"])
    op.create_index("idx_audit_action", "audit_events", ["action"])
    op.create_index("idx_audit_resource_type", "audit_events", ["resource_type", "resource_id"])
    op.create_index("idx_audit_outcome", "audit_events", ["outcome"])
    op.create_index("idx_audit_correlation", "audit_events", ["correlation_id"])


def downgrade() -> None:
    op.drop_index("idx_audit_correlation")
    op.drop_index("idx_audit_outcome")
    op.drop_index("idx_audit_resource_type")
    op.drop_index("idx_audit_action")
    op.drop_index("idx_audit_actor_created")
    op.drop_index("idx_audit_tenant_created")
    op.drop_table("audit_events")
