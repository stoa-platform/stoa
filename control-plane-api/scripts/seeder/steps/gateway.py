"""Seed gateway instances."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.seeder.models import StepResult

DEV_GATEWAYS: list[dict[str, Any]] = [
    {
        "name": "stoa-gateway-dev",
        "display_name": "STOA Gateway (Dev)",
        "gateway_type": "stoa_edge_mcp",
        "environment": "development",
        "base_url": "http://localhost:30080",
        "status": "active",
        "capabilities": ["mcp", "rate_limiting", "auth", "metering"],
    },
    {
        "name": "kong-dev",
        "display_name": "Kong Gateway (Dev)",
        "gateway_type": "kong",
        "environment": "development",
        "base_url": "http://localhost:8001",
        "status": "active",
        "capabilities": ["rate_limiting", "auth", "cors"],
    },
]

STAGING_GATEWAYS: list[dict[str, Any]] = [
    {
        "name": "stoa-gateway-staging",
        "display_name": "STOA Gateway (Staging)",
        "gateway_type": "stoa_edge_mcp",
        "environment": "staging",
        "base_url": "https://staging-mcp.gostoa.dev",
        "status": "active",
        "capabilities": ["mcp", "rate_limiting", "auth", "metering"],
    },
]

PROD_GATEWAYS: list[dict[str, Any]] = [
    {
        "name": "stoa-gateway-prod",
        "display_name": "STOA Gateway",
        "gateway_type": "stoa_edge_mcp",
        "environment": "production",
        "base_url": "https://mcp.gostoa.dev",
        "status": "active",
        "capabilities": ["mcp", "rate_limiting", "auth", "metering", "guardrails"],
    },
]

GATEWAYS_BY_PROFILE: dict[str, list[dict[str, Any]]] = {
    "dev": DEV_GATEWAYS,
    "staging": STAGING_GATEWAYS,
    "prod": PROD_GATEWAYS,
}


async def seed(session: AsyncSession, profile: str, *, dry_run: bool = False) -> StepResult:
    """Create gateway instances for the given profile."""
    gateways = GATEWAYS_BY_PROFILE[profile]
    result = StepResult(name="gateway")
    now = datetime.now(UTC)

    for gw_def in gateways:
        row = await session.execute(
            text("SELECT COUNT(*) FROM gateway_instances WHERE name = :name AND deleted_at IS NULL"),
            {"name": gw_def["name"]},
        )
        if row.scalar_one() > 0:
            result.skipped += 1
            continue

        if dry_run:
            print(f"  [DRY-RUN] Would create gateway: {gw_def['display_name']}")
            result.created += 1
            continue

        await session.execute(
            text("""
                INSERT INTO gateway_instances (
                    id, name, display_name, gateway_type, environment, base_url,
                    status, capabilities, source, enabled, visibility, created_at, updated_at
                ) VALUES (
                    :id, :name, :display_name, :gateway_type, :env, :base_url,
                    :status, :capabilities, 'seeder', true, 'public', :now, :now
                )
            """),
            {
                "id": uuid4(),
                "name": gw_def["name"],
                "display_name": gw_def["display_name"],
                "gateway_type": gw_def["gateway_type"],
                "env": gw_def["environment"],
                "base_url": gw_def["base_url"],
                "status": gw_def["status"],
                "capabilities": json.dumps(gw_def["capabilities"]),
                "now": now,
            },
        )
        result.created += 1
        print(f"  [STEP] gateway: created {gw_def['display_name']}")

    return result


async def check(session: AsyncSession, profile: str) -> list[str]:
    """Check which gateways are missing."""
    gateways = GATEWAYS_BY_PROFILE[profile]
    missing = []
    for gw_def in gateways:
        row = await session.execute(
            text("SELECT COUNT(*) FROM gateway_instances WHERE name = :name AND deleted_at IS NULL"),
            {"name": gw_def["name"]},
        )
        if row.scalar_one() == 0:
            missing.append(f"gateway:{gw_def['name']}")
    return missing


async def reset(session: AsyncSession, profile: str) -> int:
    """Delete seeder-created gateways."""
    gateways = GATEWAYS_BY_PROFILE[profile]
    total = 0
    for gw_def in gateways:
        row = await session.execute(
            text("DELETE FROM gateway_instances WHERE name = :name AND source = 'seeder'"),
            {"name": gw_def["name"]},
        )
        total += getattr(row, "rowcount", 0) or 0
    return total
