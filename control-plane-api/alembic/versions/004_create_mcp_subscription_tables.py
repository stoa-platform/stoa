"""create mcp subscription tables

Revision ID: 004
Revises: 003
Create Date: 2026-01-14

Creates tables for MCP Server subscriptions:
- mcp_servers: MCP Server registry
- mcp_server_tools: Tools within each server
- mcp_server_subscriptions: User subscriptions to servers
- mcp_tool_access: Per-tool access control within subscriptions
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enums
    op.execute("""
        CREATE TYPE mcpservercategory AS ENUM ('platform', 'tenant', 'public')
    """)
    op.execute("""
        CREATE TYPE mcpserverstatus AS ENUM ('active', 'maintenance', 'deprecated')
    """)
    op.execute("""
        CREATE TYPE mcpsubscriptionstatus AS ENUM ('pending', 'active', 'suspended', 'revoked', 'expired')
    """)
    op.execute("""
        CREATE TYPE mcptoolaccessstatus AS ENUM ('enabled', 'disabled', 'pending_approval')
    """)

    # Create mcp_servers table
    op.create_table(
        'mcp_servers',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('icon', sa.String(500), nullable=True),
        sa.Column('category', sa.Enum('platform', 'tenant', 'public', name='mcpservercategory'), nullable=False),
        sa.Column('tenant_id', sa.String(255), nullable=True),
        sa.Column('visibility', postgresql.JSON(), nullable=False),
        sa.Column('requires_approval', sa.Boolean(), nullable=False, default=False),
        sa.Column('auto_approve_roles', postgresql.JSON(), nullable=True),
        sa.Column('status', sa.Enum('active', 'maintenance', 'deprecated', name='mcpserverstatus'), nullable=False),
        sa.Column('version', sa.String(50), nullable=True),
        sa.Column('documentation_url', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index('ix_mcp_servers_tenant_id', 'mcp_servers', ['tenant_id'])
    op.create_index('ix_mcp_servers_category_status', 'mcp_servers', ['category', 'status'])
    op.create_index('ix_mcp_servers_tenant_status', 'mcp_servers', ['tenant_id', 'status'])

    # Create mcp_server_tools table
    op.create_table(
        'mcp_server_tools',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('server_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('input_schema', postgresql.JSON(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, default=True),
        sa.Column('requires_approval', sa.Boolean(), nullable=False, default=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['server_id'], ['mcp_servers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_mcp_server_tools_server_name', 'mcp_server_tools', ['server_id', 'name'], unique=True)

    # Create mcp_server_subscriptions table
    op.create_table(
        'mcp_server_subscriptions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('server_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('subscriber_id', sa.String(255), nullable=False),
        sa.Column('subscriber_email', sa.String(255), nullable=False),
        sa.Column('tenant_id', sa.String(255), nullable=False),
        sa.Column('plan', sa.String(100), nullable=False),
        sa.Column('api_key_hash', sa.String(512), nullable=True),
        sa.Column('api_key_prefix', sa.String(16), nullable=True),
        sa.Column('vault_path', sa.String(500), nullable=True),
        sa.Column('previous_api_key_hash', sa.String(512), nullable=True),
        sa.Column('previous_key_expires_at', sa.DateTime(), nullable=True),
        sa.Column('last_rotated_at', sa.DateTime(), nullable=True),
        sa.Column('rotation_count', sa.Integer(), nullable=False, default=0),
        sa.Column('status', sa.Enum('pending', 'active', 'suspended', 'revoked', 'expired', name='mcpsubscriptionstatus'), nullable=False),
        sa.Column('status_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('approved_by', sa.String(255), nullable=True),
        sa.Column('revoked_by', sa.String(255), nullable=True),
        sa.Column('usage_count', sa.Integer(), nullable=False, default=0),
        sa.ForeignKeyConstraint(['server_id'], ['mcp_servers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('api_key_hash')
    )
    op.create_index('ix_mcp_server_subscriptions_server_id', 'mcp_server_subscriptions', ['server_id'])
    op.create_index('ix_mcp_server_subscriptions_subscriber_id', 'mcp_server_subscriptions', ['subscriber_id'])
    op.create_index('ix_mcp_server_subscriptions_tenant_id', 'mcp_server_subscriptions', ['tenant_id'])
    op.create_index('ix_mcp_server_subscriptions_previous_key', 'mcp_server_subscriptions', ['previous_api_key_hash'])
    op.create_index('ix_mcp_subs_subscriber_server', 'mcp_server_subscriptions', ['subscriber_id', 'server_id'])
    op.create_index('ix_mcp_subs_tenant_status', 'mcp_server_subscriptions', ['tenant_id', 'status'])
    op.create_index('ix_mcp_subs_server_status', 'mcp_server_subscriptions', ['server_id', 'status'])

    # Create mcp_tool_access table
    op.create_table(
        'mcp_tool_access',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('subscription_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tool_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tool_name', sa.String(255), nullable=False),
        sa.Column('status', sa.Enum('enabled', 'disabled', 'pending_approval', name='mcptoolaccessstatus'), nullable=False),
        sa.Column('granted_at', sa.DateTime(), nullable=True),
        sa.Column('granted_by', sa.String(255), nullable=True),
        sa.Column('usage_count', sa.Integer(), nullable=False, default=0),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['subscription_id'], ['mcp_server_subscriptions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_mcp_tool_access_sub_tool', 'mcp_tool_access', ['subscription_id', 'tool_id'], unique=True)


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_index('ix_mcp_tool_access_sub_tool', 'mcp_tool_access')
    op.drop_table('mcp_tool_access')

    op.drop_index('ix_mcp_subs_server_status', 'mcp_server_subscriptions')
    op.drop_index('ix_mcp_subs_tenant_status', 'mcp_server_subscriptions')
    op.drop_index('ix_mcp_subs_subscriber_server', 'mcp_server_subscriptions')
    op.drop_index('ix_mcp_server_subscriptions_previous_key', 'mcp_server_subscriptions')
    op.drop_index('ix_mcp_server_subscriptions_tenant_id', 'mcp_server_subscriptions')
    op.drop_index('ix_mcp_server_subscriptions_subscriber_id', 'mcp_server_subscriptions')
    op.drop_index('ix_mcp_server_subscriptions_server_id', 'mcp_server_subscriptions')
    op.drop_table('mcp_server_subscriptions')

    op.drop_index('ix_mcp_server_tools_server_name', 'mcp_server_tools')
    op.drop_table('mcp_server_tools')

    op.drop_index('ix_mcp_servers_tenant_status', 'mcp_servers')
    op.drop_index('ix_mcp_servers_category_status', 'mcp_servers')
    op.drop_index('ix_mcp_servers_tenant_id', 'mcp_servers')
    op.drop_table('mcp_servers')

    # Drop enums
    op.execute('DROP TYPE IF EXISTS mcptoolaccessstatus')
    op.execute('DROP TYPE IF EXISTS mcpsubscriptionstatus')
    op.execute('DROP TYPE IF EXISTS mcpserverstatus')
    op.execute('DROP TYPE IF EXISTS mcpservercategory')
