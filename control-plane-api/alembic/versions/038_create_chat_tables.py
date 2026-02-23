"""Create chat_conversations and chat_messages tables (CAB-286).

Revision ID: 038
Revises: 037
Create Date: 2026-02-23

Adds tables for the Chat Agent backend: conversations + messages
with cascade delete, composite indexes, and a chat_message_role enum.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "038"
down_revision: str | None = "037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("title", sa.String(500), nullable=False, server_default="New conversation"),
        sa.Column("provider", sa.String(50), nullable=False, server_default="anthropic"),
        sa.Column("model", sa.String(100), nullable=False, server_default="claude-sonnet-4-20250514"),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_index("ix_chat_conversations_tenant_id", "chat_conversations", ["tenant_id"])
    op.create_index("ix_chat_conversations_user_id", "chat_conversations", ["user_id"])
    op.create_index("ix_chat_conversations_tenant_user", "chat_conversations", ["tenant_id", "user_id"])
    op.create_index("ix_chat_conversations_updated", "chat_conversations", ["updated_at"])

    # Create the enum type for message roles
    chat_role = postgresql.ENUM("user", "assistant", "system", name="chat_message_role", create_type=False)
    chat_role.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chat_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role",
            postgresql.ENUM("user", "assistant", "system", name="chat_message_role", create_type=False),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.String(50), nullable=True),
        sa.Column("tool_use", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_index("ix_chat_messages_conversation", "chat_messages", ["conversation_id"])
    op.create_index("ix_chat_messages_created", "chat_messages", ["created_at"])


def downgrade() -> None:
    op.drop_table("chat_messages")
    op.drop_table("chat_conversations")
    op.execute("DROP TYPE IF EXISTS chat_message_role")
