"""fix non-prod webMethods gateway urls

Revision ID: 100_fix_webmethods_nonprod_urls
Revises: 099_catalog_release_versioning
Create Date: 2026-05-01

Non-prod webMethods GatewayInstance rows inherited prod UI/target URLs from
older backfills. Keep prod URLs only on prod rows; use environment-specific
runtime/target URLs for dev and staging.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "100_fix_webmethods_nonprod_urls"
down_revision: str | tuple[str, ...] | None = "099_catalog_release_versioning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NONPROD_WEBMETHODS_URLS = (
    ("connect-webmethods-dev", "dev", "https://dev-wm.gostoa.dev", "https://dev-wm.gostoa.dev"),
    ("connect-webmethods-dev-connect-dev", "dev", "https://dev-wm.gostoa.dev", "https://dev-wm.gostoa.dev"),
    ("stoa-link-wm-dev", "dev", "https://dev-wm-k3s.gostoa.dev", "https://dev-wm.gostoa.dev"),
    (
        "stoa-link-wm-dev-sidecar-dev",
        "dev",
        "https://dev-wm-k3s.gostoa.dev",
        "https://dev-wm.gostoa.dev",
    ),
    (
        "stoa-link-wm-sidecar-dev",
        "dev",
        "https://dev-wm-k3s.gostoa.dev",
        "https://dev-wm.gostoa.dev",
    ),
    (
        "connect-webmethods-staging",
        "staging",
        "https://staging-wm-k3s.gostoa.dev",
        "https://staging-wm-k3s.gostoa.dev",
    ),
    (
        "connect-webmethods-staging-connect-staging",
        "staging",
        "https://staging-wm-k3s.gostoa.dev",
        "https://staging-wm-k3s.gostoa.dev",
    ),
    (
        "stoa-link-wm-staging",
        "staging",
        "https://staging-wm-k3s.gostoa.dev",
        "https://staging-wm-k3s.gostoa.dev",
    ),
    (
        "stoa-link-wm-staging-sidecar-staging",
        "staging",
        "https://staging-wm-k3s.gostoa.dev",
        "https://staging-wm-k3s.gostoa.dev",
    ),
)


def upgrade() -> None:
    conn = op.get_bind()
    for name, environment, public_url, target_gateway_url in _NONPROD_WEBMETHODS_URLS:
        conn.execute(
            sa.text("""
                UPDATE gateway_instances
                SET
                  public_url = :public_url,
                  target_gateway_url = :target_gateway_url,
                  ui_url = NULL,
                  endpoints = jsonb_strip_nulls(
                    (COALESCE(endpoints, '{}'::jsonb) - 'ui_url' - 'uiUrl' - 'console_url'
                      - 'consoleUrl' - 'web_ui_url' - 'webUiUrl')
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
    conn = op.get_bind()
    for name, environment, _public_url, _target_gateway_url in _NONPROD_WEBMETHODS_URLS:
        conn.execute(
            sa.text("""
                UPDATE gateway_instances
                SET
                  ui_url = NULL,
                  endpoints = COALESCE(endpoints, '{}'::jsonb) - 'ui_url' - 'uiUrl'
                    - 'console_url' - 'consoleUrl' - 'web_ui_url' - 'webUiUrl',
                  updated_at = NOW()
                WHERE name = :name
                  AND environment = :environment
                  AND deleted_at IS NULL
            """),
            {"name": name, "environment": environment},
        )
