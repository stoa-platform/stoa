"""update gateway base_urls from raw IPs to proper DNS names

Revision ID: 079_update_gateway_dns_urls
Revises: 078_create_signed_certificates
Create Date: 2026-03-25

Replaces raw IPs with DNS names for Kong and Gravitee gateways.
Also registers stoa-connect and stoa-link instances per VPS.

DNS convention:
  {type}.gostoa.dev              → Gateway admin API
  connect-{type}.gostoa.dev      → stoa-connect agent (:9100)
  link-{type}.gostoa.dev         → stoa-link sidecar (:9200)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import uuid


revision: str = "079_update_gateway_dns_urls"
down_revision: Union[str, None] = "078_create_signed_certificates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# --- URL updates for existing gateways (IP → DNS) ---
URL_UPDATES = [
    # kong-prod (seed 057): raw IP → DNS
    {"name": "kong-prod", "old_url": "http://51.83.45.13:8001", "new_url": "https://kong.gostoa.dev"},
    # kong-vps (register-gateways.sh): raw IP → DNS
    {"name": "kong-vps", "old_url": "http://54.36.209.237:8001", "new_url": "https://kong.gostoa.dev"},
    # gravitee-vps (register-gateways.sh): raw IP → DNS
    {"name": "gravitee-vps", "old_url": "http://54.36.209.237:8083", "new_url": "https://gravitee.gostoa.dev"},
    # webmethods-vps (register-gateways.sh): raw IP → DNS
    {"name": "webmethods-vps", "old_url": "http://51.255.201.17:5555", "new_url": "https://webmethods.gostoa.dev"},
]

# --- New gateway instances: stoa-connect agents ---
CONNECT_INSTANCES = [
    {
        "id": str(uuid.uuid4()),
        "name": "connect-kong",
        "display_name": "stoa-connect (Kong VPS)",
        "gateway_type": "stoa",
        "environment": "production",
        "base_url": "https://connect-kong.gostoa.dev",
        "auth_config": '{"type": "api_key", "vault_path": "stoa/shared/gateway-api-key"}',
        "status": "offline",
        "capabilities": '["mcp", "rest", "discovery"]',
        "mode": "connect",
        "tags": '["vps", "connect", "kong"]',
    },
    {
        "id": str(uuid.uuid4()),
        "name": "connect-gravitee",
        "display_name": "stoa-connect (Gravitee VPS)",
        "gateway_type": "stoa",
        "environment": "production",
        "base_url": "https://connect-gravitee.gostoa.dev",
        "auth_config": '{"type": "api_key", "vault_path": "stoa/shared/gateway-api-key"}',
        "status": "offline",
        "capabilities": '["mcp", "rest", "discovery"]',
        "mode": "connect",
        "tags": '["vps", "connect", "gravitee"]',
    },
    {
        "id": str(uuid.uuid4()),
        "name": "connect-webmethods",
        "display_name": "stoa-connect (webMethods VPS)",
        "gateway_type": "stoa",
        "environment": "production",
        "base_url": "https://connect-webmethods.gostoa.dev",
        "auth_config": '{"type": "api_key", "vault_path": "stoa/shared/gateway-api-key"}',
        "status": "offline",
        "capabilities": '["mcp", "rest", "discovery"]',
        "mode": "connect",
        "tags": '["vps", "connect", "webmethods"]',
    },
]

# --- New gateway instances: stoa-link sidecars ---
LINK_INSTANCES = [
    {
        "id": str(uuid.uuid4()),
        "name": "link-kong",
        "display_name": "stoa-link (Kong VPS)",
        "gateway_type": "stoa_sidecar",
        "environment": "production",
        "base_url": "https://link-kong.gostoa.dev",
        "auth_config": '{"type": "api_key", "vault_path": "stoa/shared/gateway-api-key"}',
        "status": "offline",
        "capabilities": '["mcp", "rest"]',
        "mode": "sidecar",
        "tags": '["vps", "link", "kong"]',
    },
    {
        "id": str(uuid.uuid4()),
        "name": "link-gravitee",
        "display_name": "stoa-link (Gravitee VPS)",
        "gateway_type": "stoa_sidecar",
        "environment": "production",
        "base_url": "https://link-gravitee.gostoa.dev",
        "auth_config": '{"type": "api_key", "vault_path": "stoa/shared/gateway-api-key"}',
        "status": "offline",
        "capabilities": '["mcp", "rest"]',
        "mode": "sidecar",
        "tags": '["vps", "link", "gravitee"]',
    },
    {
        "id": str(uuid.uuid4()),
        "name": "link-webmethods",
        "display_name": "stoa-link (webMethods VPS)",
        "gateway_type": "stoa_sidecar",
        "environment": "production",
        "base_url": "https://link-webmethods.gostoa.dev",
        "auth_config": '{"type": "api_key", "vault_path": "stoa/shared/gateway-api-key"}',
        "status": "offline",
        "capabilities": '["mcp", "rest"]',
        "mode": "sidecar",
        "tags": '["vps", "link", "webmethods"]',
    },
]

ALL_NEW = CONNECT_INSTANCES + LINK_INSTANCES


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Update existing gateway URLs (IP → DNS)
    for update in URL_UPDATES:
        conn.execute(
            sa.text("""
                UPDATE gateway_instances
                SET base_url = :new_url, updated_at = NOW()
                WHERE name = :name
            """),
            {"name": update["name"], "new_url": update["new_url"]},
        )

    # 2. Insert stoa-connect + stoa-link instances
    for gw in ALL_NEW:
        conn.execute(
            sa.text("""
                INSERT INTO gateway_instances
                    (id, name, display_name, gateway_type, environment,
                     base_url, auth_config, status, capabilities, mode, tags,
                     created_at, updated_at)
                VALUES
                    (:id, :name, :display_name, :gateway_type, :environment,
                     :base_url, CAST(:auth_config AS jsonb), :status,
                     CAST(:capabilities AS jsonb), :mode, CAST(:tags AS jsonb),
                     NOW(), NOW())
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

    # 1. Revert URL updates
    for update in URL_UPDATES:
        conn.execute(
            sa.text("""
                UPDATE gateway_instances
                SET base_url = :old_url, updated_at = NOW()
                WHERE name = :name
            """),
            {"name": update["name"], "old_url": update["old_url"]},
        )

    # 2. Delete stoa-connect + stoa-link instances
    names = [gw["name"] for gw in ALL_NEW]
    for name in names:
        conn.execute(
            sa.text("DELETE FROM gateway_instances WHERE name = :name"),
            {"name": name},
        )
