# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Create catalog cache tables for API and MCP tools caching

Revision ID: 009
Revises: 008
Create Date: 2026-01-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '009'
down_revision: Union[str, None] = '008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create api_catalog table
    op.create_table(
        'api_catalog',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.String(100), nullable=False),
        sa.Column('api_id', sa.String(100), nullable=False),
        sa.Column('api_name', sa.String(255), nullable=True),
        sa.Column('version', sa.String(50), nullable=True),
        sa.Column('status', sa.String(50), server_default='active', nullable=False),
        sa.Column('category', sa.String(100), nullable=True),
        sa.Column('tags', postgresql.JSONB, server_default='[]', nullable=False),
        sa.Column('portal_published', sa.Boolean, server_default='false', nullable=False),
        sa.Column('metadata', postgresql.JSONB, nullable=False),
        sa.Column('openapi_spec', postgresql.JSONB, nullable=True),
        sa.Column('git_path', sa.String(500), nullable=True),
        sa.Column('git_commit_sha', sa.String(40), nullable=True),
        sa.Column('synced_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('tenant_id', 'api_id', name='uq_api_catalog_tenant_api')
    )

    # Create indexes for api_catalog
    op.create_index('ix_api_catalog_tenant', 'api_catalog', ['tenant_id'])
    op.create_index('ix_api_catalog_portal', 'api_catalog', ['portal_published'])
    op.create_index('ix_api_catalog_status', 'api_catalog', ['status'])
    op.create_index('ix_api_catalog_category', 'api_catalog', ['category'])

    # Create mcp_tools_catalog table
    op.create_table(
        'mcp_tools_catalog',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.String(100), nullable=False),
        sa.Column('tool_name', sa.String(100), nullable=False),
        sa.Column('display_name', sa.String(255), nullable=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('category', sa.String(100), nullable=True),
        sa.Column('input_schema', postgresql.JSONB, nullable=True),
        sa.Column('output_schema', postgresql.JSONB, nullable=True),
        sa.Column('metadata', postgresql.JSONB, server_default='{}', nullable=False),
        sa.Column('git_path', sa.String(500), nullable=True),
        sa.Column('git_commit_sha', sa.String(40), nullable=True),
        sa.Column('synced_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('tenant_id', 'tool_name', name='uq_mcp_tools_tenant_tool')
    )

    # Create indexes for mcp_tools_catalog
    op.create_index('ix_mcp_tools_tenant', 'mcp_tools_catalog', ['tenant_id'])
    op.create_index('ix_mcp_tools_category', 'mcp_tools_catalog', ['category'])

    # Create catalog_sync_status table for tracking sync operations
    op.create_table(
        'catalog_sync_status',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('sync_type', sa.String(50), nullable=False),  # 'full', 'tenant', 'api'
        sa.Column('status', sa.String(50), nullable=False),  # 'running', 'success', 'failed'
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('items_synced', sa.Integer, server_default='0', nullable=False),
        sa.Column('errors', postgresql.JSONB, server_default='[]', nullable=False),
        sa.Column('git_commit_sha', sa.String(40), nullable=True)
    )

    # Create indexes for catalog_sync_status
    op.create_index('ix_sync_status_type', 'catalog_sync_status', ['sync_type'])
    op.create_index('ix_sync_status_status', 'catalog_sync_status', ['status'])
    op.create_index('ix_sync_status_started_at', 'catalog_sync_status', ['started_at'], postgresql_using='btree')


def downgrade() -> None:
    # Drop indexes for catalog_sync_status
    op.drop_index('ix_sync_status_started_at', table_name='catalog_sync_status')
    op.drop_index('ix_sync_status_status', table_name='catalog_sync_status')
    op.drop_index('ix_sync_status_type', table_name='catalog_sync_status')

    # Drop catalog_sync_status table
    op.drop_table('catalog_sync_status')

    # Drop indexes for mcp_tools_catalog
    op.drop_index('ix_mcp_tools_category', table_name='mcp_tools_catalog')
    op.drop_index('ix_mcp_tools_tenant', table_name='mcp_tools_catalog')

    # Drop mcp_tools_catalog table
    op.drop_table('mcp_tools_catalog')

    # Drop indexes for api_catalog
    op.drop_index('ix_api_catalog_category', table_name='api_catalog')
    op.drop_index('ix_api_catalog_status', table_name='api_catalog')
    op.drop_index('ix_api_catalog_portal', table_name='api_catalog')
    op.drop_index('ix_api_catalog_tenant', table_name='api_catalog')

    # Drop api_catalog table
    op.drop_table('api_catalog')
