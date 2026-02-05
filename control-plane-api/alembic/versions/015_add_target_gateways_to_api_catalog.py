"""add target_gateways JSONB column to api_catalog

Revision ID: 015
Revises: 014
Create Date: 2026-02-04

Adds a target_gateways column to api_catalog to declare which gateway
instances an API should be deployed to. An empty list means catalog-only
(not deployed to any gateway).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = '015'
down_revision: Union[str, None] = '014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'api_catalog',
        sa.Column('target_gateways', JSONB, nullable=False, server_default='[]'),
    )


def downgrade() -> None:
    op.drop_column('api_catalog', 'target_gateways')
