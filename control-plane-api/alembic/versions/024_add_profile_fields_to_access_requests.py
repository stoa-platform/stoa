"""Add profile fields to access_requests.

Revision ID: 024
Revises: 023
Create Date: 2026-02-12

Adds first_name, last_name, role to better qualify leads.
Role allows freelancers/students to self-identify without company.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "024"
down_revision: str | None = "023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add first_name, last_name, role columns."""
    op.add_column("access_requests", sa.Column("first_name", sa.String(100), nullable=True))
    op.add_column("access_requests", sa.Column("last_name", sa.String(100), nullable=True))
    op.add_column("access_requests", sa.Column("role", sa.String(50), nullable=True))


def downgrade() -> None:
    """Remove profile columns."""
    op.drop_column("access_requests", "role")
    op.drop_column("access_requests", "last_name")
    op.drop_column("access_requests", "first_name")
