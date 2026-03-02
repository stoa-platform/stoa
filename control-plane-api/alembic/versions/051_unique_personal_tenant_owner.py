"""Add unique index on personal tenant owner to prevent duplicates.

Race condition in POST /v1/me/tenant allowed concurrent requests to create
multiple personal tenants for the same user. This migration:
1. Deduplicates existing personal tenants (keeps oldest, archives others)
2. Adds a partial unique index on settings->>'owner_user_id' for personal tenants

Revision ID: 051_unique_personal_tenant_owner
Revises: 050_llm_spend_events
Create Date: 2026-03-02
"""

from alembic import op

revision = "051_unique_personal_tenant_owner"
down_revision = "050_llm_spend_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: Archive duplicate personal tenants (keep the oldest per owner)
    op.execute("""
        UPDATE tenants
        SET status = 'archived'
        WHERE id IN (
            SELECT t.id
            FROM tenants t
            INNER JOIN (
                SELECT settings->>'owner_user_id' AS owner_id,
                       MIN(created_at) AS first_created
                FROM tenants
                WHERE settings->>'personal' = 'true'
                  AND status != 'archived'
                  AND settings->>'owner_user_id' IS NOT NULL
                GROUP BY settings->>'owner_user_id'
                HAVING COUNT(*) > 1
            ) dups ON t.settings->>'owner_user_id' = dups.owner_id
                  AND t.created_at > dups.first_created
            WHERE t.settings->>'personal' = 'true'
              AND t.status != 'archived'
        )
    """)

    # Step 2: Add partial unique index (only for active/suspended personal tenants)
    op.execute("""
        CREATE UNIQUE INDEX ix_tenants_personal_owner_unique
        ON tenants ((settings->>'owner_user_id'))
        WHERE settings->>'personal' = 'true'
          AND status != 'archived'
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tenants_personal_owner_unique")
