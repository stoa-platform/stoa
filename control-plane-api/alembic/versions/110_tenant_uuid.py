"""Give each tenant a stable UUID so a recreated slug carries a new identity."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "110_tenant_uuid"
down_revision = "109_tool_policy_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Adding the column with a volatile default gives every existing row its own value.
    # gen_random_uuid() is built into PostgreSQL 13+, so no extension is needed. The
    # default stays in place so raw SQL seeds that omit the column keep working; the
    # ORM fills the column itself.
    op.add_column(
        "tenants",
        sa.Column("uuid", UUID(as_uuid=True), nullable=True, server_default=sa.text("gen_random_uuid()")),
    )
    op.alter_column("tenants", "uuid", nullable=False)
    op.create_index("ix_tenants_uuid", "tenants", ["uuid"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_tenants_uuid", table_name="tenants")
    op.drop_column("tenants", "uuid")
