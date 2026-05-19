"""Add audit emit idempotency store (CAB-2227)."""

import sqlalchemy as sa
from alembic import op

revision = "108_audit_emit_idempotency"
down_revision = "107_audit_immutability_pseudonymization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_emit_idempotency",
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("audit_emit_idempotency")
