"""add policy_sync_status and policy_sync_error to gateway_deployments

Revision ID: 080_add_policy_sync_status
Revises: 079_update_gateway_dns_urls
Create Date: 2026-03-26

Tracks policy synchronization independently from API sync.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "080_add_policy_sync_status"
down_revision: str | None = "079_update_gateway_dns_urls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

policy_sync_status_enum = sa.Enum(
    "pending",
    "synced",
    "partial",
    "error",
    name="policy_sync_status_enum",
)


def upgrade() -> None:
    policy_sync_status_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "gateway_deployments",
        sa.Column("policy_sync_status", policy_sync_status_enum, nullable=True),
    )
    op.add_column(
        "gateway_deployments",
        sa.Column("policy_sync_error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("gateway_deployments", "policy_sync_error")
    op.drop_column("gateway_deployments", "policy_sync_status")
    policy_sync_status_enum.drop(op.get_bind(), checkfirst=True)
