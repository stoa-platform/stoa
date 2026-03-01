"""041 — Create mcp_generated_tools table (CAB-605).

Revision ID: 041_mcp_generated_tools
Revises: 040b
Create Date: 2026-02-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "041_mcp_generated_tools"
down_revision = "040b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_generated_tools",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("tool_name", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("input_schema", sa.Text(), nullable=True),
        sa.Column("output_schema", sa.Text(), nullable=True),
        sa.Column("backend_url", sa.String(512), nullable=True),
        sa.Column("http_method", sa.String(10), nullable=True),
        sa.Column("path_pattern", sa.String(512), nullable=True),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("spec_hash", sa.String(64), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mcp_tools_tenant", "mcp_generated_tools", ["tenant_id"])
    op.create_index("ix_mcp_tools_contract", "mcp_generated_tools", ["contract_id"])
    op.create_index(
        "ix_mcp_tools_name",
        "mcp_generated_tools",
        ["tenant_id", "tool_name"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_mcp_tools_name", table_name="mcp_generated_tools")
    op.drop_index("ix_mcp_tools_contract", table_name="mcp_generated_tools")
    op.drop_index("ix_mcp_tools_tenant", table_name="mcp_generated_tools")
    op.drop_table("mcp_generated_tools")
