"""Create clients table for mTLS certificate provisioning (CAB-865)

Revision ID: 013
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("certificate_cn", sa.String(255), nullable=False),
        sa.Column("certificate_serial", sa.String(255), nullable=True),
        sa.Column("certificate_fingerprint", sa.String(255), nullable=True),
        sa.Column("certificate_pem", sa.Text(), nullable=True),
        sa.Column("certificate_not_before", sa.DateTime(timezone=True), nullable=True),
        sa.Column("certificate_not_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "revoked", "expired", name="clientstatus"),
            nullable=False,
            server_default="active",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_clients_tenant_id", "clients", ["tenant_id"])
    op.create_index("ix_clients_tenant_cn", "clients", ["tenant_id", "certificate_cn"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_clients_tenant_cn")
    op.drop_index("ix_clients_tenant_id")
    op.drop_table("clients")
    op.execute("DROP TYPE IF EXISTS clientstatus")
