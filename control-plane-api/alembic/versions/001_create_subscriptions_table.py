"""create subscriptions table

Revision ID: 001
Revises:
Create Date: 2026-01-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'subscriptions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('application_id', sa.String(255), nullable=False),
        sa.Column('application_name', sa.String(255), nullable=False),
        sa.Column('subscriber_id', sa.String(255), nullable=False),
        sa.Column('subscriber_email', sa.String(255), nullable=False),
        sa.Column('api_id', sa.String(255), nullable=False),
        sa.Column('api_name', sa.String(255), nullable=False),
        sa.Column('api_version', sa.String(50), nullable=False),
        sa.Column('tenant_id', sa.String(255), nullable=False),
        sa.Column('plan_id', sa.String(255), nullable=True),
        sa.Column('plan_name', sa.String(255), nullable=True),
        sa.Column('api_key_hash', sa.String(512), nullable=False),
        sa.Column('api_key_prefix', sa.String(10), nullable=False),
        sa.Column('status', sa.Enum('pending', 'active', 'suspended', 'revoked', 'expired', name='subscriptionstatus'), nullable=False),
        sa.Column('status_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('approved_by', sa.String(255), nullable=True),
        sa.Column('revoked_by', sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('api_key_hash')
    )

    # Create indexes
    op.create_index('ix_subscriptions_application_id', 'subscriptions', ['application_id'])
    op.create_index('ix_subscriptions_subscriber_id', 'subscriptions', ['subscriber_id'])
    op.create_index('ix_subscriptions_api_id', 'subscriptions', ['api_id'])
    op.create_index('ix_subscriptions_tenant_id', 'subscriptions', ['tenant_id'])
    op.create_index('ix_subscriptions_tenant_api', 'subscriptions', ['tenant_id', 'api_id'])
    op.create_index('ix_subscriptions_subscriber_status', 'subscriptions', ['subscriber_id', 'status'])
    op.create_index('ix_subscriptions_application_api', 'subscriptions', ['application_id', 'api_id'])


def downgrade() -> None:
    op.drop_index('ix_subscriptions_application_api', 'subscriptions')
    op.drop_index('ix_subscriptions_subscriber_status', 'subscriptions')
    op.drop_index('ix_subscriptions_tenant_api', 'subscriptions')
    op.drop_index('ix_subscriptions_tenant_id', 'subscriptions')
    op.drop_index('ix_subscriptions_api_id', 'subscriptions')
    op.drop_index('ix_subscriptions_subscriber_id', 'subscriptions')
    op.drop_index('ix_subscriptions_application_id', 'subscriptions')
    op.drop_table('subscriptions')
    op.execute('DROP TYPE IF EXISTS subscriptionstatus')
