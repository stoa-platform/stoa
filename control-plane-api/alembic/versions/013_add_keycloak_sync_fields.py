"""Add Keycloak sync fields to clients table

Revision ID: 013
Revises: 012
Create Date: 2026-01-28

CAB-866: Keycloak Certificate Sync Service

Adds fields to track Keycloak synchronization status for mTLS clients:
- keycloak_client_id: UUID of the client in Keycloak
- keycloak_sync_status: synced|failed|pending
- keycloak_synced_at: timestamp of last successful sync
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '013'
down_revision: Union[str, None] = '012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('clients', sa.Column('keycloak_client_id', sa.String(255), nullable=True))
    op.add_column('clients', sa.Column('keycloak_sync_status', sa.String(50), nullable=True))
    op.add_column('clients', sa.Column('keycloak_synced_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('clients', 'keycloak_synced_at')
    op.drop_column('clients', 'keycloak_sync_status')
    op.drop_column('clients', 'keycloak_client_id')
