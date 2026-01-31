"""Add certificate rotation fields (CAB-869)

Revision ID: 014
Revises: 013
"""
from alembic import op
import sqlalchemy as sa

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("certificate_fingerprint_previous", sa.String(255), nullable=True))
    op.add_column("clients", sa.Column("previous_cert_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("clients", sa.Column("last_rotated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("clients", sa.Column("rotation_count", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column("clients", "rotation_count")
    op.drop_column("clients", "last_rotated_at")
    op.drop_column("clients", "previous_cert_expires_at")
    op.drop_column("clients", "certificate_fingerprint_previous")
