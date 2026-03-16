"""Add source column to chat tables + tenant chat settings (CAB-1851).

Revision ID: 073_chat_source
Revises: 072_unique_connector_per_env
Create Date: 2026-03-16
"""

from alembic import op
import sqlalchemy as sa

revision = "073_chat_source"
down_revision = "072_unique_connector_per_env"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add source column to chat_messages (nullable, default 'console')
    op.add_column(
        "chat_messages",
        sa.Column("source", sa.String(20), nullable=True, server_default="console"),
    )

    # Add source column to chat_token_usage (nullable, default 'console')
    op.add_column(
        "chat_token_usage",
        sa.Column("source", sa.String(20), nullable=True, server_default="console"),
    )

    # Index for per-source usage queries
    op.create_index(
        "ix_chat_token_usage_tenant_source",
        "chat_token_usage",
        ["tenant_id", "source"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_token_usage_tenant_source", table_name="chat_token_usage")
    op.drop_column("chat_token_usage", "source")
    op.drop_column("chat_messages", "source")
