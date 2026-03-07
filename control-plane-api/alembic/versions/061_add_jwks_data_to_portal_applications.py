"""Add jwks_data column to portal_applications (CAB-1748)

Revision ID: 061
Revises: 060
Create Date: 2026-03-07
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "061"
down_revision = "060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "portal_applications",
        sa.Column("jwks_data", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("portal_applications", "jwks_data")
