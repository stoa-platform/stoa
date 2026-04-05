"""add enabled and visibility columns to gateway_instances

Revision ID: 089
Revises: 088
Create Date: 2026-04-04

CAB-1979: Gateway enabled flag + visibility + soft disable enforcement.
Adds enabled (boolean, default true) and visibility (JSONB, nullable) columns.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "089_add_gateway_enabled_visibility"
down_revision: str | None = "088"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "gateway_instances",
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "gateway_instances",
        sa.Column("visibility", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("gateway_instances", "visibility")
    op.drop_column("gateway_instances", "enabled")
