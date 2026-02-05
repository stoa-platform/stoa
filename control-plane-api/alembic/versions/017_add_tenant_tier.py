"""add tenant tier column (CAB-1089)

Revision ID: 017
Revises: 016
Create Date: 2026-02-05

Adds explicit `tier` column to the tenants table for SLO-based
differentiation (demo / platform / business / enterprise).
Previously tier information was buried inside the `settings` JSON column.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '017'
down_revision: Union[str, None] = '016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add tier column with default 'platform' (safest default for existing tenants)
    op.add_column(
        'tenants',
        sa.Column(
            'tier',
            sa.String(32),
            nullable=False,
            server_default='platform',
        ),
    )
    op.create_index('ix_tenants_tier', 'tenants', ['tier'])


def downgrade() -> None:
    op.drop_index('ix_tenants_tier', table_name='tenants')
    op.drop_column('tenants', 'tier')
