"""cleanup phantom gateway instances (ADR-059)

Revision ID: 083_cleanup_phantom_instances
Revises: 082_add_target_gateway_url
Create Date: 2026-03-30

Soft-deletes gateway instances that were created manually or by legacy
import and have no active deployments. These phantom instances cause
push-sync failures when the CP tries to reach non-resolvable hostnames.

ADR-059 moves to a pull/SSE model where only self-registered instances
(from STOA Link/Connect agents) are valid deployment targets.

This migration is safe to run: it only marks `deleted_at` on instances
that have zero gateway_deployments records. No data is hard-deleted.
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "083_cleanup_phantom_instances"
down_revision: str | None = "082_add_target_gateway_url"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Soft-delete gateway instances where:
    # 1. source is NOT 'self_register' (manually created or imported)
    # 2. already not soft-deleted (deleted_at IS NULL)
    # 3. have NO active gateway_deployments
    conn = op.get_bind()

    # Find phantom instances with no deployments
    result = conn.execute(
        sa.text("""
            UPDATE gateway_instances
            SET deleted_at = :now
            WHERE source != 'self_register'
              AND deleted_at IS NULL
              AND id NOT IN (
                  SELECT DISTINCT gateway_instance_id
                  FROM gateway_deployments
                  WHERE sync_status != 'DELETING'
              )
        """),
        {"now": datetime.now(UTC)},
    )
    print(f"ADR-059: soft-deleted {result.rowcount} phantom gateway instances")


def downgrade() -> None:
    # Restore soft-deleted phantom instances (undo the cleanup)
    conn = op.get_bind()
    conn.execute(sa.text("""
            UPDATE gateway_instances
            SET deleted_at = NULL
            WHERE source != 'self_register'
              AND deleted_at IS NOT NULL
        """))
