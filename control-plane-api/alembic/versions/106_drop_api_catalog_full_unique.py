"""drop obsolete api_catalog full unique constraint

Revision ID: 106_drop_api_catalog_full_unique
Revises: 105_fix_webmethods_staging_target_urls
Create Date: 2026-05-02

Migration 084 introduced the active-row-only uniqueness contract:

* ``ix_api_catalog_tenant_name_version`` for ``(tenant_id, api_name, version)``
  where ``deleted_at IS NULL``
* ``ix_api_catalog_tenant_api_active`` for ``(tenant_id, api_id)`` where
  ``deleted_at IS NULL``

The original table constraint from migration 009 still exists in long-lived
prod databases as ``uq_api_catalog_tenant_api``. Because it includes
soft-deleted rows, a deleted canonical Git slug can block the reconciler from
adopting a legacy UUID row back to the Git identity.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "106_drop_api_catalog_full_unique"
down_revision: str | tuple[str, ...] | None = "105_fix_webmethods_staging_target_urls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'uq_api_catalog_tenant_api'
                  AND conrelid = 'api_catalog'::regclass
            ) THEN
                ALTER TABLE api_catalog DROP CONSTRAINT uq_api_catalog_tenant_api;
            END IF;
        END
        $$;
        """
    )
    op.execute("DROP INDEX IF EXISTS uq_api_catalog_tenant_api")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_api_catalog_tenant_api_active
        ON api_catalog (tenant_id, api_id)
        WHERE deleted_at IS NULL
        """
    )


def downgrade() -> None:
    # Do not recreate the old full-table uniqueness constraint. It violates
    # the soft-delete contract and can fail on legitimate historical rows.
    pass
