"""add promotion_id FK to gateway_deployments

Revision ID: 081_add_promotion_id_to_gw_deploy
Revises: 080_add_policy_sync_status
Create Date: 2026-03-27

Links deployments created by a promotion back to the promotion record,
enabling promotion completion tracking after all gateways report sync status.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "081_add_promotion_id_to_gw_deploy"
down_revision: str | None = "080_add_policy_sync_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "gateway_deployments",
        sa.Column(
            "promotion_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("promotions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_gw_deploy_promotion",
        "gateway_deployments",
        ["promotion_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_gw_deploy_promotion", table_name="gateway_deployments")
    op.drop_column("gateway_deployments", "promotion_id")
