"""Add cache token columns to usage_summaries (CAB-1601).

Adds input_tokens, output_tokens, cache_creation_input_tokens, and
cache_read_input_tokens to the usage_summaries table for Anthropic
prompt caching support.

Revision ID: 049_cache_token_columns
Revises: 048_seed_chat_completions
Create Date: 2026-03-01
"""

import sqlalchemy as sa
from alembic import op

revision = "049_cache_token_columns"
down_revision = "048_seed_chat_completions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "usage_summaries",
        sa.Column("input_tokens", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "usage_summaries",
        sa.Column("output_tokens", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "usage_summaries",
        sa.Column("cache_creation_input_tokens", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "usage_summaries",
        sa.Column("cache_read_input_tokens", sa.BigInteger(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("usage_summaries", "cache_read_input_tokens")
    op.drop_column("usage_summaries", "cache_creation_input_tokens")
    op.drop_column("usage_summaries", "output_tokens")
    op.drop_column("usage_summaries", "input_tokens")
