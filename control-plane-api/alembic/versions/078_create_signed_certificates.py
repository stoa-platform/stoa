"""Create signed_certificates table for certificate lifecycle tracking.

Revision ID: 078
Revises: 077
Create Date: 2026-03-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "078"
down_revision = "077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signed_certificates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "ca_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant_cas.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "consumer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("consumers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("subject_dn", sa.String(500), nullable=False),
        sa.Column("issuer_dn", sa.String(500), nullable=False),
        sa.Column("serial_number", sa.String(128), nullable=False),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=False),
        sa.Column("not_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("key_algorithm", sa.String(32), server_default="RSA-4096", nullable=False),
        sa.Column("fingerprint_sha256", sa.String(64), unique=True, nullable=False),
        sa.Column("certificate_pem", sa.Text, nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_signed_certs_tenant_id", "signed_certificates", ["tenant_id"])
    op.create_index("ix_signed_certs_ca_id", "signed_certificates", ["ca_id"])
    op.create_index("ix_signed_certs_consumer_id", "signed_certificates", ["consumer_id"])
    op.create_index("ix_signed_certs_status", "signed_certificates", ["status"])
    op.create_index("ix_signed_certs_fingerprint", "signed_certificates", ["fingerprint_sha256"])
    op.create_index("ix_signed_certs_not_after", "signed_certificates", ["not_after"])


def downgrade() -> None:
    op.drop_index("ix_signed_certs_not_after")
    op.drop_index("ix_signed_certs_fingerprint")
    op.drop_index("ix_signed_certs_status")
    op.drop_index("ix_signed_certs_consumer_id")
    op.drop_index("ix_signed_certs_ca_id")
    op.drop_index("ix_signed_certs_tenant_id")
    op.drop_table("signed_certificates")
