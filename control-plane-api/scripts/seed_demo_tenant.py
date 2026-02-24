#!/usr/bin/env python3
"""Seed a demo tenant with sample APIs, MCP servers, tools, consumers, and subscriptions.

Creates a fully-functional demo environment for prospects and community members.
Supports both fresh seeding and idempotent re-runs (skips existing data).

Usage:
    cd control-plane-api
    python -m scripts.seed_demo_tenant              # Seed demo tenant
    python -m scripts.seed_demo_tenant --reset      # Reset (delete + re-seed)
    python -m scripts.seed_demo_tenant --check      # Check current demo state

Requirements:
    - Database must be running and accessible
    - Tables must exist (run alembic migrations first)
    - Keycloak NOT required (provisioning bypassed for speed)
"""

import argparse
import asyncio
import hashlib
import json
import secrets
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ---------------------------------------------------------------------------
# Demo data definitions
# ---------------------------------------------------------------------------

DEMO_TENANT_ID = "demo"
DEMO_TENANT_NAME = "Demo Corp"
DEMO_TENANT_DESCRIPTION = (
    "STOA demo tenant with sample APIs, MCP tools, and pre-configured consumers. "
    "Resets automatically every 24 hours."
)
DEMO_OWNER_EMAIL = "admin@demo.gostoa.dev"

# MCP Servers — grouped collections of tools
DEMO_MCP_SERVERS: list[dict[str, Any]] = [
    {
        "name": "weather-service",
        "display_name": "Weather Service",
        "description": "Real-time weather data and forecasts for any location worldwide.",
        "category": "public",
        "tools": [
            {
                "name": "get_current_weather",
                "display_name": "Get Current Weather",
                "description": "Get current weather conditions for a city or coordinates.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "City name or lat,lon"},
                        "units": {"type": "string", "enum": ["celsius", "fahrenheit"], "default": "celsius"},
                    },
                    "required": ["location"],
                },
                "endpoint": "https://api.demo.gostoa.dev/weather/current",
                "method": "GET",
                "rate_limit": 120,
            },
            {
                "name": "get_forecast",
                "display_name": "Get 5-Day Forecast",
                "description": "Get weather forecast for the next 5 days.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"},
                        "days": {"type": "integer", "minimum": 1, "maximum": 5, "default": 3},
                    },
                    "required": ["location"],
                },
                "endpoint": "https://api.demo.gostoa.dev/weather/forecast",
                "method": "GET",
                "rate_limit": 60,
            },
        ],
    },
    {
        "name": "crm-tools",
        "display_name": "CRM Tools",
        "description": "Customer relationship management tools — search, create, and manage contacts.",
        "category": "tenant",
        "tools": [
            {
                "name": "search_contacts",
                "display_name": "Search Contacts",
                "description": "Search CRM contacts by name, email, or company.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "limit": {"type": "integer", "default": 10, "maximum": 50},
                    },
                    "required": ["query"],
                },
                "endpoint": "https://api.demo.gostoa.dev/crm/contacts/search",
                "method": "POST",
                "rate_limit": 60,
            },
            {
                "name": "create_contact",
                "display_name": "Create Contact",
                "description": "Create a new contact in the CRM.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "first_name": {"type": "string"},
                        "last_name": {"type": "string"},
                        "email": {"type": "string", "format": "email"},
                        "company": {"type": "string"},
                        "phone": {"type": "string"},
                    },
                    "required": ["first_name", "last_name", "email"],
                },
                "endpoint": "https://api.demo.gostoa.dev/crm/contacts",
                "method": "POST",
                "rate_limit": 30,
            },
            {
                "name": "get_contact_history",
                "display_name": "Get Contact History",
                "description": "Get interaction history for a contact.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "contact_id": {"type": "string"},
                        "since": {"type": "string", "format": "date", "description": "ISO date"},
                    },
                    "required": ["contact_id"],
                },
                "endpoint": "https://api.demo.gostoa.dev/crm/contacts/{contact_id}/history",
                "method": "GET",
                "rate_limit": 60,
            },
        ],
    },
    {
        "name": "payment-gateway",
        "display_name": "Payment Gateway",
        "description": "Secure payment processing — charges, refunds, and transaction lookup.",
        "category": "tenant",
        "tools": [
            {
                "name": "create_charge",
                "display_name": "Create Charge",
                "description": "Create a new payment charge.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "amount": {"type": "number", "minimum": 0.01},
                        "currency": {"type": "string", "enum": ["EUR", "USD", "GBP"], "default": "EUR"},
                        "description": {"type": "string"},
                        "customer_email": {"type": "string", "format": "email"},
                    },
                    "required": ["amount", "currency", "customer_email"],
                },
                "endpoint": "https://api.demo.gostoa.dev/payments/charges",
                "method": "POST",
                "rate_limit": 30,
            },
            {
                "name": "get_transaction",
                "display_name": "Get Transaction",
                "description": "Look up a transaction by ID.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "transaction_id": {"type": "string"},
                    },
                    "required": ["transaction_id"],
                },
                "endpoint": "https://api.demo.gostoa.dev/payments/transactions/{transaction_id}",
                "method": "GET",
                "rate_limit": 120,
            },
        ],
    },
]

