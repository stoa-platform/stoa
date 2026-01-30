"""add gateway provisioning columns for webMethods auto-provisioning (CAB-800)

Revision ID: 012
Revises: 011
Create Date: 2026-01-30

Adds columns to support gateway auto-provisioning on subscription approval:
- provisioning_status: Current provisioning state (none/pending/provisioning/ready/failed/...)
- gateway_app_id: Application ID in the external gateway (webMethods)
- provisioning_error: Last error message if provisioning failed
- provisioned_at: When the gateway route was successfully created
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '012'
down_revision: Union[str, None] = '011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'subscriptions',
        sa.Column('provisioning_status', sa.String(20), nullable=False, server_default='none')
    )
    op.add_column(
        'subscriptions',
        sa.Column('gateway_app_id', sa.String(255), nullable=True)
    )
    op.add_column(
        'subscriptions',
        sa.Column('provisioning_error', sa.Text(), nullable=True)
    )
    op.add_column(
        'subscriptions',
        sa.Column('provisioned_at', sa.DateTime(), nullable=True)
    )

    op.create_index(
        'ix_subscriptions_provisioning_status',
        'subscriptions',
        ['provisioning_status'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_subscriptions_provisioning_status', 'subscriptions')
    op.drop_column('subscriptions', 'provisioned_at')
    op.drop_column('subscriptions', 'provisioning_error')
    op.drop_column('subscriptions', 'gateway_app_id')
    op.drop_column('subscriptions', 'provisioning_status')
