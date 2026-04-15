"""Add REJECTED subscription status + rejected_by/rejected_at columns (CAB-1635).

Revision ID: 053_add_rejected_subscription_status
Revises: 052_mcp_connector_catalog
Create Date: 2026-03-02
"""

import sqlalchemy as sa
from alembic import op

revision = "053_add_rejected_subscription_status"
down_revision = "052_mcp_connector_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add 'rejected' value to the subscriptionstatus enum
    op.execute("COMMIT")
    op.execute("ALTER TYPE subscriptionstatus ADD VALUE IF NOT EXISTS 'rejected'")

    # Add rejected_by and rejected_at columns
    op.add_column("subscriptions", sa.Column("rejected_by", sa.String(255), nullable=True))
    op.add_column("subscriptions", sa.Column("rejected_at", sa.DateTime, nullable=True))


def downgrade() -> None:
    op.drop_column("subscriptions", "rejected_at")
    op.drop_column("subscriptions", "rejected_by")
    # Note: PostgreSQL does not support removing enum values
