"""Reset incorrectly offline external gateways back to online.

Kong prod, webMethods prod, and webMethods dev were marked OFFLINE by the
health worker because the K8s pod cannot reach external VPS IPs. The worker
now skips OFFLINE transition for gateways that were never reachable
(last_health_check IS NULL). This migration resets them to their seeded status.

Revision ID: 066
Revises: 065
Create Date: 2026-03-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "066_reset_offline_external_gateways"
down_revision: Union[str, None] = "065_mcp_server_environment_gateway"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Gateways that were seeded as online but incorrectly marked offline
_GATEWAY_NAMES = ["kong-prod", "webmethods-prod", "webmethods-dev"]


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("""
            UPDATE gateway_instances
            SET status = 'online',
                health_details = '{}'::jsonb,
                updated_at = NOW()
            WHERE name = ANY(:names)
              AND status = 'offline'
              AND last_health_check IS NULL
              AND deleted_at IS NULL
        """),
        {"names": _GATEWAY_NAMES},
    )


def downgrade() -> None:
    # No-op: we don't want to re-mark them as offline
    pass
