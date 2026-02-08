"""create gateway_deployments table for desired vs actual state tracking

Revision ID: 014
Revises: 013
Create Date: 2026-02-04

Adds the gateway_deployments junction table linking API catalog entries
to gateway instances with sync status and desired/actual state tracking.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = '014'
down_revision: Union[str, None] = '013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    sync_status_enum = sa.Enum(
        'pending', 'syncing', 'synced', 'drifted', 'error', 'deleting',
        name='deployment_sync_status_enum',
    )

    op.create_table(
        'gateway_deployments',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'api_catalog_id', UUID(as_uuid=True),
            sa.ForeignKey('api_catalog.id', ondelete='CASCADE'), nullable=False,
        ),
        sa.Column(
            'gateway_instance_id', UUID(as_uuid=True),
            sa.ForeignKey('gateway_instances.id', ondelete='CASCADE'), nullable=False,
        ),
        sa.Column('desired_state', JSONB, nullable=False, server_default='{}'),
        sa.Column('desired_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('actual_state', JSONB, nullable=True),
        sa.Column('actual_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sync_status', sync_status_enum, nullable=False, server_default='pending'),
        sa.Column('last_sync_attempt', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_sync_success', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sync_error', sa.Text(), nullable=True),
        sa.Column('sync_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('gateway_resource_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_unique_constraint(
        'uq_deployment_api_gateway', 'gateway_deployments',
        ['api_catalog_id', 'gateway_instance_id'],
    )
    op.create_index('ix_gw_deploy_sync_status', 'gateway_deployments', ['sync_status'])
    op.create_index('ix_gw_deploy_gateway', 'gateway_deployments', ['gateway_instance_id'])
    op.create_index('ix_gw_deploy_api', 'gateway_deployments', ['api_catalog_id'])


def downgrade() -> None:
    op.drop_index('ix_gw_deploy_api', 'gateway_deployments')
    op.drop_index('ix_gw_deploy_gateway', 'gateway_deployments')
    op.drop_index('ix_gw_deploy_sync_status', 'gateway_deployments')
    op.drop_constraint('uq_deployment_api_gateway', 'gateway_deployments')
    op.drop_table('gateway_deployments')

    sa.Enum(name='deployment_sync_status_enum').drop(op.get_bind(), checkfirst=True)
