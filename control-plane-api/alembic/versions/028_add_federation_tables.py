"""Add federation tables for enterprise MCP multi-account orchestration

Revision ID: 028
Revises: 027
Create Date: 2026-02-17
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enums
    master_status = postgresql.ENUM(
        "active", "suspended", "disabled", name="master_account_status_enum", create_type=False
    )
    sub_type = postgresql.ENUM("developer", "agent", name="sub_account_type_enum", create_type=False)
    sub_status = postgresql.ENUM("active", "suspended", "revoked", name="sub_account_status_enum", create_type=False)

    master_status.create(op.get_bind(), checkfirst=True)
    sub_type.create(op.get_bind(), checkfirst=True)
    sub_status.create(op.get_bind(), checkfirst=True)

    # master_accounts
    op.create_table(
        "master_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", master_status, nullable=False, server_default="active"),
        sa.Column("max_sub_accounts", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("quota_config", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.String(255), nullable=True),
    )
    op.create_index("ix_master_accounts_tenant_id", "master_accounts", ["tenant_id"])
    op.create_index("ix_master_accounts_tenant_name", "master_accounts", ["tenant_id", "name"], unique=True)
    op.create_index("ix_master_accounts_tenant_status", "master_accounts", ["tenant_id", "status"])

    # sub_accounts
    op.create_table(
        "sub_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "master_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("master_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("account_type", sub_type, nullable=False, server_default="developer"),
        sa.Column("status", sub_status, nullable=False, server_default="active"),
        sa.Column("api_key_hash", sa.String(512), nullable=True),
        sa.Column("api_key_prefix", sa.String(20), nullable=True),
        sa.Column("kc_client_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.String(255), nullable=True),
    )
    op.create_index("ix_sub_accounts_master_account_id", "sub_accounts", ["master_account_id"])
    op.create_index("ix_sub_accounts_tenant_id", "sub_accounts", ["tenant_id"])
    op.create_index("ix_sub_accounts_master_name", "sub_accounts", ["master_account_id", "name"], unique=True)
    op.create_index("ix_sub_accounts_tenant_status", "sub_accounts", ["tenant_id", "status"])
    op.create_index("ix_sub_accounts_key_prefix", "sub_accounts", ["api_key_prefix"])

    # sub_account_tools
    op.create_table(
        "sub_account_tools",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "sub_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sub_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tool_name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_sub_account_tools_sub_account_id", "sub_account_tools", ["sub_account_id"])
    op.create_index("ix_sub_account_tools_unique", "sub_account_tools", ["sub_account_id", "tool_name"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_sub_account_tools_unique", table_name="sub_account_tools")
    op.drop_index("ix_sub_account_tools_sub_account_id", table_name="sub_account_tools")
    op.drop_table("sub_account_tools")

    op.drop_index("ix_sub_accounts_key_prefix", table_name="sub_accounts")
    op.drop_index("ix_sub_accounts_tenant_status", table_name="sub_accounts")
    op.drop_index("ix_sub_accounts_master_name", table_name="sub_accounts")
    op.drop_index("ix_sub_accounts_tenant_id", table_name="sub_accounts")
    op.drop_index("ix_sub_accounts_master_account_id", table_name="sub_accounts")
    op.drop_table("sub_accounts")

    op.drop_index("ix_master_accounts_tenant_status", table_name="master_accounts")
    op.drop_index("ix_master_accounts_tenant_name", table_name="master_accounts")
    op.drop_index("ix_master_accounts_tenant_id", table_name="master_accounts")
    op.drop_table("master_accounts")

    op.execute("DROP TYPE IF EXISTS sub_account_status_enum")
    op.execute("DROP TYPE IF EXISTS sub_account_type_enum")
    op.execute("DROP TYPE IF EXISTS master_account_status_enum")
