"""Add session_fingerprint and last_active_at to chat_conversations (CAB-1653).

Revision ID: 054_chat_session_binding
Revises: 053_add_rejected_subscription_status
Create Date: 2026-03-04
"""

import sqlalchemy as sa
from alembic import op

revision = "054_chat_session_binding"
down_revision = "053_add_rejected_subscription_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_conversations", sa.Column("session_fingerprint", sa.String(64), nullable=True))
    op.add_column(
        "chat_conversations",
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chat_conversations", "last_active_at")
    op.drop_column("chat_conversations", "session_fingerprint")