# API Catalog entries — REST APIs published in the developer portal
DEMO_API_CATALOG = [
    {
        "api_id": "weather-api-v1",
        "api_name": "Weather API",
        "version": "1.0.0",
        "category": "data",
        "tags": ["weather", "forecast", "public"],
        "audience": "public",
        "portal_published": True,
        "api_metadata": {
            "name": "Weather API",
            "version": "1.0.0",
            "description": "Real-time weather data for any location.",
            "base_url": "https://api.demo.gostoa.dev/weather",
            "auth": {"type": "api_key", "header": "X-API-Key"},
            "rate_limit": {"requests_per_minute": 120},
        },
    },
    {
        "api_id": "crm-api-v2",
        "api_name": "CRM API",
        "version": "2.1.0",
        "category": "business",
        "tags": ["crm", "contacts", "internal"],
        "audience": "internal",
        "portal_published": True,
        "api_metadata": {
            "name": "CRM API",
            "version": "2.1.0",
            "description": "Customer relationship management endpoints.",
            "base_url": "https://api.demo.gostoa.dev/crm",
            "auth": {"type": "bearer", "scheme": "oauth2"},
            "rate_limit": {"requests_per_minute": 60},
        },
    },
    {
        "api_id": "payments-api-v1",
        "api_name": "Payment Gateway API",
        "version": "1.3.0",
        "category": "financial",
        "tags": ["payments", "charges", "partner"],
        "audience": "partner",
        "portal_published": True,
        "api_metadata": {
            "name": "Payment Gateway API",
            "version": "1.3.0",
            "description": "Secure payment processing with PCI-DSS compliance.",
            "base_url": "https://api.demo.gostoa.dev/payments",
            "auth": {"type": "bearer", "scheme": "oauth2"},
            "rate_limit": {"requests_per_minute": 30},
        },
    },
]

# Consumers — external API consumers
DEMO_CONSUMERS = [
    {
        "external_id": "demo-alice",
        "name": "Alice Martin",
        "email": "alice@acme-corp.demo",
        "company": "Acme Corp",
        "description": "Full-access developer with all subscriptions.",
    },
    {
        "external_id": "demo-bob",
        "name": "Bob Chen",
        "email": "bob@techstart.demo",
        "company": "TechStart Inc",
        "description": "Read-only weather API consumer.",
    },
    {
        "external_id": "demo-carol",
        "name": "Carol Dupont",
        "email": "carol@eurofinance.demo",
        "company": "EuroFinance SA",
        "description": "Payment gateway partner with CRM access.",
    },
]

# Subscriptions — who subscribes to which MCP server
# Format: (consumer_index, server_name)
DEMO_SUBSCRIPTIONS = [
    (0, "weather-service"),   # Alice → Weather
    (0, "crm-tools"),         # Alice → CRM
    (0, "payment-gateway"),   # Alice → Payments
    (1, "weather-service"),   # Bob → Weather only
    (2, "crm-tools"),         # Carol → CRM
    (2, "payment-gateway"),   # Carol → Payments
]


def _generate_api_key() -> tuple[str, str, str]:
    """Generate an API key, its hash, and prefix."""
    raw_key = f"stoa_demo_{secrets.token_hex(24)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    prefix = raw_key[:16]
    return raw_key, key_hash, prefix


# ---------------------------------------------------------------------------
# Seed logic
# ---------------------------------------------------------------------------


