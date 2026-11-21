"""Create invites table.

Revision ID: 001
Revises:
Create Date: 2026-01-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create schema if not exists
    op.execute("CREATE SCHEMA IF NOT EXISTS stoa")

    # Create invites table
    op.create_table(
        "invites",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("company", sa.String(length=100), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invites")),
        sa.UniqueConstraint("token", name=op.f("uq_invites_token")),
        schema="stoa",
    )

    # Create indexes
    op.create_index(op.f("ix_invites_token"), "invites", ["token"], schema="stoa")
    op.create_index("idx_invites_email", "invites", ["email"], schema="stoa")
    op.create_index("idx_invites_status", "invites", ["status"], schema="stoa")


def downgrade() -> None:
    op.drop_index("idx_invites_status", table_name="invites", schema="stoa")
    op.drop_index("idx_invites_email", table_name="invites", schema="stoa")
    op.drop_index(op.f("ix_invites_token"), table_name="invites", schema="stoa")
    op.drop_table("invites", schema="stoa")
