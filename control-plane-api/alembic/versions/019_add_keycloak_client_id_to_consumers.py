"""add keycloak_client_id to consumers table

Revision ID: 019
Revises: 018
Create Date: 2026-02-09

CAB-1121 Phase 2: Keycloak Consumer Integration
- keycloak_client_id column for OAuth2 client reference
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "019"
down_revision: str | None = "018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "consumers",
        sa.Column("keycloak_client_id", sa.String(255), nullable=True),
    )
    op.create_index("ix_consumers_keycloak_client_id", "consumers", ["keycloak_client_id"])


def downgrade() -> None:
    op.drop_index("ix_consumers_keycloak_client_id", table_name="consumers")
    op.drop_column("consumers", "keycloak_client_id")
