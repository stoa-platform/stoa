"""add is_platform flag and seed STOA Gateway as built-in MCP server

Revision ID: 091
Revises: 090_add_tenant_tool_permissions
Create Date: 2026-04-07

CAB-2003: STOA Gateway as first-class MCP Server in admin console.
Adds is_platform boolean to external_mcp_servers and seeds the gateway row.
"""

from collections.abc import Sequence
from datetime import datetime
from uuid import NAMESPACE_DNS, uuid5

import sqlalchemy as sa
from alembic import op

revision: str = "091_add_is_platform_and_seed_gateway"
down_revision: str | None = "090_add_tenant_tool_permissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Deterministic UUID for the STOA Gateway seed row — always the same across environments
STOA_GATEWAY_ID = str(uuid5(NAMESPACE_DNS, "stoa-gateway"))


def upgrade() -> None:
    # 1. Add is_platform column (default false for existing rows)
    op.add_column(
        "external_mcp_servers",
        sa.Column("is_platform", sa.Boolean(), nullable=False, server_default="false"),
    )

    # 2. Seed STOA Gateway as built-in platform server
    op.execute(sa.text("""
            INSERT INTO external_mcp_servers (
                id, name, display_name, description, base_url, transport, auth_type,
                enabled, health_status, is_platform, created_at, updated_at, created_by
            ) VALUES (
                :id, 'stoa-gateway', 'STOA Gateway',
                'Platform-native MCP server — tools generated from governed APIs',
                'internal://stoa-gateway', 'http', 'none',
                true, 'healthy', true, :now, :now, 'system'
            )
            ON CONFLICT (name) DO UPDATE SET is_platform = true
            """).bindparams(id=STOA_GATEWAY_ID, now=datetime.utcnow()))


def downgrade() -> None:
    # Remove the seed row first, then drop the column
    op.execute(sa.text("DELETE FROM external_mcp_servers WHERE id = :id").bindparams(id=STOA_GATEWAY_ID))
    op.drop_column("external_mcp_servers", "is_platform")
