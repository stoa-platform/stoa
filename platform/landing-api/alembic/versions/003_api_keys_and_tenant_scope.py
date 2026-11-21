"""Scope invites to a tenant and store only secret hashes.

Downgrade is refused: the original invite tokens cannot be rebuilt from
their hashes, so rolling back would not restore working invite links.

Revision ID: 003
Revises: 002
Create Date: 2026-11-02
"""

import hashlib
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "invites",
        sa.Column("tenant_id", sa.String(length=128), nullable=True),
        schema="stoa",
    )
    op.execute("UPDATE stoa.invites SET tenant_id = 'legacy' WHERE tenant_id IS NULL")
    op.alter_column("invites", "tenant_id", nullable=False, schema="stoa")
    op.create_index("idx_invites_tenant", "invites", ["tenant_id"], schema="stoa")

    op.add_column(
        "invites",
        sa.Column("token_hash", sa.String(length=64), nullable=True),
        schema="stoa",
    )
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, token FROM stoa.invites")).fetchall()
    for row in rows:
        digest = hashlib.sha256(row.token.encode("utf-8")).hexdigest()
        bind.execute(
            sa.text("UPDATE stoa.invites SET token_hash = :digest WHERE id = :invite_id"),
            {"digest": digest, "invite_id": row.id},
        )
    op.alter_column("invites", "token_hash", nullable=False, schema="stoa")
    op.execute("DROP INDEX IF EXISTS stoa.ix_invites_token")
    op.execute("ALTER TABLE stoa.invites DROP CONSTRAINT IF EXISTS uq_invites_token")
    op.drop_column("invites", "token", schema="stoa")
    op.create_index(
        "uq_invites_token_hash",
        "invites",
        ["token_hash"],
        unique=True,
        schema="stoa",
    )

    op.create_table(
        "api_keys",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("key_prefix", sa.String(length=16), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_keys")),
        schema="stoa",
    )
    op.create_index(
        "uq_api_keys_key_hash",
        "api_keys",
        ["key_hash"],
        unique=True,
        schema="stoa",
    )
    op.create_index("idx_api_keys_tenant", "api_keys", ["tenant_id"], schema="stoa")


def downgrade() -> None:
    raise RuntimeError(
        "Revision 003 cannot be downgraded: invite tokens are stored only as "
        "hashes, and the original invite links cannot be restored."
    )
