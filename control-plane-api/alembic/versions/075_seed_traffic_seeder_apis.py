"""Seed 6 additional APIs for realistic traffic seeder (CAB-1869).

Extends the catalog with EU public data APIs + FAPI banking echo endpoints,
covering sidecar/connect modes and OAuth2/FAPI auth types for Call Flow demo.

New APIs:
- ECB Financial Data (EU public, sidecar mode)
- Eurostat (EU public, connect mode)
- Echo OAuth2 (internal, oauth2_cc auth)
- Echo Bearer (internal, bearer auth, connect mode)
- FAPI Accounts (banking demo, DPoP auth)
- FAPI Transfers (banking demo, DPoP + mTLS auth)

Idempotent: ON CONFLICT (tenant_id, api_id) DO UPDATE SET.

Revision ID: 075_seed_traffic_seeder_apis
Revises: 074_seed_realdata_apis
Create Date: 2026-03-17
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "075_seed_traffic_seeder_apis"
down_revision = "074_seed_realdata_apis"
branch_labels = None
depends_on = None

TENANT_ID = "demo"

# Deterministic UUIDs continuing from 074 series (d1a1b1c1-0007+)
APIS = [
    {
        "id": "d1a1b1c1-0007-4000-a000-000000000007",
        "api_id": "ecb-financial-data",
        "api_name": "ECB Financial Data",
        "version": "1.0",
        "category": "finance",
        "tags": ["ecb", "euribor", "forex", "eu-public", "realdata", "sidecar"],
        "metadata": {
            "description": "European Central Bank statistical data. Exchange rates, interest rates, monetary aggregates. EU public data, no auth.",
            "backend_url": "https://data-api.ecb.europa.eu/service/data",
            "auth_type": "none",
            "rate_limit": "unlimited",
            "methods": ["GET"],
            "deployment_mode": "sidecar",
        },
    },
    {
        "id": "d1a1b1c1-0008-4000-a000-000000000008",
        "api_id": "eurostat",
        "api_name": "Eurostat Statistics",
        "version": "1.0",
        "category": "statistics",
        "tags": ["eurostat", "gdp", "inflation", "eu-public", "realdata", "connect"],
        "metadata": {
            "description": "EU statistical data: GDP, inflation, unemployment, trade. Eurostat REST API, no auth required.",
            "backend_url": "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data",
            "auth_type": "none",
            "rate_limit": "unlimited",
            "methods": ["GET"],
            "deployment_mode": "connect",
        },
    },
    {
        "id": "d1a1b1c1-0009-4000-a000-000000000009",
        "api_id": "echo-oauth2",
        "api_name": "Echo OAuth2 Protected",
        "version": "1.0",
        "category": "internal",
        "tags": ["echo", "oauth2", "realdata", "internal"],
        "metadata": {
            "description": "Echo backend protected by OAuth2 client credentials. Demonstrates Keycloak integration and token caching.",
            "backend_url": "http://echo-backend.stoa-system.svc:8888",
            "auth_type": "oauth2_cc",
            "rate_limit": "unlimited",
            "methods": ["GET", "POST"],
            "deployment_mode": "edge-mcp",
        },
    },
    {
        "id": "d1a1b1c1-0010-4000-a000-000000000010",
        "api_id": "echo-bearer",
        "api_name": "Echo Bearer Token",
        "version": "1.0",
        "category": "internal",
        "tags": ["echo", "bearer", "realdata", "internal", "connect"],
        "metadata": {
            "description": "Echo backend with Bearer token auth via stoa-connect. Demonstrates Connect mode auth passthrough.",
            "backend_url": "http://fapi-echo:8889",
            "auth_type": "bearer",
            "rate_limit": "unlimited",
            "methods": ["GET"],
            "deployment_mode": "connect",
        },
    },
    {
        "id": "d1a1b1c1-0011-4000-a000-000000000011",
        "api_id": "fapi-accounts",
        "api_name": "FAPI Banking Accounts",
        "version": "2.0",
        "category": "banking",
        "tags": ["fapi", "banking", "dpop", "accounts", "realdata"],
        "metadata": {
            "description": "FAPI 2.0 Banking Accounts API. DPoP-bound access tokens (RFC 9449). Demonstrates financial-grade security.",
            "backend_url": "http://fapi-echo:8889/api/v1/accounts",
            "auth_type": "fapi_baseline",
            "rate_limit": "100/min",
            "methods": ["GET"],
            "deployment_mode": "edge-mcp",
        },
    },
    {
        "id": "d1a1b1c1-0012-4000-a000-000000000012",
        "api_id": "fapi-transfers",
        "api_name": "FAPI Banking Transfers",
        "version": "2.0",
        "category": "banking",
        "tags": ["fapi", "banking", "dpop", "mtls", "transfers", "realdata"],
        "metadata": {
            "description": "FAPI 2.0 Banking Transfers API. DPoP + mTLS client certificate binding. Maximum security for payment initiation.",
            "backend_url": "http://fapi-echo:8889/api/v1/transfers",
            "auth_type": "fapi_advanced",
            "rate_limit": "50/min",
            "methods": ["GET", "POST"],
            "deployment_mode": "edge-mcp",
        },
    },
]


def upgrade() -> None:
    conn = op.get_bind()

    for api in APIS:
        conn.execute(
            sa.text("""
                INSERT INTO api_catalog (
                    id, tenant_id, api_id, api_name, version, status, category, tags,
                    portal_published, audience, metadata, target_gateways
                )
                VALUES (
                    :id, :tenant_id, :api_id, :api_name, :version, :status, :category,
                    CAST(:tags AS jsonb), :portal_published, :audience,
                    CAST(:metadata AS jsonb), CAST(:target_gateways AS jsonb)
                )
                ON CONFLICT (tenant_id, api_id) DO UPDATE SET
                    api_name = EXCLUDED.api_name,
                    version = EXCLUDED.version,
                    status = EXCLUDED.status,
                    category = EXCLUDED.category,
                    tags = EXCLUDED.tags,
                    portal_published = EXCLUDED.portal_published,
                    metadata = EXCLUDED.metadata,
                    target_gateways = EXCLUDED.target_gateways
            """),
            {
                "id": api["id"],
                "tenant_id": TENANT_ID,
                "api_id": api["api_id"],
                "api_name": api["api_name"],
                "version": api["version"],
                "status": "published",
                "category": api["category"],
                "tags": json.dumps(api["tags"]),
                "portal_published": True,
                "audience": "public",
                "metadata": json.dumps(api["metadata"]),
                "target_gateways": '["stoa-gateway-prod"]',
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    api_ids = [api["id"] for api in APIS]
    for api_id in api_ids:
        conn.execute(
            sa.text("DELETE FROM api_catalog WHERE id = :id"),
            {"id": api_id},
        )