async def check_demo_state(session: AsyncSession) -> dict[str, Any]:
    """Check current demo data state."""
    counts: dict[str, Any] = {}
    for table, condition in [
        ("tenants", f"id = '{DEMO_TENANT_ID}'"),
        ("mcp_servers", f"tenant_id = '{DEMO_TENANT_ID}'"),
        ("mcp_server_tools", f"server_id IN (SELECT id FROM mcp_servers WHERE tenant_id = '{DEMO_TENANT_ID}')"),  # noqa: S608
        ("consumers", f"tenant_id = '{DEMO_TENANT_ID}'"),
        ("mcp_server_subscriptions", f"tenant_id = '{DEMO_TENANT_ID}'"),
        ("api_catalog", f"tenant_id = '{DEMO_TENANT_ID}'"),
    ]:
        try:
            result = await session.execute(text(f"SELECT COUNT(*) FROM {table} WHERE {condition}"))  # noqa: S608
            counts[table] = result.scalar_one()
        except Exception:
            counts[table] = -1  # Table might not exist
    return counts


async def delete_demo_data(session: AsyncSession) -> int:
    """Delete all demo tenant data. Returns total rows deleted."""
    total = 0
    # Order matters — delete dependents first (FK constraints)
    delete_order = [
        ("mcp_tool_access", f"subscription_id IN (SELECT id FROM mcp_server_subscriptions WHERE tenant_id = '{DEMO_TENANT_ID}')"),  # noqa: S608
        ("mcp_server_subscriptions", f"tenant_id = '{DEMO_TENANT_ID}'"),
        ("mcp_server_tools", f"server_id IN (SELECT id FROM mcp_servers WHERE tenant_id = '{DEMO_TENANT_ID}')"),  # noqa: S608
        ("mcp_servers", f"tenant_id = '{DEMO_TENANT_ID}'"),
        ("consumers", f"tenant_id = '{DEMO_TENANT_ID}'"),
        ("api_catalog", f"tenant_id = '{DEMO_TENANT_ID}'"),
        ("tenants", f"id = '{DEMO_TENANT_ID}'"),
    ]
    for table, condition in delete_order:
        try:
            result = await session.execute(text(f"DELETE FROM {table} WHERE {condition}"))  # noqa: S608
            deleted: int = result.rowcount or 0  # type: ignore[assignment]
            if deleted > 0:
                print(f"  Deleted {deleted} rows from {table}")
                total += deleted
        except Exception as e:
            print(f"  Warning: could not delete from {table}: {e}")  # noqa: S608
    return total


