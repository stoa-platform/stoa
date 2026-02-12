"""Create access_requests table for email capture.

Revision ID: 023
Revises: 022
Create Date: 2026-02-11

Captures email + company from unauthenticated portal visitors
who want early access to the STOA Developer Portal.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "023"
down_revision: str | None = "022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create access_requests table."""
    op.create_table(
        "access_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_access_requests_email"),
    )
    op.create_index("ix_access_requests_created_at", "access_requests", ["created_at"])


def downgrade() -> None:
    """Drop access_requests table."""
    op.drop_index("ix_access_requests_created_at", "access_requests")
    op.drop_table("access_requests")
