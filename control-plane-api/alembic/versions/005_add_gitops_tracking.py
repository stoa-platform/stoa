# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""add gitops tracking columns

Revision ID: 005
Revises: 004
Create Date: 2026-01-14

Add GitOps tracking columns to mcp_servers table:
- git_path: Path in GitLab repository
- git_commit_sha: Last synced commit SHA
- last_synced_at: Timestamp of last sync
- sync_status: Current sync status (synced, pending, error, orphan)

Also add sync_status enum for MCP server sync states.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create sync_status enum
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE mcpserversyncstatus AS ENUM ('synced', 'pending', 'error', 'orphan');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    # Add GitOps tracking columns to mcp_servers
    op.add_column('mcp_servers', sa.Column('git_path', sa.String(500), nullable=True))
    op.add_column('mcp_servers', sa.Column('git_commit_sha', sa.String(64), nullable=True))
    op.add_column('mcp_servers', sa.Column('last_synced_at', sa.DateTime(), nullable=True))
    op.add_column('mcp_servers', sa.Column(
        'sync_status',
        sa.Enum('synced', 'pending', 'error', 'orphan', name='mcpserversyncstatus', create_type=False),
        nullable=True
    ))
    op.add_column('mcp_servers', sa.Column('sync_error', sa.Text(), nullable=True))

    # Add GitOps tracking columns to mcp_server_tools
    op.add_column('mcp_server_tools', sa.Column('endpoint', sa.String(500), nullable=True))
    op.add_column('mcp_server_tools', sa.Column('method', sa.String(10), nullable=True, server_default='POST'))
    op.add_column('mcp_server_tools', sa.Column('timeout', sa.String(20), nullable=True, server_default='30s'))
    op.add_column('mcp_server_tools', sa.Column('rate_limit', sa.Integer(), nullable=True, server_default='60'))

    # Create index for git_path lookup
    op.create_index('ix_mcp_servers_git_path', 'mcp_servers', ['git_path'])

    # Create index for sync_status queries
    op.create_index('ix_mcp_servers_sync_status', 'mcp_servers', ['sync_status'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_mcp_servers_sync_status', 'mcp_servers')
    op.drop_index('ix_mcp_servers_git_path', 'mcp_servers')

    # Drop columns from mcp_server_tools
    op.drop_column('mcp_server_tools', 'rate_limit')
    op.drop_column('mcp_server_tools', 'timeout')
    op.drop_column('mcp_server_tools', 'method')
    op.drop_column('mcp_server_tools', 'endpoint')

    # Drop columns from mcp_servers
    op.drop_column('mcp_servers', 'sync_error')
    op.drop_column('mcp_servers', 'sync_status')
    op.drop_column('mcp_servers', 'last_synced_at')
    op.drop_column('mcp_servers', 'git_commit_sha')
    op.drop_column('mcp_servers', 'git_path')

    # Drop enum
    op.execute('DROP TYPE IF EXISTS mcpserversyncstatus')
