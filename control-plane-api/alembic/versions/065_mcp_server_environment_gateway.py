"""Add environment and gateway_instance_id to external_mcp_servers.

Multi-environment dataplane support: MCP servers are scoped to an environment
(dev/staging/production) and optionally bound to a specific gateway instance.

Revision ID: 065_mcp_server_environment_gateway
Revises: 064_create_tenant_cas_table
Create Date: 2026-03-12
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "065_mcp_server_environment_gateway"
down_revision = "064_create_tenant_cas_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "external_mcp_servers",
        sa.Column("environment", sa.String(50), nullable=True, server_default="dev"),
    )
    op.add_column(
        "external_mcp_servers",
        sa.Column(
            "gateway_instance_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gateway_instances.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_external_mcp_servers_environment",
        "external_mcp_servers",
        ["environment"],
    )
    # Backfill existing rows to 'dev'
    op.execute("UPDATE external_mcp_servers SET environment = 'dev' WHERE environment IS NULL")


def downgrade() -> None:
    op.drop_index("ix_external_mcp_servers_environment", table_name="external_mcp_servers")
    op.drop_column("external_mcp_servers", "gateway_instance_id")
    op.drop_column("external_mcp_servers", "environment")