async def seed_demo_tenant(session: AsyncSession) -> dict[str, Any]:
    """Seed the demo tenant with all data. Returns summary of created items."""
    now = datetime.now(UTC)
    summary: dict[str, Any] = {"tenant": 0, "servers": 0, "tools": 0, "consumers": 0, "subscriptions": 0, "catalog": 0, "api_keys": []}

    # 1. Create tenant (set provisioning_status=ready to skip async provisioning)
    result = await session.execute(text(f"SELECT COUNT(*) FROM tenants WHERE id = '{DEMO_TENANT_ID}'"))  # noqa: S608
    if result.scalar_one() > 0:
        print(f"  Tenant '{DEMO_TENANT_ID}' already exists, skipping...")
    else:
        await session.execute(
            text("""
                INSERT INTO tenants (id, name, description, status, provisioning_status, settings, created_at, updated_at)
                VALUES (:id, :name, :desc, 'active', 'ready', :settings, :now, :now)
            """),
            {
                "id": DEMO_TENANT_ID,
                "name": DEMO_TENANT_NAME,
                "desc": DEMO_TENANT_DESCRIPTION,
                "settings": json.dumps({"owner_email": DEMO_OWNER_EMAIL, "demo": True}),
                "now": now,
            },
        )
        summary["tenant"] = 1
        print(f"  Created tenant: {DEMO_TENANT_NAME} ({DEMO_TENANT_ID})")

    # 2. Create MCP servers + tools
    server_ids = {}  # name → UUID
    for server_def in DEMO_MCP_SERVERS:
        server_id = uuid4()
        server_ids[server_def["name"]] = server_id

        # Check if server already exists
        result = await session.execute(
            text("SELECT id FROM mcp_servers WHERE name = :name"),
            {"name": server_def["name"]},
        )
        existing = result.scalar_one_or_none()
        if existing:
            server_ids[server_def["name"]] = existing if isinstance(existing, UUID) else UUID(str(existing))
            print(f"  Server '{server_def['name']}' already exists, skipping...")
            continue

        await session.execute(
            text("""
                INSERT INTO mcp_servers (id, name, display_name, description, category, tenant_id,
                    visibility, requires_approval, status, version, created_at, updated_at)
                VALUES (:id, :name, :display_name, :desc, :category, :tenant_id,
                    :visibility, false, 'active', '1.0.0', :now, :now)
            """),
            {
                "id": server_id,
                "name": server_def["name"],
                "display_name": server_def["display_name"],
                "desc": server_def["description"],
                "category": server_def["category"],
                "tenant_id": DEMO_TENANT_ID,
                "visibility": json.dumps({"public": True}),
                "now": now,
            },
        )
        summary["servers"] += 1
        print(f"  Created MCP server: {server_def['display_name']}")

        # Create tools for this server
        for tool_def in server_def["tools"]:
            tool_id = uuid4()
            await session.execute(
                text("""
                    INSERT INTO mcp_server_tools (id, server_id, name, display_name, description,
                        input_schema, enabled, requires_approval, endpoint, method, rate_limit, created_at, updated_at)
                    VALUES (:id, :server_id, :name, :display_name, :desc,
                        :input_schema, true, false, :endpoint, :method, :rate_limit, :now, :now)
                """),
                {
                    "id": tool_id,
                    "server_id": server_id,
                    "name": tool_def["name"],
                    "display_name": tool_def["display_name"],
                    "desc": tool_def["description"],
                    "input_schema": json.dumps(tool_def["input_schema"]),
                    "endpoint": tool_def["endpoint"],
                    "method": tool_def["method"],
                    "rate_limit": tool_def["rate_limit"],
                    "now": now,
                },
            )
            summary["tools"] += 1

    # 3. Create consumers
    consumer_ids = []
    for consumer_def in DEMO_CONSUMERS:
        consumer_id = uuid4()

        result = await session.execute(
            text("SELECT id FROM consumers WHERE tenant_id = :tid AND external_id = :eid"),
            {"tid": DEMO_TENANT_ID, "eid": consumer_def["external_id"]},
        )
        existing = result.scalar_one_or_none()
        if existing:
            consumer_ids.append(existing if isinstance(existing, UUID) else UUID(str(existing)))
            print(f"  Consumer '{consumer_def['name']}' already exists, skipping...")
            continue

        consumer_ids.append(consumer_id)
        await session.execute(
            text("""
                INSERT INTO consumers (id, external_id, name, email, company, description,
                    tenant_id, status, created_at, updated_at)
                VALUES (:id, :eid, :name, :email, :company, :desc,
                    :tid, 'active', :now, :now)
            """),
            {
                "id": consumer_id,
                "eid": consumer_def["external_id"],
                "name": consumer_def["name"],
                "email": consumer_def["email"],
                "company": consumer_def["company"],
                "desc": consumer_def["description"],
                "tid": DEMO_TENANT_ID,
                "now": now,
            },
        )
        summary["consumers"] += 1
        print(f"  Created consumer: {consumer_def['name']} ({consumer_def['company']})")

    # 4. Create subscriptions with API keys
    for consumer_idx, server_name in DEMO_SUBSCRIPTIONS:
        server_id = server_ids.get(server_name)
        if not server_id or consumer_idx >= len(consumer_ids):
            continue

        consumer_id = consumer_ids[consumer_idx]
        consumer_def = DEMO_CONSUMERS[consumer_idx]

        # Check if subscription already exists
        result = await session.execute(
            text("""
                SELECT id FROM mcp_server_subscriptions
                WHERE subscriber_id = :sub_id AND server_id = :srv_id AND tenant_id = :tid
            """),
            {"sub_id": str(consumer_id), "srv_id": server_id, "tid": DEMO_TENANT_ID},
        )
        if result.scalar_one_or_none():
            continue

        raw_key, key_hash, key_prefix = _generate_api_key()
        sub_id = uuid4()
        await session.execute(
            text("""
                INSERT INTO mcp_server_subscriptions (id, server_id, subscriber_id, subscriber_email,
                    tenant_id, plan, api_key_hash, api_key_prefix, status, created_at, updated_at, approved_at)
                VALUES (:id, :srv_id, :sub_id, :email, :tid, 'free',
                    :key_hash, :key_prefix, 'active', :now, :now, :now)
            """),
            {
                "id": sub_id,
                "srv_id": server_id,
                "sub_id": str(consumer_id),
                "email": consumer_def["email"],
                "tid": DEMO_TENANT_ID,
                "key_hash": key_hash,
                "key_prefix": key_prefix,
                "now": now,
            },
        )
        summary["subscriptions"] += 1
        summary["api_keys"].append({
            "consumer": consumer_def["name"],
            "server": server_name,
            "api_key": raw_key,
        })

    # 5. Create API catalog entries
    for api_def in DEMO_API_CATALOG:
        result = await session.execute(
            text("SELECT id FROM api_catalog WHERE tenant_id = :tid AND api_id = :aid"),
            {"tid": DEMO_TENANT_ID, "aid": api_def["api_id"]},
        )
        if result.scalar_one_or_none():
            print(f"  API '{api_def['api_name']}' already in catalog, skipping...")
            continue

        await session.execute(
            text("""
                INSERT INTO api_catalog (id, tenant_id, api_id, api_name, version, status,
                    category, tags, portal_published, audience, metadata, synced_at)
                VALUES (:id, :tid, :aid, :name, :version, 'active',
                    :category, :tags, :published, :audience, :metadata, :now)
            """),
            {
                "id": uuid4(),
                "tid": DEMO_TENANT_ID,
                "aid": api_def["api_id"],
                "name": api_def["api_name"],
                "version": api_def["version"],
                "category": api_def["category"],
                "tags": json.dumps(api_def["tags"]),
                "published": api_def["portal_published"],
                "audience": api_def["audience"],
                "metadata": json.dumps(api_def["api_metadata"]),
                "now": now,
            },
        )
        summary["catalog"] += 1
        print(f"  Published API: {api_def['api_name']} v{api_def['version']} ({api_def['audience']})")

    return summary


