"""CAB-660: Initial schema for tool handlers.

Revision ID: 001_cab660
Revises:
Create Date: 2026-01-18

Note: Uses IF NOT EXISTS to safely coexist with control-plane-api schema.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_cab660"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def table_exists(table_name: str) -> bool:
    """Check if a table already exists."""
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :name)"
        ),
        {"name": table_name},
    )
    return result.scalar()


def upgrade() -> None:
    # Tenants table
    if not table_exists("tenants"):
        op.create_table(
            "tenants",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("status", sa.String(32), server_default="active"),
            sa.Column("settings", postgresql.JSONB, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.CheckConstraint(
                "status IN ('active', 'suspended', 'archived')",
                name="ck_tenants_status",
            ),
        )

    # Users table
    if not table_exists("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("keycloak_id", sa.String(64), unique=True, nullable=True),
            sa.Column("email", sa.String(255), nullable=True),
            sa.Column("name", sa.String(255), nullable=True),
            sa.Column(
                "tenant_id",
                sa.String(64),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("roles", postgresql.ARRAY(sa.Text), server_default="{}"),
            sa.Column("avatar", sa.String(32), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("idx_users_tenant", "users", ["tenant_id"])
        op.create_index("idx_users_keycloak", "users", ["keycloak_id"])

    # APIs table
    if not table_exists("apis"):
        op.create_table(
            "apis",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("category", sa.String(64), nullable=True),
            sa.Column("status", sa.String(32), server_default="active"),
            sa.Column("version", sa.String(32), nullable=True),
            sa.Column(
                "owner_tenant_id",
                sa.String(64),
                sa.ForeignKey("tenants.id"),
                nullable=True,
            ),
            sa.Column("access_type", sa.String(32), server_default="public"),
            sa.Column("allowed_tenants", postgresql.ARRAY(sa.Text), server_default="{}"),
            sa.Column("tags", postgresql.ARRAY(sa.Text), server_default="{}"),
            sa.Column("spec", postgresql.JSONB, nullable=True),
            sa.Column("rate_limit", sa.String(32), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.CheckConstraint(
                "status IN ('active', 'deprecated', 'draft')",
                name="ck_apis_status",
            ),
            sa.CheckConstraint(
                "access_type IN ('public', 'tenant', 'restricted')",
                name="ck_apis_access_type",
            ),
        )
        op.create_index("idx_apis_category", "apis", ["category"])
        op.create_index("idx_apis_status", "apis", ["status"])
        op.create_index("idx_apis_owner", "apis", ["owner_tenant_id"])

    # API Endpoints table
    if not table_exists("api_endpoints"):
        op.create_table(
            "api_endpoints",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column(
                "api_id",
                sa.String(64),
                sa.ForeignKey("apis.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("method", sa.String(16), nullable=False),
            sa.Column("path", sa.String(255), nullable=False),
            sa.Column("description", sa.Text, nullable=True),
            sa.UniqueConstraint("api_id", "method", "path", name="uq_endpoints_api_method_path"),
        )
        op.create_index("idx_endpoints_api", "api_endpoints", ["api_id"])

    # Subscriptions table (may exist from control-plane-api with different schema)
    # We'll use a separate table name to avoid conflicts
    if not table_exists("mcp_subscriptions"):
        op.create_table(
            "mcp_subscriptions",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.id"), nullable=True),
            sa.Column("api_id", sa.String(64), sa.ForeignKey("apis.id"), nullable=True),
            sa.Column("plan", sa.String(64), server_default="free"),
            sa.Column("status", sa.String(32), server_default="active"),
            sa.Column("api_key_hash", sa.String(255), nullable=True),
            sa.Column("denial_reason", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "status IN ('active', 'suspended', 'cancelled', 'denied', 'pending')",
                name="ck_mcp_subscriptions_status",
            ),
        )
        op.create_index("idx_mcp_subs_tenant", "mcp_subscriptions", ["tenant_id"])
        op.create_index("idx_mcp_subs_api", "mcp_subscriptions", ["api_id"])
        op.create_index("idx_mcp_subs_user", "mcp_subscriptions", ["user_id"])
        op.create_index("idx_mcp_subs_status", "mcp_subscriptions", ["status"])

    # Audit Logs table
    if not table_exists("audit_logs"):
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
            sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("user_id", sa.String(64), nullable=True),
            sa.Column("tenant_id", sa.String(64), nullable=True),
            sa.Column("action", sa.String(64), nullable=False),
            sa.Column("resource_type", sa.String(64), nullable=True),
            sa.Column("resource_id", sa.String(64), nullable=True),
            sa.Column("status", sa.String(32), nullable=True),
            sa.Column("details", postgresql.JSONB, nullable=True),
            sa.Column("ip_address", postgresql.INET, nullable=True),
            sa.Column("user_agent", sa.Text, nullable=True),
        )
        op.create_index("idx_audit_timestamp", "audit_logs", [sa.text("timestamp DESC")])
        op.create_index("idx_audit_user", "audit_logs", ["user_id"])
        op.create_index("idx_audit_tenant", "audit_logs", ["tenant_id"])
        op.create_index("idx_audit_action", "audit_logs", ["action"])

    # UAC Contracts table
    if not table_exists("uac_contracts"):
        op.create_table(
            "uac_contracts",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("status", sa.String(32), server_default="active"),
            sa.Column("terms", postgresql.JSONB, nullable=False),
            sa.Column("tenant_ids", postgresql.ARRAY(sa.Text), server_default="{}"),
            sa.Column("api_ids", postgresql.ARRAY(sa.Text), server_default="{}"),
            sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.CheckConstraint(
                "status IN ('active', 'expired', 'pending', 'draft')",
                name="ck_uac_contracts_status",
            ),
        )

    # Create updated_at trigger function (IF NOT EXISTS)
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create triggers for updated_at (drop first to avoid duplicates)
    if table_exists("tenants"):
        op.execute("DROP TRIGGER IF EXISTS tenants_updated_at ON tenants;")
        op.execute("""
            CREATE TRIGGER tenants_updated_at
            BEFORE UPDATE ON tenants
            FOR EACH ROW EXECUTE FUNCTION update_updated_at();
        """)

    if table_exists("apis"):
        op.execute("DROP TRIGGER IF EXISTS apis_updated_at ON apis;")
        op.execute("""
            CREATE TRIGGER apis_updated_at
            BEFORE UPDATE ON apis
            FOR EACH ROW EXECUTE FUNCTION update_updated_at();
        """)

    if table_exists("mcp_subscriptions"):
        op.execute("DROP TRIGGER IF EXISTS mcp_subscriptions_updated_at ON mcp_subscriptions;")
        op.execute("""
            CREATE TRIGGER mcp_subscriptions_updated_at
            BEFORE UPDATE ON mcp_subscriptions
            FOR EACH ROW EXECUTE FUNCTION update_updated_at();
        """)


def downgrade() -> None:
    # Drop triggers
    op.execute("DROP TRIGGER IF EXISTS mcp_subscriptions_updated_at ON mcp_subscriptions;")
    op.execute("DROP TRIGGER IF EXISTS apis_updated_at ON apis;")
    op.execute("DROP TRIGGER IF EXISTS tenants_updated_at ON tenants;")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at();")

    # Drop tables in reverse order of creation (only if they were created by this migration)
    op.drop_table("uac_contracts", if_exists=True)
    op.drop_table("audit_logs", if_exists=True)
    op.drop_table("mcp_subscriptions", if_exists=True)
    op.drop_table("api_endpoints", if_exists=True)
    op.drop_table("apis", if_exists=True)
    op.drop_table("users", if_exists=True)
    op.drop_table("tenants", if_exists=True)
