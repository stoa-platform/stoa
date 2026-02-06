"""add gateway mode column and STOA mode enum values

Revision ID: 017
Revises: 016
Create Date: 2026-02-06

Adds:
- mode column to gateway_instances for STOA 4-mode architecture (ADR-024)
- New gateway_type_enum values: stoa_edge_mcp, stoa_sidecar, stoa_proxy, stoa_shadow
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
    # Add mode column
    op.add_column(
        'gateway_instances',
        sa.Column('mode', sa.String(50), nullable=True),
    )
    op.create_index('ix_gw_instances_mode', 'gateway_instances', ['mode'])

    # Add new enum values for STOA modes (ADR-024)
    # Using raw SQL since Alembic doesn't have direct enum value addition
    op.execute("ALTER TYPE gateway_type_enum ADD VALUE IF NOT EXISTS 'stoa_edge_mcp'")
    op.execute("ALTER TYPE gateway_type_enum ADD VALUE IF NOT EXISTS 'stoa_sidecar'")
    op.execute("ALTER TYPE gateway_type_enum ADD VALUE IF NOT EXISTS 'stoa_proxy'")
    op.execute("ALTER TYPE gateway_type_enum ADD VALUE IF NOT EXISTS 'stoa_shadow'")


def downgrade() -> None:
    op.drop_index('ix_gw_instances_mode', 'gateway_instances')
    op.drop_column('gateway_instances', 'mode')
    # Note: PostgreSQL doesn't support removing enum values, so we leave them
