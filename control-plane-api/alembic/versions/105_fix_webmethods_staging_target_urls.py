"""fix webMethods staging target urls

Revision ID: 105_fix_webmethods_staging_target_urls
Revises: 104_gateway_external_urls
Create Date: 2026-05-02

Staging webMethods has two external surfaces:

* ``staging-wm.gostoa.dev`` reaches the third-party webMethods gateway.
* ``staging-wm-k3s.gostoa.dev`` reaches the STOA remote-link runtime.

The target gateway URL must identify the third-party gateway, otherwise a
rebuild can make staging Link/Connect point back to the K3s STOA link.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "105_fix_webmethods_staging_target_urls"
down_revision: str | tuple[str, ...] | None = "104_gateway_external_urls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WEBMETHODS_STAGING_URL_FIXES = (
    (
        "connect-webmethods-staging",
        "staging",
        "https://staging-wm.gostoa.dev",
        "https://staging-wm.gostoa.dev",
    ),
    (
        "connect-webmethods-staging-connect-staging",
        "staging",
        "https://staging-wm.gostoa.dev",
        "https://staging-wm.gostoa.dev",
    ),
    (
        "stoa-link-wm-staging",
        "staging",
        "https://staging-wm-k3s.gostoa.dev",
        "https://staging-wm.gostoa.dev",
    ),
    (
        "stoa-link-wm-staging-sidecar-staging",
        "staging",
        "https://staging-wm-k3s.gostoa.dev",
        "https://staging-wm.gostoa.dev",
    ),
)


def upgrade() -> None:
    conn = op.get_bind()
    for name, environment, public_url, target_gateway_url in _WEBMETHODS_STAGING_URL_FIXES:
        conn.execute(
            sa.text("""
                UPDATE gateway_instances
                SET
                  public_url = :public_url,
                  target_gateway_url = :target_gateway_url,
                  endpoints = jsonb_strip_nulls(
                    (
                      COALESCE(endpoints, '{}'::jsonb)
                      - 'publicUrl' - 'public' - 'runtime_url' - 'runtimeUrl'
                      - 'external_url' - 'externalUrl'
                      - 'targetGatewayUrl' - 'target_url' - 'targetUrl'
                    )
                    || jsonb_build_object(
                      'public_url', :public_url,
                      'target_gateway_url', :target_gateway_url
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
            },
        )


def downgrade() -> None:
    # Data repair only. Previous values were inconsistent across rebuild paths.
    pass
