# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Create MCP Error Snapshots table

Revision ID: 006_mcp_snapshots
Revises: 005_add_gitops_tracking
Create Date: 2026-01-15

CAB-397: Error Snapshot / Flight Recorder (Time-Travel Debugging)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '006_mcp_snapshots'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create ResolutionStatus enum type
    resolution_status_enum = postgresql.ENUM(
        'unresolved', 'investigating', 'resolved', 'ignored',
        name='resolutionstatus',
        create_type=False
    )

    # Create the enum type first
    op.execute("CREATE TYPE resolutionstatus AS ENUM ('unresolved', 'investigating', 'resolved', 'ignored')")

    # Create mcp_error_snapshots table
    op.create_table(
        'mcp_error_snapshots',
        sa.Column('id', sa.String(50), primary_key=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, index=True),

        # Error classification
        sa.Column('error_type', sa.String(50), nullable=False, index=True),
        sa.Column('error_message', sa.Text, nullable=False),
        sa.Column('error_code', sa.String(100), nullable=True),
        sa.Column('response_status', sa.Integer, nullable=False, default=500, index=True),

        # Request context
        sa.Column('request_method', sa.String(10), nullable=True),
        sa.Column('request_path', sa.Text, nullable=True),

        # User context
        sa.Column('user_id', sa.String(255), nullable=True, index=True),
        sa.Column('tenant_id', sa.String(100), nullable=True, index=True),

        # MCP context
        sa.Column('mcp_server_name', sa.String(100), nullable=True, index=True),
        sa.Column('tool_name', sa.String(100), nullable=True, index=True),

        # LLM context
        sa.Column('llm_provider', sa.String(50), nullable=True),
        sa.Column('llm_model', sa.String(100), nullable=True),
        sa.Column('llm_tokens_input', sa.Integer, nullable=True),
        sa.Column('llm_tokens_output', sa.Integer, nullable=True),

        # Cost tracking
        sa.Column('total_cost_usd', sa.Float, nullable=False, default=0.0),
        sa.Column('tokens_wasted', sa.Integer, nullable=False, default=0),

        # Retry context
        sa.Column('retry_attempts', sa.Integer, nullable=False, default=1),
        sa.Column('retry_max_attempts', sa.Integer, nullable=False, default=3),

        # Tracing
        sa.Column('trace_id', sa.String(64), nullable=True, index=True),
        sa.Column('conversation_id', sa.String(64), nullable=True),

        # Resolution workflow
        sa.Column('resolution_status', resolution_status_enum, nullable=False, server_default='unresolved', index=True),
        sa.Column('resolution_notes', sa.Text, nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by', sa.String(255), nullable=True),

        # Full snapshot data as JSONB
        sa.Column('snapshot_data', postgresql.JSONB, nullable=False),
    )

    # Create composite indexes for common queries
    op.create_index('ix_mcp_snapshots_timestamp_desc', 'mcp_error_snapshots', [sa.text('timestamp DESC')])
    op.create_index('ix_mcp_snapshots_tenant_timestamp', 'mcp_error_snapshots', ['tenant_id', sa.text('timestamp DESC')])
    op.create_index('ix_mcp_snapshots_server_timestamp', 'mcp_error_snapshots', ['mcp_server_name', sa.text('timestamp DESC')])
    op.create_index('ix_mcp_snapshots_tool_timestamp', 'mcp_error_snapshots', ['tool_name', sa.text('timestamp DESC')])
    op.create_index('ix_mcp_snapshots_error_type_timestamp', 'mcp_error_snapshots', ['error_type', sa.text('timestamp DESC')])
    op.create_index('ix_mcp_snapshots_resolution_timestamp', 'mcp_error_snapshots', ['resolution_status', sa.text('timestamp DESC')])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_mcp_snapshots_resolution_timestamp', 'mcp_error_snapshots')
    op.drop_index('ix_mcp_snapshots_error_type_timestamp', 'mcp_error_snapshots')
    op.drop_index('ix_mcp_snapshots_tool_timestamp', 'mcp_error_snapshots')
    op.drop_index('ix_mcp_snapshots_server_timestamp', 'mcp_error_snapshots')
    op.drop_index('ix_mcp_snapshots_tenant_timestamp', 'mcp_error_snapshots')
    op.drop_index('ix_mcp_snapshots_timestamp_desc', 'mcp_error_snapshots')

    # Drop table
    op.drop_table('mcp_error_snapshots')

    # Drop enum type
    op.execute("DROP TYPE resolutionstatus")
