"""Add environment column to consumers, portal_applications, subscriptions (CAB-1665).

Revision ID: 055_add_environment_column
Revises: 054_chat_session_binding
Create Date: 2026-03-04
"""

import sqlalchemy as sa
from alembic import op

revision = "055_add_environment_column"
down_revision = "054_chat_session_binding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("consumers", sa.Column("environment", sa.String(50), nullable=True))
    op.add_column("portal_applications", sa.Column("environment", sa.String(50), nullable=True))
    op.add_column("subscriptions", sa.Column("environment", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("subscriptions", "environment")
    op.drop_column("portal_applications", "environment")
    op.drop_column("consumers", "environment")
