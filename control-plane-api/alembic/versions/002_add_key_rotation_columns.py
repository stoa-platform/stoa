"""add key rotation columns for grace period support

Revision ID: 002
Revises: 001
Create Date: 2026-01-09

Adds columns to support API key rotation with grace period:
- previous_api_key_hash: Hash of the old key during grace period
- previous_key_expires_at: When the old key becomes invalid
- last_rotated_at: Timestamp of last key rotation
- rotation_count: Number of times the key has been rotated

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add columns for key rotation with grace period
    op.add_column(
        'subscriptions',
        sa.Column('previous_api_key_hash', sa.String(512), nullable=True)
    )
    op.add_column(
        'subscriptions',
        sa.Column('previous_key_expires_at', sa.DateTime(), nullable=True)
    )
    op.add_column(
        'subscriptions',
        sa.Column('last_rotated_at', sa.DateTime(), nullable=True)
    )
    op.add_column(
        'subscriptions',
        sa.Column('rotation_count', sa.Integer(), nullable=False, server_default='0')
    )

    # Create index for looking up by previous key during grace period
    op.create_index(
        'ix_subscriptions_previous_key_hash',
        'subscriptions',
        ['previous_api_key_hash'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_subscriptions_previous_key_hash', 'subscriptions')
    op.drop_column('subscriptions', 'rotation_count')
    op.drop_column('subscriptions', 'last_rotated_at')
    op.drop_column('subscriptions', 'previous_key_expires_at')
    op.drop_column('subscriptions', 'previous_api_key_hash')
