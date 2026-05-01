"""runtime target reconciliation backfill

Revision ID: 102_runtime_target_reconciliation
Revises: 101_seed_portal_subscription_plans
Create Date: 2026-05-01

Backfills api_gateway_assignments from explicit catalog/runtime target state
and expires old pending GatewayDeployment rows that predate the runtime
acknowledgement contract.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "102_runtime_target_reconciliation"
down_revision: str | tuple[str, ...] | None = "101_seed_portal_subscription_plans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()

    # Existing catalog rows already carry explicit target_gateways. Materialize
    # those as default auto-deploy assignments so promotion and Git boolean env
    # markers can resolve concrete runtime targets without guessing.
    conn.execute(
        sa.text("""
            INSERT INTO api_gateway_assignments (id, api_id, gateway_id, environment, auto_deploy, created_at)
            SELECT gen_random_uuid(), ac.id, gi.id, gi.environment, true, NOW()
            FROM api_catalog ac
            JOIN LATERAL jsonb_array_elements_text(COALESCE(ac.target_gateways, '[]'::jsonb)) AS t(gateway_name)
                ON true
            JOIN gateway_instances gi
                ON gi.name = t.gateway_name
               AND gi.deleted_at IS NULL
               AND gi.enabled IS TRUE
            WHERE ac.deleted_at IS NULL
            ON CONFLICT ON CONSTRAINT uq_api_gateway_env
            DO UPDATE SET auto_deploy = EXCLUDED.auto_deploy
        """)
    )

    # Preserve assignments for runtime deployments that already converged or are
    # still waiting for an agent ack. This turns the observed runtime target into
    # an explicit contract for subsequent promotions.
    conn.execute(
        sa.text("""
            INSERT INTO api_gateway_assignments (id, api_id, gateway_id, environment, auto_deploy, created_at)
            SELECT DISTINCT gen_random_uuid(), gd.api_catalog_id, gi.id, gi.environment, true, NOW()
            FROM gateway_deployments gd
            JOIN gateway_instances gi
                ON gi.id = gd.gateway_instance_id
               AND gi.deleted_at IS NULL
               AND gi.enabled IS TRUE
            WHERE gd.sync_status IN ('synced', 'pending', 'syncing')
            ON CONFLICT ON CONSTRAINT uq_api_gateway_env
            DO UPDATE SET auto_deploy = EXCLUDED.auto_deploy
        """)
    )

    # Stop retrying deployments whose target gateway has been archived. They
    # must be explicitly redeployed to an active gateway target.
    conn.execute(
        sa.text("""
            UPDATE gateway_deployments gd
            SET sync_status = 'error',
                sync_error = 'Gateway instance is archived or missing; select an active gateway target and redeploy',
                sync_attempts = GREATEST(sync_attempts, 3),
                updated_at = NOW()
            WHERE EXISTS (
                SELECT 1
                FROM gateway_instances gi
                WHERE gi.id = gd.gateway_instance_id
                  AND gi.deleted_at IS NOT NULL
            )
        """)
    )

    # Old pending rows from before the ack timeout contract are not meaningful
    # in the Console. Mark them as failed so they can be force-synced or
    # redeployed intentionally.
    conn.execute(
        sa.text("""
            UPDATE gateway_deployments
            SET sync_status = 'error',
                sync_error = 'Gateway did not acknowledge deployment within 86400 seconds; force sync or redeploy',
                sync_attempts = GREATEST(sync_attempts, 3),
                updated_at = NOW()
            WHERE sync_status IN ('pending', 'syncing')
              AND COALESCE(last_sync_attempt, desired_at, created_at) < NOW() - INTERVAL '24 hours'
        """)
    )


def downgrade() -> None:
    # Data backfill is intentionally not reversed: assignments may have been
    # edited by users after upgrade, and failed/pending runtime status is
    # operational state.
    pass
