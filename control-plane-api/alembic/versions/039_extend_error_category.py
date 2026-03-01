"""Extend errorcategory enum with diagnostic categories (CAB-1316).

Revision ID: 039b
Revises: 038
Create Date: 2026-02-23

Adds: network, certificate, policy, circuit_breaker to errorcategory enum.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "039b"
down_revision: str | None = "039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE errorcategory ADD VALUE IF NOT EXISTS 'network'")
    op.execute("ALTER TYPE errorcategory ADD VALUE IF NOT EXISTS 'certificate'")
    op.execute("ALTER TYPE errorcategory ADD VALUE IF NOT EXISTS 'policy'")
    op.execute("ALTER TYPE errorcategory ADD VALUE IF NOT EXISTS 'circuit_breaker'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values.
    # These values are additive and safe to leave in place.
    pass
