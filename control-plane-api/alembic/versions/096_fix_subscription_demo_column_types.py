"""Fix subscription column types used by demo API key smoke.

Revision ID: 096_fix_subscription_demo_column_types
Revises: 095_merge_heads
Create Date: 2026-04-25

The SQLAlchemy model stores 12-character API key prefixes, but the original
subscriptions migration created api_key_prefix as VARCHAR(10). Fresh demo DBs
therefore reject the one-time key returned by the demo smoke subscription path.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "096_fix_subscription_demo_column_types"
down_revision: str | tuple[str, ...] | None = "095_merge_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "subscriptions",
        "api_key_prefix",
        existing_type=sa.String(10),
        type_=sa.String(20),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "subscriptions",
        "api_key_prefix",
        existing_type=sa.String(20),
        type_=sa.String(10),
        existing_nullable=True,
    )
