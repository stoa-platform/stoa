"""Create tenant_cas table for per-tenant CA keypairs (CAB-1787)

Revision ID: 064
Revises: 063
Create Date: 2026-03-12
"""

import sqlalchemy as sa
from alembic import op

revision = "064"
down_revision = "063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_cas",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(64),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("ca_certificate_pem", sa.Text, nullable=False),
        sa.Column("encrypted_private_key", sa.Text, nullable=False),
        sa.Column("subject_dn", sa.String(500), nullable=False),
        sa.Column("serial_number", sa.String(128), nullable=False),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=False),
        sa.Column("not_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("key_algorithm", sa.String(32), nullable=False, server_default="RSA-4096"),
        sa.Column("fingerprint_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_tenant_cas_tenant_id", "tenant_cas", ["tenant_id"])
    op.create_index("ix_tenant_cas_status", "tenant_cas", ["status"])


def downgrade() -> None:
    op.drop_index("ix_tenant_cas_status", table_name="tenant_cas")
    op.drop_index("ix_tenant_cas_tenant_id", table_name="tenant_cas")
    op.drop_table("tenant_cas")
