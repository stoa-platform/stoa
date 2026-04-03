"""Add ui_url column to gateway_instances (CAB-1953)

Stores the web UI URL of third-party gateways managed by Link/Connect
instances (e.g. webMethods admin console at port 9072).

Also backfills public_url for known gateways that were missed by migration 085
(name mismatch: 085 used 'stoa-gateway' but instance is 'stoa-gateway-edge-mcp-dev').

Revision ID: 088
Revises: 087
"""

import sqlalchemy as sa
from alembic import op

revision = "088"
down_revision = "087"
branch_labels = None
depends_on = None

# Known URLs for existing gateways
KNOWN_PUBLIC_URLS = {
    "stoa-gateway-edge-mcp-dev": "https://mcp.gostoa.dev",
}


def upgrade() -> None:
    op.add_column(
        "gateway_instances",
        sa.Column("ui_url", sa.String(500), nullable=True),
    )

    # Backfill public_url for gateways missed by migration 085
    gateway_instances = sa.table(
        "gateway_instances",
        sa.column("name", sa.String),
        sa.column("public_url", sa.String),
    )
    for name, url in KNOWN_PUBLIC_URLS.items():
        op.execute(
            gateway_instances.update()
            .where(gateway_instances.c.name == name)
            .where(gateway_instances.c.public_url.is_(None))
            .values(public_url=url)
        )


def downgrade() -> None:
    op.drop_column("gateway_instances", "ui_url")
