"""add mTLS certificate fields to consumers table

Revision ID: 020
Revises: 019
Create Date: 2026-02-09

CAB-864 Phase 3: Bulk Client Certificate Onboarding + Registry
- 12 certificate columns on consumers table
- 2 fingerprint indexes for fast lookup
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "020"
down_revision: str | None = "019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add mTLS certificate fields to consumers table."""
    op.add_column("consumers", sa.Column("certificate_fingerprint", sa.String(64), nullable=True))
    op.add_column(
        "consumers",
        sa.Column("certificate_fingerprint_previous", sa.String(64), nullable=True),
    )
    op.add_column(
        "consumers", sa.Column("certificate_subject_dn", sa.String(500), nullable=True)
    )
    op.add_column(
        "consumers", sa.Column("certificate_issuer_dn", sa.String(500), nullable=True)
    )
    op.add_column("consumers", sa.Column("certificate_serial", sa.String(64), nullable=True))
    op.add_column(
        "consumers",
        sa.Column("certificate_not_before", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "consumers",
        sa.Column("certificate_not_after", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("consumers", sa.Column("certificate_pem", sa.Text, nullable=True))
    op.add_column(
        "consumers",
        sa.Column("certificate_status", sa.String(20), nullable=True, server_default="active"),
    )
    op.add_column(
        "consumers",
        sa.Column("previous_cert_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "consumers",
        sa.Column("last_rotated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "consumers",
        sa.Column("rotation_count", sa.Integer, nullable=True, server_default="0"),
    )

    op.create_index("ix_consumers_fingerprint", "consumers", ["certificate_fingerprint"])
    op.create_index(
        "ix_consumers_fingerprint_prev", "consumers", ["certificate_fingerprint_previous"]
    )


def downgrade() -> None:
    """Remove mTLS certificate fields from consumers table."""
    op.drop_index("ix_consumers_fingerprint_prev", table_name="consumers")
    op.drop_index("ix_consumers_fingerprint", table_name="consumers")

    op.drop_column("consumers", "rotation_count")
    op.drop_column("consumers", "last_rotated_at")
    op.drop_column("consumers", "previous_cert_expires_at")
    op.drop_column("consumers", "certificate_status")
    op.drop_column("consumers", "certificate_pem")
    op.drop_column("consumers", "certificate_not_after")
    op.drop_column("consumers", "certificate_not_before")
    op.drop_column("consumers", "certificate_serial")
    op.drop_column("consumers", "certificate_issuer_dn")
    op.drop_column("consumers", "certificate_subject_dn")
    op.drop_column("consumers", "certificate_fingerprint_previous")
    op.drop_column("consumers", "certificate_fingerprint")
