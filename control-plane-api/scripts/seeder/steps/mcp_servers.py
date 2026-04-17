"""Seed MCP servers and tools."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.seeder.models import StepResult

DEV_MCP_SERVERS: list[dict[str, Any]] = [
    {
        "name": "weather-service",
        "display_name": "Weather Service",
        "description": "Real-time weather data and forecasts.",
        "category": "public",
        "tenant_id": "demo",
        "tools": [
            {"name": "get_current_weather", "display_name": "Get Current Weather"},
            {"name": "get_forecast", "display_name": "Get 5-Day Forecast"},
        ],
    },
    {
        "name": "crm-tools",
        "display_name": "CRM Tools",
        "description": "Customer relationship management tools.",
        "category": "tenant",
        "tenant_id": "demo",
        "tools": [
            {"name": "search_contacts", "display_name": "Search Contacts"},
            {"name": "create_contact", "display_name": "Create Contact"},
            {"name": "get_contact_history", "display_name": "Get Contact History"},
        ],
    },
    {
        "name": "payment-gateway",
        "display_name": "Payment Gateway",
        "description": "Secure payment processing.",
        "category": "tenant",
        "tenant_id": "demo",
        "tools": [
            {"name": "create_charge", "display_name": "Create Charge"},
            {"name": "get_transaction", "display_name": "Get Transaction"},
        ],
    },
]

STAGING_MCP_SERVERS: list[dict[str, Any]] = [
    {
        "name": "weather-service",
        "display_name": "Weather Service",
        "description": "Weather data for staging validation.",
        "category": "public",
        "tenant_id": "oasis",
        "tools": [
            {"name": "get_current_weather", "display_name": "Get Current Weather"},
        ],
    },
]

MCP_SERVERS_BY_PROFILE: dict[str, list[dict[str, Any]]] = {
    "dev": DEV_MCP_SERVERS,
    "staging": STAGING_MCP_SERVERS,
    "prod": [],
}


async def seed(session: AsyncSession, profile: str, *, dry_run: bool = False) -> StepResult:
    """Create MCP servers and tools for the given profile."""
    servers = MCP_SERVERS_BY_PROFILE[profile]
    result = StepResult(name="mcp_servers")
    # mcp_servers.created_at / mcp_server_tools.created_at are DateTime
    # (tz-naive) in the ORM — asyncpg rejects tz-aware datetimes against
    # them. See fix notes in scripts/seeder/steps/plans.py.
    now = datetime.now(UTC).replace(tzinfo=None)

    for srv_def in servers:
        row = await session.execute(
            text("SELECT id FROM mcp_servers WHERE name = :name AND tenant_id = :tid"),
            {"name": srv_def["name"], "tid": srv_def["tenant_id"]},
        )
        existing = row.scalar_one_or_none()
        if existing:
            result.skipped += 1
            continue

        if dry_run:
            tools_count = len(srv_def.get("tools", []))
            print(f"  [DRY-RUN] Would create MCP server: {srv_def['display_name']} ({tools_count} tools)")
            result.created += 1
            continue

        server_id = uuid4()
        visibility = json.dumps({"public": True, "source": "seeder"})
        await session.execute(
            text("""
                INSERT INTO mcp_servers (
                    id, name, display_name, description, category, tenant_id,
                    visibility, requires_approval, status, version, created_at, updated_at
                ) VALUES (
                    :id, :name, :display_name, :desc, :category, :tid,
                    :visibility, false, 'active', '1.0.0', :now, :now
                )
            """),
            {
                "id": server_id,
                "name": srv_def["name"],
                "display_name": srv_def["display_name"],
                "desc": srv_def["description"],
                "category": srv_def["category"],
                "tid": srv_def["tenant_id"],
                "visibility": visibility,
                "now": now,
            },
        )

        for tool_def in srv_def.get("tools", []):
            await session.execute(
                text("""
                    INSERT INTO mcp_server_tools (
                        id, server_id, name, display_name, description,
                        input_schema, enabled, requires_approval, created_at, updated_at
                    ) VALUES (
                        :id, :server_id, :name, :display_name, :desc,
                        :schema, true, false, :now, :now
                    )
                """),
                {
                    "id": uuid4(),
                    "server_id": server_id,
                    "name": tool_def["name"],
                    "display_name": tool_def["display_name"],
                    "desc": f"Tool: {tool_def['display_name']}",
                    "schema": json.dumps({"type": "object", "properties": {}}),
                    "now": now,
                },
            )

        result.created += 1
        print(f"  [STEP] mcp_servers: created {srv_def['display_name']}")

    return result


async def check(session: AsyncSession, profile: str) -> list[str]:
    """Check which MCP servers are missing."""
    servers = MCP_SERVERS_BY_PROFILE[profile]
    missing = []
    for srv_def in servers:
        row = await session.execute(
            text("SELECT COUNT(*) FROM mcp_servers WHERE name = :name AND tenant_id = :tid"),
            {"name": srv_def["name"], "tid": srv_def["tenant_id"]},
        )
        if row.scalar_one() == 0:
            missing.append(f"mcp_server:{srv_def['name']}")
    return missing


async def reset(session: AsyncSession, profile: str) -> int:
    """Delete seeder-created MCP servers and their tools."""
    servers = MCP_SERVERS_BY_PROFILE[profile]
    total = 0
    for srv_def in servers:
        # Delete tools first (FK)
        await session.execute(
            text(
                "DELETE FROM mcp_server_tools WHERE server_id IN "
                "(SELECT id FROM mcp_servers WHERE name = :name AND tenant_id = :tid "
                "AND visibility->>'source' = 'seeder')"
            ),
            {"name": srv_def["name"], "tid": srv_def["tenant_id"]},
        )
        row = await session.execute(
            text(
                "DELETE FROM mcp_servers WHERE name = :name AND tenant_id = :tid "
                "AND visibility->>'source' = 'seeder'"
            ),
            {"name": srv_def["name"], "tid": srv_def["tenant_id"]},
        )
        total += getattr(row, "rowcount", 0) or 0
    return total
