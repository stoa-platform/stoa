"""add target_gateway_url to gateway_instances

Revision ID: 082_add_target_gateway_url
Revises: 081_add_promotion_id_to_gw_deploy
Create Date: 2026-03-29

Stores the URL of the third-party gateway managed by STOA Link/Connect
instances (e.g. webMethods admin URL), displayed in Console UI.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "082_add_target_gateway_url"
down_revision: str | None = "081_add_promotion_id_to_gw_deploy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "gateway_instances",
        sa.Column("target_gateway_url", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("gateway_instances", "target_gateway_url")
