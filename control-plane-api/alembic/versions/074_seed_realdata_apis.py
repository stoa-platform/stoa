"""Seed 5 real public APIs + echo fallback for constant real data in prod (CAB-1856).

Inserts 6 api_catalog entries for the 'demo' tenant, each with portal_published=True
so the Rust gateway auto-discovers them via /v1/internal/catalog/apis.

APIs:
- Exchange Rate API (public, unlimited)
- CoinGecko (public, 30 req/min)
- OpenWeatherMap (API key query param, 1000/day)
- NewsAPI (API key header, 100/day)
- Alpha Vantage (API key query param, 5/min)
- Echo Backend (internal fallback, unlimited)

Idempotent: ON CONFLICT (tenant_id, api_id) DO UPDATE SET.

Revision ID: 074_seed_realdata_apis
Revises: 073_chat_source
Create Date: 2026-03-16
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "074_seed_realdata_apis"
down_revision = "073_chat_source"
branch_labels = None
depends_on = None

TENANT_ID = "demo"

# Deterministic UUIDs for reproducible seeding
APIS = [
    {
        "id": "d1a1b1c1-0001-4000-a000-000000000001",
        "api_id": "exchange-rate",
        "api_name": "Exchange Rate API",
        "version": "4.0",
        "category": "finance",
        "tags": ["forex", "currency", "realdata", "public"],
        "metadata": {
            "description": "Real-time foreign exchange rates for 180+ currencies. No authentication required.",
            "backend_url": "https://api.exchangerate-api.com/v4/latest",
            "auth_type": "none",
            "rate_limit": "unlimited",
            "methods": ["GET"],
        },
    },
    {
        "id": "d1a1b1c1-0002-4000-a000-000000000002",
        "api_id": "coingecko",
        "api_name": "CoinGecko Crypto Prices",
        "version": "3.0",
        "category": "finance",
        "tags": ["crypto", "bitcoin", "realdata", "public"],
        "metadata": {
            "description": "Cryptocurrency prices, market cap, and volume for thousands of coins.",
            "backend_url": "https://api.coingecko.com/api/v3",
            "auth_type": "none",
            "rate_limit": "30 req/min",
            "methods": ["GET"],
        },
    },
    {
        "id": "d1a1b1c1-0003-4000-a000-000000000003",
        "api_id": "openweathermap",
        "api_name": "OpenWeatherMap",
        "version": "2.5",
        "category": "weather",
        "tags": ["weather", "forecast", "realdata", "api-key"],
        "metadata": {
            "description": "Real-time weather data for any location worldwide. Requires API key (query param).",
            "backend_url": "https://api.openweathermap.org/data/2.5",
            "auth_type": "api_key_query",
            "auth_param": "appid",
            "rate_limit": "1000/day",
            "methods": ["GET"],
        },
    },
    {
        "id": "d1a1b1c1-0004-4000-a000-000000000004",
        "api_id": "newsapi",
        "api_name": "NewsAPI Headlines",
        "version": "2.0",
        "category": "news",
        "tags": ["news", "headlines", "realdata", "api-key"],
        "metadata": {
            "description": "Top headlines from 80+ news sources worldwide. Requires API key (header).",
            "backend_url": "https://newsapi.org/v2",
            "auth_type": "api_key_header",
            "auth_header": "X-Api-Key",
            "rate_limit": "100/day",
            "methods": ["GET"],
        },
    },
    {
        "id": "d1a1b1c1-0005-4000-a000-000000000005",
        "api_id": "alphavantage",
        "api_name": "Alpha Vantage Stock Data",
        "version": "1.0",
        "category": "finance",
        "tags": ["stocks", "market", "realdata", "api-key"],
        "metadata": {
            "description": "Real-time and historical stock prices, technical indicators. Requires API key (query param).",
            "backend_url": "https://www.alphavantage.co/query",
            "auth_type": "api_key_query",
            "auth_param": "apikey",
            "rate_limit": "5/min, 500/day",
            "methods": ["GET"],
        },
    },
    {
        "id": "d1a1b1c1-0006-4000-a000-000000000006",
        "api_id": "echo-fallback",
        "api_name": "Echo Fallback Backend",
        "version": "1.0",
        "category": "internal",
        "tags": ["echo", "fallback", "realdata", "internal"],
        "metadata": {
            "description": "Internal echo backend for fallback when external APIs are unreachable. Always returns canned JSON.",
            "backend_url": "http://echo-backend.stoa-system.svc:8888",
            "auth_type": "none",
            "rate_limit": "unlimited",
            "methods": ["GET", "POST"],
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
