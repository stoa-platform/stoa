"""Add tenant lifecycle management fields

Revision ID: 015
Revises: 014
Create Date: 2026-02-01

CAB-409: Tenant Lifecycle Management for demo.gostoa.dev
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Lifecycle state enum
    lifecycle_state = postgresql.ENUM(
        "active", "warning", "expired", "deleted", "converted",
        name="tenant_lifecycle_state",
        create_type=True,
    )
    lifecycle_state.create(op.get_bind(), checkfirst=True)

    # Add lifecycle columns to tenants table
    op.add_column("tenants", sa.Column(
        "lifecycle_state",
        lifecycle_state,
        server_default="active",
        nullable=False,
    ))
    op.add_column("tenants", sa.Column(
        "trial_expires_at",
        sa.DateTime(timezone=True),
        nullable=True,
        comment="When the demo trial expires (14 days after creation)",
    ))
    op.add_column("tenants", sa.Column(
        "trial_extended_count",
        sa.Integer,
        server_default="0",
        nullable=False,
        comment="Number of trial extensions used (max 1)",
    ))
    op.add_column("tenants", sa.Column(
        "lifecycle_changed_at",
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    ))
    op.add_column("tenants", sa.Column(
        "deleted_at",
        sa.DateTime(timezone=True),
        nullable=True,
    ))
    op.add_column("tenants", sa.Column(
        "converted_at",
        sa.DateTime(timezone=True),
        nullable=True,
    ))

    # Index for lifecycle cron queries
    op.create_index(
        "ix_tenants_lifecycle_state",
        "tenants",
        ["lifecycle_state"],
    )
    op.create_index(
        "ix_tenants_trial_expires_at",
        "tenants",
        ["trial_expires_at"],
        postgresql_where=sa.text("lifecycle_state NOT IN ('deleted', 'converted')"),
    )

    # Notification tracking table
    op.create_table(
        "tenant_lifecycle_notifications",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("notification_type", sa.String(50), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("channel", sa.String(20), server_default="email", nullable=False),
        sa.Column("recipient_email", sa.String(255), nullable=True),
        sa.Column("success", sa.Boolean, server_default="true", nullable=False),
        sa.Column("error_message", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_lifecycle_notif_tenant_type",
        "tenant_lifecycle_notifications",
        ["tenant_id", "notification_type"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("tenant_lifecycle_notifications")
    op.drop_index("ix_tenants_trial_expires_at", table_name="tenants")
    op.drop_index("ix_tenants_lifecycle_state", table_name="tenants")
    op.drop_column("tenants", "converted_at")
    op.drop_column("tenants", "deleted_at")
    op.drop_column("tenants", "lifecycle_changed_at")
    op.drop_column("tenants", "trial_extended_count")
    op.drop_column("tenants", "trial_expires_at")
    op.drop_column("tenants", "lifecycle_state")
    postgresql.ENUM(name="tenant_lifecycle_state").drop(op.get_bind(), checkfirst=True)
