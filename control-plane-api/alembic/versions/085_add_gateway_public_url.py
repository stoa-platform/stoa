"""Add public_url column to gateway_instances (CAB-1940)

Stores the public DNS URL of each gateway for Console display.
Populated by auto-registration (STOA_GATEWAY_PUBLIC_URL env var)
or manually via the admin API.

Also backfills known DNS URLs for existing gateway instances.

Revision ID: 085
Revises: 084
"""

import sqlalchemy as sa
from alembic import op

revision = "085"
down_revision = "084"
branch_labels = None
depends_on = None

# Known public URLs for existing gateways
KNOWN_URLS = {
    "stoa-gateway": "https://mcp.gostoa.dev",
    "stoa-link-wm-dev": "https://link-webmethods.gostoa.dev",
}


def upgrade() -> None:
    op.add_column(
        "gateway_instances",
        sa.Column("public_url", sa.String(500), nullable=True),
    )

    # Backfill known URLs
    gateway_instances = sa.table(
        "gateway_instances",
        sa.column("name", sa.String),
        sa.column("public_url", sa.String),
    )
    for name, url in KNOWN_URLS.items():
        op.execute(
            gateway_instances.update()
            .where(gateway_instances.c.name == name)
            .values(public_url=url)
        )


def downgrade() -> None:
    op.drop_column("gateway_instances", "public_url")
