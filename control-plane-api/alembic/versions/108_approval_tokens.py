"""approval tokens for destructive MCP calls

Revision ID: 108_approval_tokens
Revises: 107_audit_immutability_pseudonymization
Create Date: 2026-05-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "108_approval_tokens"
down_revision: str | tuple[str, ...] | None = "107_audit_immutability_pseudonymization"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "approval_tokens",
        sa.Column("jti", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("tool_name", sa.String(length=512), nullable=False),
        sa.Column("tool_call_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("arguments_hash", sa.String(length=64), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("contract_version", sa.String(length=128), nullable=False),
        sa.Column("requester_actor_id", sa.String(length=255), nullable=False),
        sa.Column("approver_actor_id", sa.String(length=255), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
    )
    op.create_index("ix_approval_tokens_tenant_id", "approval_tokens", ["tenant_id"])
    op.create_index("idx_approval_tokens_tenant_status", "approval_tokens", ["tenant_id", "status"])
    op.create_index("idx_approval_tokens_expires_at", "approval_tokens", ["expires_at"])


def downgrade() -> None:
    op.drop_index("idx_approval_tokens_expires_at", table_name="approval_tokens")
    op.drop_index("idx_approval_tokens_tenant_status", table_name="approval_tokens")
    op.drop_index("ix_approval_tokens_tenant_id", table_name="approval_tokens")
    op.drop_table("approval_tokens")
