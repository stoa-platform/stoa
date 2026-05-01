"""route sync ack consistency repair

Revision ID: 103_route_sync_ack_consistency
Revises: 102_runtime_target_reconciliation
Create Date: 2026-05-01

Repairs GatewayDeployment rows that were marked synced even though their
stored route-sync step trace contains a failed step.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "103_route_sync_ack_consistency"
down_revision: str | tuple[str, ...] | None = "102_runtime_target_reconciliation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text("""
            UPDATE gateway_deployments gd
            SET sync_status = 'error',
                sync_error = COALESCE(
                    (
                        SELECT NULLIF(step ->> 'detail', '')
                        FROM jsonb_array_elements(COALESCE(gd.sync_steps, '[]'::jsonb)) AS step
                        WHERE step ->> 'status' = 'failed'
                        LIMIT 1
                    ),
                    'Gateway ack contained a failed sync step while deployment was marked synced'
                ),
                updated_at = NOW()
            WHERE gd.sync_status = 'synced'
              AND EXISTS (
                  SELECT 1
                  FROM jsonb_array_elements(COALESCE(gd.sync_steps, '[]'::jsonb)) AS step
                  WHERE step ->> 'status' = 'failed'
              )
        """)
    )


def downgrade() -> None:
    # Data repair is intentionally not reversible: previous "synced" rows were
    # internally contradictory and cannot be reconstructed safely.
    pass
