"""Add status column to chat_conversations.

Revision ID: 040
Revises: 039
"""

import sqlalchemy as sa
from alembic import op

revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_conversations",
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
    )
    op.create_index(
        "ix_chat_conversations_tenant_status",
        "chat_conversations",
        ["tenant_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_conversations_tenant_status", table_name="chat_conversations")
    op.drop_column("chat_conversations", "status")
