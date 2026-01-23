"""Create external MCP servers tables

Revision ID: 010
Revises: 009
Create Date: 2026-01-23

Creates tables for external MCP server registration:
- external_mcp_servers: External MCP server configurations (Linear, GitHub, etc.)
- external_mcp_server_tools: Tools discovered/synced from external servers
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '010'
down_revision: Union[str, None] = '009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enums with IF NOT EXISTS to be idempotent
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE externalmcptransport AS ENUM ('sse', 'http', 'websocket');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE externalmcpauthtype AS ENUM ('none', 'api_key', 'bearer_token', 'oauth2');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE externalmcphealthstatus AS ENUM ('unknown', 'healthy', 'degraded', 'unhealthy');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    # Create external_mcp_servers table
    op.create_table(
        'external_mcp_servers',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('icon', sa.String(500), nullable=True),
        sa.Column('base_url', sa.String(500), nullable=False),
        sa.Column('transport', postgresql.ENUM('sse', 'http', 'websocket', name='externalmcptransport', create_type=False), nullable=False, server_default='sse'),
        sa.Column('auth_type', postgresql.ENUM('none', 'api_key', 'bearer_token', 'oauth2', name='externalmcpauthtype', create_type=False), nullable=False, server_default='none'),
        sa.Column('credential_vault_path', sa.String(500), nullable=True),
        sa.Column('tool_prefix', sa.String(100), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('health_status', postgresql.ENUM('unknown', 'healthy', 'degraded', 'unhealthy', name='externalmcphealthstatus', create_type=False), nullable=False, server_default='unknown'),
        sa.Column('last_health_check', sa.DateTime(), nullable=True),
        sa.Column('last_sync_at', sa.DateTime(), nullable=True),
        sa.Column('sync_error', sa.Text(), nullable=True),
        sa.Column('tenant_id', sa.String(255), nullable=True),  # null = platform-wide
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('created_by', sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_external_mcp_servers_name')
    )
    op.create_index('ix_external_mcp_servers_tenant_id', 'external_mcp_servers', ['tenant_id'])
    op.create_index('ix_external_mcp_servers_enabled', 'external_mcp_servers', ['enabled'])
    op.create_index('ix_external_mcp_servers_tenant_enabled', 'external_mcp_servers', ['tenant_id', 'enabled'])

    # Create external_mcp_server_tools table
    op.create_table(
        'external_mcp_server_tools',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('server_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),  # Original tool name from external server
        sa.Column('namespaced_name', sa.String(255), nullable=False),  # {prefix}__{name} or just {name}
        sa.Column('display_name', sa.String(255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('input_schema', postgresql.JSON(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('synced_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['server_id'], ['external_mcp_servers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_external_mcp_server_tools_server_id', 'external_mcp_server_tools', ['server_id'])
    op.create_index('ix_external_mcp_server_tools_server_name', 'external_mcp_server_tools', ['server_id', 'name'], unique=True)
    op.create_index('ix_external_mcp_server_tools_namespaced', 'external_mcp_server_tools', ['namespaced_name'])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_index('ix_external_mcp_server_tools_namespaced', 'external_mcp_server_tools')
    op.drop_index('ix_external_mcp_server_tools_server_name', 'external_mcp_server_tools')
    op.drop_index('ix_external_mcp_server_tools_server_id', 'external_mcp_server_tools')
    op.drop_table('external_mcp_server_tools')

    op.drop_index('ix_external_mcp_servers_tenant_enabled', 'external_mcp_servers')
    op.drop_index('ix_external_mcp_servers_enabled', 'external_mcp_servers')
    op.drop_index('ix_external_mcp_servers_tenant_id', 'external_mcp_servers')
    op.drop_table('external_mcp_servers')

    # Drop enums
    op.execute('DROP TYPE IF EXISTS externalmcphealthstatus')
    op.execute('DROP TYPE IF EXISTS externalmcpauthtype')
    op.execute('DROP TYPE IF EXISTS externalmcptransport')
