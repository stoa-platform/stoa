"""Seed tenants."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.seeder.models import StepResult

SEEDER_TAG = {"source": "seeder"}

# Tenant definitions per profile
DEV_TENANTS: list[dict[str, Any]] = [
    {
        "id": "demo",
        "name": "Demo Corp",
        "description": "STOA demo tenant with sample APIs, MCP tools, and pre-configured consumers.",
        "owner_email": "admin@demo.gostoa.dev",
    },
    {
        "id": "oasis",
        "name": "OASIS",
        "description": "Primary development tenant.",
        "owner_email": "admin@oasis.gostoa.dev",
    },
    {
        "id": "acme-corp",
        "name": "Acme Corp",
        "description": "Test tenant for mTLS and federation demos.",
        "owner_email": "admin@acme-corp.gostoa.dev",
    },
]

STAGING_TENANTS: list[dict[str, Any]] = [
    {
        "id": "oasis",
        "name": "OASIS",
        "description": "Primary staging tenant.",
        "owner_email": "admin@oasis.gostoa.dev",
    },
    {
        "id": "staging-test",
        "name": "Staging Test Corp",
        "description": "Staging validation tenant.",
        "owner_email": "admin@staging-test.gostoa.dev",
    },
]

PROD_TENANTS: list[dict[str, Any]] = [
    {
        "id": "oasis",
        "name": "OASIS",
        "description": "Platform admin tenant.",
        "owner_email": "admin@oasis.gostoa.dev",
    },
]

TENANTS_BY_PROFILE: dict[str, list[dict[str, Any]]] = {
    "dev": DEV_TENANTS,
    "staging": STAGING_TENANTS,
    "prod": PROD_TENANTS,
}


async def seed(session: AsyncSession, profile: str, *, dry_run: bool = False) -> StepResult:
    """Create tenants for the given profile."""
    tenants = TENANTS_BY_PROFILE[profile]
    result = StepResult(name="tenants")
    now = datetime.now(UTC)

    for tenant_def in tenants:
        row = await session.execute(
            text("SELECT COUNT(*) FROM tenants WHERE id = :id"),
            {"id": tenant_def["id"]},
        )
        if row.scalar_one() > 0:
            result.skipped += 1
            continue

        if dry_run:
            print(f"  [DRY-RUN] Would create tenant: {tenant_def['name']} ({tenant_def['id']})")
            result.created += 1
            continue

        settings = {**SEEDER_TAG, "owner_email": tenant_def["owner_email"], "demo": True}
        await session.execute(
            text("""
                INSERT INTO tenants (id, name, description, status, provisioning_status, settings, created_at, updated_at)
                VALUES (:id, :name, :desc, 'active', 'ready', :settings, :now, :now)
            """),
            {
                "id": tenant_def["id"],
                "name": tenant_def["name"],
                "desc": tenant_def["description"],
                "settings": json.dumps(settings),
                "now": now,
            },
        )
        result.created += 1
        print(f"  [STEP] tenants: created {tenant_def['name']} ({tenant_def['id']})")

    return result


async def check(session: AsyncSession, profile: str) -> list[str]:
    """Check which tenants are missing."""
    tenants = TENANTS_BY_PROFILE[profile]
    missing = []
    for tenant_def in tenants:
        row = await session.execute(
            text("SELECT COUNT(*) FROM tenants WHERE id = :id"),
            {"id": tenant_def["id"]},
        )
        if row.scalar_one() == 0:
            missing.append(f"tenant:{tenant_def['id']}")
    return missing


async def reset(session: AsyncSession, profile: str) -> int:
    """Delete seeder-created tenants. Returns rows deleted."""
    tenants = TENANTS_BY_PROFILE[profile]
    total = 0
    for tenant_def in tenants:
        row = await session.execute(
            text("DELETE FROM tenants WHERE id = :id AND settings->>'source' = 'seeder'"),
            {"id": tenant_def["id"]},
        )
        total += getattr(row, "rowcount", 0) or 0
    return total
