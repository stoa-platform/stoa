"""040 — Create chat_token_usage table (CAB-288).

Revision ID: 040
Revises: 039b
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "040"
down_revision = "039b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_token_usage",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.String(100), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("period_date", sa.Date(), nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("total_tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("request_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            "model",
            "period_date",
            name="uq_chat_token_usage_tenant_user_model_date",
        ),
    )
    op.create_index(
        "ix_chat_token_usage_tenant_date",
        "chat_token_usage",
        ["tenant_id", "period_date"],
    )
    op.create_index(
        "ix_chat_token_usage_tenant_user_date",
        "chat_token_usage",
        ["tenant_id", "user_id", "period_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_token_usage_tenant_user_date", table_name="chat_token_usage")
    op.drop_index("ix_chat_token_usage_tenant_date", table_name="chat_token_usage")
    op.drop_table("chat_token_usage")
