"""add gravitee to gateway_type_enum

Revision ID: 022
Revises: 021
Create Date: 2026-02-11

Adds the 'gravitee' value to the existing gateway_type_enum
for multi-gateway orchestration (Kong already present from migration 013).
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "022"
down_revision: str | None = "021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add gravitee to gateway_type_enum."""
    op.execute("ALTER TYPE gateway_type_enum ADD VALUE IF NOT EXISTS 'gravitee'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values
    pass
