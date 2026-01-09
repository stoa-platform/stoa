"""Create webhook tables for CAB-315

Revision ID: 003_webhooks
Revises: 002_add_key_rotation_columns
Create Date: 2026-01-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '003_webhooks'
down_revision: Union[str, None] = '002_rotation'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create tenant_webhooks table
    op.create_table(
        'tenant_webhooks',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('url', sa.String(2048), nullable=False),
        sa.Column('secret', sa.String(512), nullable=True),
        sa.Column('events', postgresql.JSON(), nullable=False),
        sa.Column('headers', postgresql.JSON(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('created_by', sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_tenant_webhooks_tenant_id', 'tenant_webhooks', ['tenant_id'], unique=False)
    op.create_index('ix_tenant_webhooks_tenant_enabled', 'tenant_webhooks', ['tenant_id', 'enabled'], unique=False)

    # Create webhook_deliveries table
    op.create_table(
        'webhook_deliveries',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('webhook_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('subscription_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('payload', postgresql.JSON(), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('response_status_code', sa.Integer(), nullable=True),
        sa.Column('response_body', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('last_attempt_at', sa.DateTime(), nullable=True),
        sa.Column('next_retry_at', sa.DateTime(), nullable=True),
        sa.Column('delivered_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_webhook_deliveries_webhook_id', 'webhook_deliveries', ['webhook_id'], unique=False)
    op.create_index('ix_webhook_deliveries_subscription_id', 'webhook_deliveries', ['subscription_id'], unique=False)
    op.create_index('ix_webhook_deliveries_status_retry', 'webhook_deliveries', ['status', 'next_retry_at'], unique=False)
    op.create_index('ix_webhook_deliveries_webhook_created', 'webhook_deliveries', ['webhook_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_webhook_deliveries_webhook_created', table_name='webhook_deliveries')
    op.drop_index('ix_webhook_deliveries_status_retry', table_name='webhook_deliveries')
    op.drop_index('ix_webhook_deliveries_subscription_id', table_name='webhook_deliveries')
    op.drop_index('ix_webhook_deliveries_webhook_id', table_name='webhook_deliveries')
    op.drop_table('webhook_deliveries')

    op.drop_index('ix_tenant_webhooks_tenant_enabled', table_name='tenant_webhooks')
    op.drop_index('ix_tenant_webhooks_tenant_id', table_name='tenant_webhooks')
    op.drop_table('tenant_webhooks')
