"""Add audience column to api_catalog for multi-audience content model (CAB-1323)

Revision ID: 031
Revises: 030
Create Date: 2026-02-18
"""

from alembic import op
import sqlalchemy as sa

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "api_catalog",
        sa.Column("audience", sa.String(20), nullable=False, server_default="public"),
    )
    op.create_check_constraint(
        "ck_api_catalog_audience",
        "api_catalog",
        "audience IN ('public', 'internal', 'partner')",
    )
    op.create_index("ix_api_catalog_audience", "api_catalog", ["audience"])


def downgrade() -> None:
    op.drop_index("ix_api_catalog_audience", table_name="api_catalog")
    op.drop_constraint("ck_api_catalog_audience", "api_catalog", type_="check")
    op.drop_column("api_catalog", "audience")
