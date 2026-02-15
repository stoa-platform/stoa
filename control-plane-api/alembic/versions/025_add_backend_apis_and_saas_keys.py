"""Add backend_apis and saas_api_keys tables.

Revision ID: 025
Revises: 024
Create Date: 2026-02-15

SaaS self-service: tenants register backend APIs for MCP exposure,
scoped API keys control which backends an agent can access (CAB-1188).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "025"
down_revision: str | None = "024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create enum types
    backend_api_auth_type_enum = sa.Enum(
        "none", "api_key", "bearer", "basic", "oauth2_cc",
        name="backend_api_auth_type_enum",
    )
    backend_api_status_enum = sa.Enum(
        "draft", "active", "disabled",
        name="backend_api_status_enum",
    )
    saas_api_key_status_enum = sa.Enum(
        "active", "revoked", "expired",
        name="saas_api_key_status_enum",
    )

    # backend_apis table
    op.create_table(
        "backend_apis",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("backend_url", sa.String(2048), nullable=False),
        sa.Column("openapi_spec_url", sa.String(2048), nullable=True),
        sa.Column("openapi_spec", postgresql.JSONB(), nullable=True),
        sa.Column("spec_hash", sa.String(64), nullable=True),
        sa.Column("auth_type", backend_api_auth_type_enum, nullable=False, server_default="none"),
        sa.Column("auth_config_encrypted", sa.Text(), nullable=True),
        sa.Column("tool_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("status", backend_api_status_enum, nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_backend_apis_tenant_name", "backend_apis",
        ["tenant_id", "name"], unique=True,
    )
    op.create_index(
        "ix_backend_apis_tenant_status", "backend_apis",
        ["tenant_id", "status"],
    )

    # saas_api_keys table
    op.create_table(
        "saas_api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("key_hash", sa.String(512), nullable=False, unique=True),
        sa.Column("key_prefix", sa.String(20), nullable=False),
        sa.Column("allowed_backend_api_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("rate_limit_rpm", sa.Integer(), nullable=True),
        sa.Column("status", saas_api_key_status_enum, nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_saas_api_keys_tenant_name", "saas_api_keys",
        ["tenant_id", "name"], unique=True,
    )
    op.create_index(
        "ix_saas_api_keys_tenant_status", "saas_api_keys",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_saas_api_keys_prefix", "saas_api_keys",
        ["key_prefix"],
    )


def downgrade() -> None:
    op.drop_table("saas_api_keys")
    op.drop_table("backend_apis")
    op.execute("DROP TYPE IF EXISTS saas_api_key_status_enum")
    op.execute("DROP TYPE IF EXISTS backend_api_status_enum")
    op.execute("DROP TYPE IF EXISTS backend_api_auth_type_enum")
