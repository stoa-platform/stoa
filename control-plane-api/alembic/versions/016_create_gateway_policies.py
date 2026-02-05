"""create gateway_policies and gateway_policy_bindings tables

Revision ID: 016
Revises: 015
Create Date: 2026-02-04

Adds two tables for gateway-agnostic policy management:
- gateway_policies: reusable policy definitions (CORS, rate limit, etc.)
- gateway_policy_bindings: junction binding policies to API/gateway/tenant
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = '016'
down_revision: Union[str, None] = '015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types
    policy_type_enum = sa.Enum(
        'cors', 'rate_limit', 'jwt_validation', 'ip_filter',
        'logging', 'caching', 'transform',
        name='policy_type_enum',
    )
    policy_type_enum.create(op.get_bind(), checkfirst=True)

    policy_scope_enum = sa.Enum(
        'api', 'gateway', 'tenant',
        name='policy_scope_enum',
    )
    policy_scope_enum.create(op.get_bind(), checkfirst=True)

    # Create gateway_policies table
    op.create_table(
        'gateway_policies',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('policy_type', policy_type_enum, nullable=False),
        sa.Column('tenant_id', sa.String(255), nullable=True),
        sa.Column('scope', policy_scope_enum, nullable=False, server_default='api'),
        sa.Column('config', JSONB, nullable=False, server_default='{}'),
        sa.Column('priority', sa.Integer, nullable=False, server_default='100'),
        sa.Column('enabled', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('name', 'tenant_id', name='uq_policy_name_tenant'),
    )
    op.create_index('ix_gateway_policies_tenant_id', 'gateway_policies', ['tenant_id'])

    # Create gateway_policy_bindings table
    op.create_table(
        'gateway_policy_bindings',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'policy_id',
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey('gateway_policies.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'api_catalog_id',
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey('api_catalog.id', ondelete='CASCADE'),
            nullable=True,
        ),
        sa.Column(
            'gateway_instance_id',
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey('gateway_instances.id', ondelete='CASCADE'),
            nullable=True,
        ),
        sa.Column('tenant_id', sa.String(255), nullable=True),
        sa.Column('enabled', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('policy_id', 'api_catalog_id', 'gateway_instance_id', name='uq_policy_binding'),
    )
    op.create_index('ix_policy_binding_policy', 'gateway_policy_bindings', ['policy_id'])
    op.create_index('ix_policy_binding_api', 'gateway_policy_bindings', ['api_catalog_id'])
    op.create_index('ix_policy_binding_gateway', 'gateway_policy_bindings', ['gateway_instance_id'])
    op.create_index('ix_policy_binding_tenant_id', 'gateway_policy_bindings', ['tenant_id'])


def downgrade() -> None:
    op.drop_table('gateway_policy_bindings')
    op.drop_table('gateway_policies')
    sa.Enum(name='policy_scope_enum').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='policy_type_enum').drop(op.get_bind(), checkfirst=True)
