"""Add portal_applications table for persistent app management (CAB-1306)

Revision ID: 029
Revises: 028
Create Date: 2026-02-17
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    portal_app_status = postgresql.ENUM("active", "suspended", name="portal_app_status_enum", create_type=False)
    portal_app_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "portal_applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.String(255), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(255), nullable=True, index=True),
        sa.Column("keycloak_client_id", sa.String(255), nullable=True),
        sa.Column("keycloak_client_uuid", sa.String(255), nullable=True),
        sa.Column(
            "status",
            portal_app_status,
            nullable=False,
            server_default="active",
        ),
        sa.Column("redirect_uris", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_index("ix_portal_apps_owner_name", "portal_applications", ["owner_id", "name"], unique=True)
    op.create_index("ix_portal_apps_owner_status", "portal_applications", ["owner_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_portal_apps_owner_status", table_name="portal_applications")
    op.drop_index("ix_portal_apps_owner_name", table_name="portal_applications")
    op.drop_table("portal_applications")

    portal_app_status = postgresql.ENUM("active", "suspended", name="portal_app_status_enum", create_type=False)
    portal_app_status.drop(op.get_bind(), checkfirst=True)
