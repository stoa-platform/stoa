"""Add ui_url column to gateway_instances (CAB-1953)

Stores the web UI URL of third-party gateways managed by Link/Connect
instances (e.g. webMethods admin console at port 9072).

Also backfills public_url for known gateways that were missed by migration 085
(name mismatch: 085 used 'stoa-gateway' but instance is 'stoa-gateway-edge-mcp-dev').

Revision ID: 088
Revises: 087_add_deployment_generations
"""

import sqlalchemy as sa
from alembic import op

revision = "088"
down_revision = "087_add_deployment_generations"
branch_labels = None
depends_on = None

# Known URLs for existing gateways: (public_url, ui_url)
KNOWN_URLS = {
    # STOA Gateway (edge-mcp)
    "stoa-gateway-edge-mcp-dev": ("https://mcp.gostoa.dev", None),
    # STOA Link — webMethods (old name with double -dev, and fixed name)
    "stoa-link-wm-dev-sidecar-dev": ("https://link-webmethods.gostoa.dev", "https://vps-wm-ui.gostoa.dev"),
    "stoa-link-wm-sidecar-dev": ("https://link-webmethods.gostoa.dev", "https://vps-wm-ui.gostoa.dev"),
    # STOA Connect agents (VPS)
    "connect-webmethods-connect-production": ("https://connect-webmethods.gostoa.dev", "https://vps-wm-ui.gostoa.dev"),
    "kong-vps-connect-production": ("https://connect-kong.gostoa.dev", None),
    "gravitee-vps-connect-production": ("https://connect-gravitee.gostoa.dev", None),
    "connect-webmethods-dev-connect-dev": ("https://connect-webmethods.gostoa.dev", None),
}


def upgrade() -> None:
    op.add_column(
        "gateway_instances",
        sa.Column("ui_url", sa.String(500), nullable=True),
    )

    # Backfill public_url and ui_url for known gateways
    gateway_instances = sa.table(
        "gateway_instances",
        sa.column("name", sa.String),
        sa.column("public_url", sa.String),
        sa.column("ui_url", sa.String),
    )
    for name, (public_url, ui_url) in KNOWN_URLS.items():
        values: dict[str, str] = {}
        if public_url:
            values["public_url"] = public_url
        if ui_url:
            values["ui_url"] = ui_url
        if values:
            op.execute(
                gateway_instances.update()
                .where(gateway_instances.c.name == name)
                .values(**values)
            )


def downgrade() -> None:
    op.drop_column("gateway_instances", "ui_url")
