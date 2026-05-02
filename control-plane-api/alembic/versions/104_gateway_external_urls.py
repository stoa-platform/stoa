"""backfill third-party gateway external urls

Revision ID: 104_gateway_external_urls
Revises: 103_route_sync_ack_consistency
Create Date: 2026-05-02

Backfills public, target, and UI URLs for third-party gateway instances whose
deployment source already supports explicit registration metadata.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "104_gateway_external_urls"
down_revision: str | tuple[str, ...] | None = "103_route_sync_ack_consistency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_URL_BACKFILLS = (
    (
        "connect-webmethods-dev-connect-dev",
        "dev",
        "https://dev-wm.gostoa.dev",
        "https://dev-wm.gostoa.dev",
        "https://dev-wm-ui.gostoa.dev",
    ),
    (
        "stoa-link-wm-dev-sidecar-dev",
        "dev",
        "https://dev-wm-k3s.gostoa.dev",
        "https://dev-wm.gostoa.dev",
        "https://dev-wm-ui.gostoa.dev",
    ),
    (
        "connect-webmethods-staging-connect-staging",
        "staging",
        "https://staging-wm.gostoa.dev",
        "https://staging-wm.gostoa.dev",
        "https://staging-wm-ui.gostoa.dev",
    ),
    (
        "stoa-link-wm-staging-sidecar-staging",
        "staging",
        "https://staging-wm-k3s.gostoa.dev",
        "https://staging-wm.gostoa.dev",
        "https://staging-wm-ui.gostoa.dev",
    ),
    (
        "connect-webmethods-connect-prod",
        "prod",
        "https://vps-wm.gostoa.dev",
        "https://vps-wm.gostoa.dev",
        "https://vps-wm-ui.gostoa.dev",
    ),
    (
        "connect-webmethods-connect-production",
        "production",
        "https://vps-wm.gostoa.dev",
        "https://vps-wm.gostoa.dev",
        "https://vps-wm-ui.gostoa.dev",
    ),
    (
        "vps-wm-link-prod-sidecar-prod",
        "prod",
        "https://vps-wm-link.gostoa.dev",
        "https://vps-wm.gostoa.dev",
        "https://vps-wm-ui.gostoa.dev",
    ),
    (
        "webmethods-stoa-link-sidecar-prod",
        "prod",
        "https://vps-wm-link.gostoa.dev",
        "https://vps-wm.gostoa.dev",
        "https://vps-wm-ui.gostoa.dev",
    ),
    (
        "kong-stoa-link-sidecar-prod",
        "prod",
        "https://kong.gostoa.dev",
        "https://kong-admin.gostoa.dev",
        "https://kong-ui.gostoa.dev",
    ),
    (
        "connect-kong-connect-production",
        "production",
        "https://kong.gostoa.dev",
        "https://kong-admin.gostoa.dev",
        "https://kong-ui.gostoa.dev",
    ),
    (
        "gravitee-stoa-link-sidecar-prod",
        "prod",
        "https://gravitee.gostoa.dev",
        "https://gravitee-ui.gostoa.dev/management",
        "https://gravitee-ui.gostoa.dev/console/",
    ),
    (
        "agentgateway-stoa-link-sidecar-prod",
        "prod",
        "https://agentgateway.gostoa.dev",
        "https://agentgateway-ui.gostoa.dev",
        "https://agentgateway-ui.gostoa.dev/ui/",
    ),
)


def upgrade() -> None:
    conn = op.get_bind()
    for name, environment, public_url, target_gateway_url, ui_url in _URL_BACKFILLS:
        conn.execute(
            sa.text("""
                UPDATE gateway_instances
                SET
                  public_url = :public_url,
                  target_gateway_url = :target_gateway_url,
                  ui_url = :ui_url,
                  endpoints = jsonb_strip_nulls(
                    (
                      COALESCE(endpoints, '{}'::jsonb)
                      - 'publicUrl' - 'public' - 'runtime_url' - 'runtimeUrl'
                      - 'external_url' - 'externalUrl'
                      - 'uiUrl' - 'console_url' - 'consoleUrl' - 'web_ui_url' - 'webUiUrl'
                      - 'targetGatewayUrl' - 'target_url' - 'targetUrl'
                    )
                    || jsonb_build_object(
                      'public_url', :public_url,
                      'target_gateway_url', :target_gateway_url,
                      'ui_url', :ui_url
                    )
                  ),
                  updated_at = NOW()
                WHERE name = :name
                  AND environment = :environment
                  AND deleted_at IS NULL
            """),
            {
                "name": name,
                "environment": environment,
                "public_url": public_url,
                "target_gateway_url": target_gateway_url,
                "ui_url": ui_url,
            },
        )


def downgrade() -> None:
    # Data repair only. The previous values cannot be reconstructed reliably
    # because some rows were null while others had stale prod webMethods URLs.
    pass
