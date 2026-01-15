"""Create pipeline_traces table for E2E monitoring

Revision ID: 008
Revises: 007
Create Date: 2026-01-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '008'
down_revision: Union[str, None] = '007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum for trace status
    trace_status_enum = postgresql.ENUM(
        'pending', 'in_progress', 'success', 'failed', 'skipped',
        name='tracestatus',
        create_type=False
    )

    # Create the enum type first
    op.execute("CREATE TYPE tracestatus AS ENUM ('pending', 'in_progress', 'success', 'failed', 'skipped')")

    # Create pipeline_traces table
    op.create_table(
        'pipeline_traces',
        sa.Column('id', sa.String(36), primary_key=True),

        # Trigger info
        sa.Column('trigger_type', sa.String(50), nullable=False),
        sa.Column('trigger_source', sa.String(50), nullable=False),

        # Git info
        sa.Column('git_commit_sha', sa.String(40), nullable=True),
        sa.Column('git_commit_message', sa.Text, nullable=True),
        sa.Column('git_branch', sa.String(255), nullable=True),
        sa.Column('git_author', sa.String(255), nullable=True),
        sa.Column('git_author_email', sa.String(255), nullable=True),
        sa.Column('git_project', sa.String(255), nullable=True),
        sa.Column('git_files_changed', postgresql.JSONB, nullable=True),

        # Target info
        sa.Column('tenant_id', sa.String(100), nullable=True),
        sa.Column('api_id', sa.String(100), nullable=True),
        sa.Column('api_name', sa.String(255), nullable=True),
        sa.Column('environment', sa.String(50), nullable=True),

        # Timing
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('total_duration_ms', sa.Integer, nullable=True),

        # Status
        sa.Column('status', trace_status_enum, nullable=False, server_default='pending'),
        sa.Column('error_summary', sa.Text, nullable=True),

        # Steps stored as JSONB array
        sa.Column('steps', postgresql.JSONB, nullable=False, server_default='[]'),
    )

    # Create indexes for common queries
    op.create_index('idx_traces_tenant_id', 'pipeline_traces', ['tenant_id'])
    op.create_index('idx_traces_status', 'pipeline_traces', ['status'])
    op.create_index('idx_traces_created_at', 'pipeline_traces', ['created_at'], postgresql_using='btree')
    op.create_index('idx_traces_trigger_type', 'pipeline_traces', ['trigger_type'])


def downgrade() -> None:
    op.drop_index('idx_traces_trigger_type', table_name='pipeline_traces')
    op.drop_index('idx_traces_created_at', table_name='pipeline_traces')
    op.drop_index('idx_traces_status', table_name='pipeline_traces')
    op.drop_index('idx_traces_tenant_id', table_name='pipeline_traces')
    op.drop_table('pipeline_traces')
    op.execute("DROP TYPE tracestatus")
