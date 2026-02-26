"""Create oauth_clients table (CAB-1483)

Revision ID: 045
Revises: 044
Create Date: 2026-02-26
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "045"
down_revision = "044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oauth_clients",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("keycloak_client_id", sa.String(255), nullable=False, unique=True),
        sa.Column("keycloak_uuid", sa.String(36), nullable=True),
        sa.Column("client_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("product_roles", JSONB, nullable=True),
        sa.Column("oauth_metadata", JSONB, nullable=True),
        sa.Column("vault_secret_path", sa.String(512), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_oauth_client_tenant", "oauth_clients", ["tenant_id"])
    op.create_index("idx_oauth_client_status", "oauth_clients", ["status"])
    op.create_index("idx_oauth_client_kc_client_id", "oauth_clients", ["keycloak_client_id"])


def downgrade() -> None:
    op.drop_index("idx_oauth_client_kc_client_id", table_name="oauth_clients")
    op.drop_index("idx_oauth_client_status", table_name="oauth_clients")
    op.drop_index("idx_oauth_client_tenant", table_name="oauth_clients")
    op.drop_table("oauth_clients")
