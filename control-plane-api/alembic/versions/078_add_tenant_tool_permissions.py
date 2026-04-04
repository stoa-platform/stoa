"""add tenant_tool_permissions table

Revision ID: 078
Revises: 077
Create Date: 2026-04-04

CAB-1980: Tenant-level tool permission overrides with composite unique index.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "078"
down_revision: str | None = "077"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_tool_permissions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False, index=True),
        sa.Column("mcp_server_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("tool_name", sa.String(255), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "uq_tenant_server_tool",
        "tenant_tool_permissions",
        ["tenant_id", "mcp_server_id", "tool_name"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_tenant_server_tool", table_name="tenant_tool_permissions")
    op.drop_table("tenant_tool_permissions")
