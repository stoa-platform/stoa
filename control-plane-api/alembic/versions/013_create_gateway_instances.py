"""create gateway_instances table for multi-gateway orchestration

Revision ID: 013
Revises: 012
Create Date: 2026-02-04

Adds the gateway_instances table to register external gateways
(webMethods, Kong, Apigee, STOA, etc.) that the Control Plane can pilot.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = '013'
down_revision: Union[str, None] = '012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    gateway_type_enum = sa.Enum(
        'webmethods', 'kong', 'apigee', 'aws_apigateway', 'stoa',
        name='gateway_type_enum',
    )
    gateway_status_enum = sa.Enum(
        'online', 'offline', 'degraded', 'maintenance',
        name='gateway_instance_status_enum',
    )

    op.create_table(
        'gateway_instances',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), unique=True, nullable=False),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('gateway_type', gateway_type_enum, nullable=False),
        sa.Column('environment', sa.String(50), nullable=False),
        sa.Column('tenant_id', sa.String(255), nullable=True),
        sa.Column('base_url', sa.String(500), nullable=False),
        sa.Column('auth_config', JSONB, nullable=False, server_default='{}'),
        sa.Column('status', gateway_status_enum, nullable=False, server_default='offline'),
        sa.Column('last_health_check', sa.DateTime(timezone=True), nullable=True),
        sa.Column('health_details', JSONB, nullable=True),
        sa.Column('capabilities', JSONB, nullable=False, server_default='[]'),
        sa.Column('version', sa.String(50), nullable=True),
        sa.Column('tags', JSONB, nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index('ix_gw_instances_type_env', 'gateway_instances', ['gateway_type', 'environment'])
    op.create_index('ix_gw_instances_environment', 'gateway_instances', ['environment'])
    op.create_index('ix_gw_instances_tenant', 'gateway_instances', ['tenant_id'])


def downgrade() -> None:
    op.drop_index('ix_gw_instances_tenant', 'gateway_instances')
    op.drop_index('ix_gw_instances_environment', 'gateway_instances')
    op.drop_index('ix_gw_instances_type_env', 'gateway_instances')
    op.drop_table('gateway_instances')

    sa.Enum(name='gateway_instance_status_enum').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='gateway_type_enum').drop(op.get_bind(), checkfirst=True)
