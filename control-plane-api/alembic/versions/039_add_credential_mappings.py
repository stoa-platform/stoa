"""Add credential_mappings table (CAB-1432).

Revision ID: 039
Revises: 038
Create Date: 2026-02-23

Maps consumer OAuth2 identities to backend API credentials.
One credential per consumer per API (unique constraint).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "039"
down_revision: str | None = "038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create enum type
    auth_type_enum = postgresql.ENUM("api_key", "bearer", "basic", name="credential_auth_type", create_type=False)
    auth_type_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "credential_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("consumer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("api_id", sa.String(255), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column(
            "auth_type",
            auth_type_enum,
            nullable=False,
        ),
        sa.Column("header_name", sa.String(255), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.String(255), nullable=True),
    )

    # Unique constraint: one credential per consumer per API
    op.create_unique_constraint(
        "uq_credential_mappings_consumer_api",
        "credential_mappings",
        ["consumer_id", "api_id"],
    )

    # Indexes for common queries
    op.create_index("ix_credential_mappings_consumer_id", "credential_mappings", ["consumer_id"])
    op.create_index("ix_credential_mappings_api_id", "credential_mappings", ["api_id"])
    op.create_index("ix_credential_mappings_tenant_id", "credential_mappings", ["tenant_id"])
    op.create_index(
        "ix_credential_mappings_consumer_api_active",
        "credential_mappings",
        ["consumer_id", "api_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_credential_mappings_consumer_api_active", table_name="credential_mappings")
    op.drop_index("ix_credential_mappings_tenant_id", table_name="credential_mappings")
    op.drop_index("ix_credential_mappings_api_id", table_name="credential_mappings")
    op.drop_index("ix_credential_mappings_consumer_id", table_name="credential_mappings")
    op.drop_constraint("uq_credential_mappings_consumer_api", "credential_mappings", type_="unique")
    op.drop_table("credential_mappings")

    # Drop enum type
    postgresql.ENUM(name="credential_auth_type").drop(op.get_bind(), checkfirst=True)
