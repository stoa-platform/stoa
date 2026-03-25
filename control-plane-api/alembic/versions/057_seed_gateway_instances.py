"""seed gateway instances for multi-env platform

Revision ID: 057
Revises: 056
Create Date: 2026-03-05

Registers STOA + webMethods + Kong gateways across dev/staging/prod.
Idempotent: skips existing names via ON CONFLICT DO NOTHING.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid

# revision identifiers, used by Alembic.
revision: str = "057_seed_gateway_instances"
down_revision: Union[str, None] = "056_subscription_oauth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GATEWAYS = [
    # --- Production ---
    {
        "id": str(uuid.uuid4()),
        "name": "stoa-prod",
        "display_name": "STOA Gateway (Prod)",
        "gateway_type": "stoa_edge_mcp",
        "environment": "production",
        "base_url": "https://mcp.gostoa.dev",
        "auth_config": "{}",
        "status": "online",
        "capabilities": '["mcp", "rest", "oidc", "rate_limiting", "guardrails"]',
        "mode": "edge-mcp",
        "tags": '["prod", "primary"]',
    },
    {
        "id": str(uuid.uuid4()),
        "name": "webmethods-prod",
        "display_name": "webMethods API Gateway (Prod)",
        "gateway_type": "webmethods",
        "environment": "production",
        "base_url": "https://gateway.gostoa.dev",
        "auth_config": '{"type": "basic", "username": "Administrator", "vault_path": "/ovh/GATEWAY_ADMIN_PASSWORD"}',
        "status": "online",
        "capabilities": '["rest", "oidc", "rate_limiting", "backup"]',
        "mode": None,
        "tags": '["prod", "showcase"]',
    },
    {
        "id": str(uuid.uuid4()),
        "name": "kong-prod",
        "display_name": "Kong DB-less (Prod)",
        "gateway_type": "kong",
        "environment": "production",
        "base_url": "http://51.83.45.13:8001",
        "auth_config": "{}",
        "status": "online",
        "capabilities": '["rest", "rate_limiting"]',
        "mode": None,
        "tags": '["prod", "showcase", "arena"]',
    },
    # --- Staging (Hetzner K3s decommissioned 2026-03) ---
    # stoa-staging and kong-staging removed — cluster no longer exists
    # --- Development ---
    {
        "id": str(uuid.uuid4()),
        "name": "stoa-dev",
        "display_name": "STOA Gateway (Dev)",
        "gateway_type": "stoa_edge_mcp",
        "environment": "development",
        "base_url": "https://dev-mcp.gostoa.dev",
        "auth_config": "{}",
        "status": "online",
        "capabilities": '["mcp", "rest", "oidc", "rate_limiting"]',
        "mode": "edge-mcp",
        "tags": '["dev"]',
    },
    {
        "id": str(uuid.uuid4()),
        "name": "webmethods-dev",
        "display_name": "webMethods API Gateway (Dev)",
        "gateway_type": "webmethods",
        "environment": "development",
        "base_url": "https://dev-gateway.gostoa.dev",
        "auth_config": '{"type": "basic", "username": "Administrator", "vault_path": "/ovh/GATEWAY_ADMIN_PASSWORD"}',
        "status": "online",
        "capabilities": '["rest", "oidc", "rate_limiting", "backup"]',
        "mode": None,
        "tags": '["dev", "showcase"]',
    },
]


def upgrade() -> None:
    conn = op.get_bind()
    for gw in GATEWAYS:
        conn.execute(
            sa.text("""
                INSERT INTO gateway_instances
                    (id, name, display_name, gateway_type, environment,
                     base_url, auth_config, status, capabilities, mode, tags,
                     created_at, updated_at)
                VALUES
                    (:id, :name, :display_name, :gateway_type, :environment,
                     :base_url, CAST(:auth_config AS jsonb), :status, CAST(:capabilities AS jsonb),
                     :mode, CAST(:tags AS jsonb), NOW(), NOW())
                ON CONFLICT (name) DO NOTHING
            """),
            {
                "id": gw["id"],
                "name": gw["name"],
                "display_name": gw["display_name"],
                "gateway_type": gw["gateway_type"],
                "environment": gw["environment"],
                "base_url": gw["base_url"],
                "auth_config": gw["auth_config"],
                "status": gw["status"],
                "capabilities": gw["capabilities"],
                "mode": gw["mode"],
                "tags": gw["tags"],
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    names = [gw["name"] for gw in GATEWAYS]
    for name in names:
        conn.execute(
            sa.text("DELETE FROM gateway_instances WHERE name = :name"),
            {"name": name},
        )