# ---------------------------------------------------------------------------
# Main entry points
# ---------------------------------------------------------------------------


async def run(database_url: str, *, reset: bool = False, check_only: bool = False) -> None:
    """Main seed/reset/check workflow."""
    engine = create_async_engine(database_url, echo=False)
    async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session_factory() as session:
        try:
            if check_only:
                print("Demo tenant state:")
                counts = await check_demo_state(session)
                for table, count in counts.items():
                    status = "OK" if count > 0 else ("missing" if count == 0 else "error")
                    print(f"  {table}: {count} ({status})")
                total = sum(c for c in counts.values() if c > 0)
                print(f"\nTotal demo records: {total}")
                return

            if reset:
                print("Resetting demo tenant...")
                deleted = await delete_demo_data(session)
                await session.commit()
                print(f"Deleted {deleted} total rows.\n")

            # Check if already seeded
            counts = await check_demo_state(session)
            if counts.get("tenants", 0) > 0 and not reset:
                print("Demo tenant already exists. Use --reset to re-seed.")
                print("Current state:")
                for table, count in counts.items():
                    if count > 0:
                        print(f"  {table}: {count}")
                return

            print(f"Seeding demo tenant '{DEMO_TENANT_ID}'...\n")
            summary = await seed_demo_tenant(session)
            await session.commit()

            # Print summary
            print(f"\n{'='*60}")
            print("Demo tenant seeded successfully!")
            print(f"{'='*60}")
            print(f"  Tenant:        {summary['tenant']} created")
            print(f"  MCP Servers:   {summary['servers']} created")
            print(f"  Tools:         {summary['tools']} created")
            print(f"  Consumers:     {summary['consumers']} created")
            print(f"  Subscriptions: {summary['subscriptions']} created")
            print(f"  API Catalog:   {summary['catalog']} published")

            if summary["api_keys"]:
                print("\nAPI Keys (save these — not retrievable later):")
                print(f"{'─'*60}")
                for entry in summary["api_keys"]:
                    print(f"  {entry['consumer']} → {entry['server']}")
                    print(f"    Key: {entry['api_key']}")
                print(f"{'─'*60}")

        except Exception as e:
            await session.rollback()
            print(f"\nError: {e}")
            raise


async def main() -> None:
    """CLI entry point."""
    import os

    parser = argparse.ArgumentParser(description="Seed STOA demo tenant")
    parser.add_argument("--reset", action="store_true", help="Delete existing demo data and re-seed")
    parser.add_argument("--check", action="store_true", help="Check current demo state (no changes)")
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://stoa:stoa@localhost:5432/stoa")
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    await run(database_url, reset=args.reset, check_only=args.check)


if __name__ == "__main__":
    asyncio.run(main())
