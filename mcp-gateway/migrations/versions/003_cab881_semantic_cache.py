# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""CAB-881: Semantic cache table with pgvector.

Revision ID: 003_cab881
Revises: 002_cab660
Create Date: 2026-01-28

Creates:
- pgvector extension (IF NOT EXISTS)
- semantic_cache table with embedding column (vector(384))
- RLS policy for tenant isolation
- Indexes for fast lookup
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "003_cab881"
down_revision: Union[str, None] = "002_cab660"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Create semantic_cache table via raw SQL (vector type not supported by sa.Column)
    op.execute("""
        CREATE TABLE semantic_cache (
            id BIGSERIAL PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL,
            tool_name VARCHAR(255) NOT NULL,
            key_hash VARCHAR(64) NOT NULL,
            embedding vector(384) NOT NULL,
            response_payload TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL
        )
    """)

    # Unique constraint for fast-path upsert
    op.create_unique_constraint(
        "uq_semantic_cache_tenant_hash",
        "semantic_cache",
        ["tenant_id", "key_hash"],
    )

    # Index for fast-path exact match
    op.create_index(
        "ix_semantic_cache_tenant_hash",
        "semantic_cache",
        ["tenant_id", "key_hash"],
    )

    # Index for TTL cleanup
    op.create_index(
        "ix_semantic_cache_expires_at",
        "semantic_cache",
        ["expires_at"],
    )

    # Index for tool-scoped queries
    op.create_index(
        "ix_semantic_cache_tenant_tool",
        "semantic_cache",
        ["tenant_id", "tool_name"],
    )

    # IVFFlat index for cosine similarity search (pgvector)
    # Using lists=10 for small-to-medium datasets; increase for large scale
    op.execute("""
        CREATE INDEX ix_semantic_cache_embedding
        ON semantic_cache
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 10)
    """)

    # Enable Row Level Security for tenant isolation
    op.execute("ALTER TABLE semantic_cache ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON semantic_cache
        USING (tenant_id = current_setting('app.current_tenant', true))
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON semantic_cache")
    op.execute("ALTER TABLE semantic_cache DISABLE ROW LEVEL SECURITY")
    op.drop_table("semantic_cache")
    # Don't drop the vector extension — other tables might use it
