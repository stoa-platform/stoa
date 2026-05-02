"""gateway-aware promotions

Revision ID: 106_gateway_aware_promotions
Revises: 105_fix_webmethods_staging_target_urls
Create Date: 2026-05-02

Promotion requests now carry explicit target gateway IDs. The column stays
nullable so historical promotion rows remain readable.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "106_gateway_aware_promotions"
down_revision: str | tuple[str, ...] | None = "105_fix_webmethods_staging_target_urls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "promotions",
        sa.Column("target_gateway_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("promotions", "target_gateway_ids")
