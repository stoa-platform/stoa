"""Enforce API uniqueness on (tenant_id, api_name, version) with slug api_id (CAB-1938)

- Drop old unique index on (tenant_id, api_id)
- Backfill api_name and version for existing rows
- Add partial unique index on (tenant_id, api_name, version) WHERE deleted_at IS NULL
- Add partial unique index on (tenant_id, api_id) WHERE deleted_at IS NULL
- Make api_name and version NOT NULL

Revision ID: 084
Revises: 083
"""

import sqlalchemy as sa
from alembic import op

revision = "084"
down_revision = "083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Backfill NULLs before adding NOT NULL constraints
    op.execute("UPDATE api_catalog SET api_name = api_id WHERE api_name IS NULL")
    op.execute("UPDATE api_catalog SET version = '1.0.0' WHERE version IS NULL")

    # 2. Drop old unique index (tenant_id, api_id) — no partial, blocks soft-delete reuse
    op.drop_index("ix_api_catalog_tenant_api", table_name="api_catalog")

    # 3. Add partial unique index on (tenant_id, api_name, version) for active APIs only
    op.execute(
        """
        CREATE UNIQUE INDEX ix_api_catalog_tenant_name_version
        ON api_catalog (tenant_id, api_name, version)
        WHERE deleted_at IS NULL
        """
    )

    # 4. Add partial unique index on (tenant_id, api_id) for URL routing integrity
    op.execute(
        """
        CREATE UNIQUE INDEX ix_api_catalog_tenant_api_active
        ON api_catalog (tenant_id, api_id)
        WHERE deleted_at IS NULL
        """
    )

    # 5. Make api_name and version NOT NULL
    op.alter_column(
        "api_catalog", "api_name",
        existing_type=sa.String(255),
        nullable=False,
    )
    op.alter_column(
        "api_catalog", "version",
        existing_type=sa.String(50),
        nullable=False,
        server_default="1.0.0",
    )


def downgrade() -> None:
    # Reverse NOT NULL
    op.alter_column(
        "api_catalog", "version",
        existing_type=sa.String(50),
        nullable=True,
        server_default=None,
    )
    op.alter_column(
        "api_catalog", "api_name",
        existing_type=sa.String(255),
        nullable=True,
    )

    # Drop new indexes
    op.drop_index("ix_api_catalog_tenant_api_active", table_name="api_catalog")
    op.drop_index("ix_api_catalog_tenant_name_version", table_name="api_catalog")

    # Restore old unique index
    op.create_index(
        "ix_api_catalog_tenant_api", "api_catalog",
        ["tenant_id", "api_id"], unique=True,
    )
