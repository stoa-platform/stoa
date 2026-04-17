"""Seed consumers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.seeder.models import StepResult

DEV_CONSUMERS: list[dict[str, Any]] = [
    {
        "external_id": "demo-alice",
        "name": "Alice Martin",
        "email": "alice@acme-corp.demo",
        "company": "Acme Corp",
        "tenant_id": "demo",
    },
    {
        "external_id": "demo-bob",
        "name": "Bob Chen",
        "email": "bob@techstart.demo",
        "company": "TechStart Inc",
        "tenant_id": "demo",
    },
    {
        "external_id": "demo-carol",
        "name": "Carol Dupont",
        "email": "carol@eurofinance.demo",
        "company": "EuroFinance SA",
        "tenant_id": "demo",
    },
    {
        "external_id": "oasis-mobile",
        "name": "OASIS Mobile",
        "email": "mobile@oasis.gostoa.dev",
        "company": "OASIS",
        "tenant_id": "oasis",
    },
    {
        "external_id": "gunter-analytics",
        "name": "Gunter Analytics",
        "email": "analytics@gunter.demo",
        "company": "Gunter Corp",
        "tenant_id": "oasis",
    },
]

STAGING_CONSUMERS: list[dict[str, Any]] = [
    {
        "external_id": "staging-alice",
        "name": "Alice Staging",
        "email": "alice@staging.gostoa.dev",
        "company": "Staging Corp",
        "tenant_id": "oasis",
    },
    {
        "external_id": "staging-bob",
        "name": "Bob Staging",
        "email": "bob@staging.gostoa.dev",
        "company": "Staging Corp",
        "tenant_id": "oasis",
    },
    {
        "external_id": "staging-carol",
        "name": "Carol Staging",
        "email": "carol@staging-test.gostoa.dev",
        "company": "Staging Test Corp",
        "tenant_id": "staging-test",
    },
    {
        "external_id": "staging-dave",
        "name": "Dave Staging",
        "email": "dave@staging-test.gostoa.dev",
        "company": "Staging Test Corp",
        "tenant_id": "staging-test",
    },
    {
        "external_id": "staging-eve",
        "name": "Eve Staging",
        "email": "eve@staging.gostoa.dev",
        "company": "Staging Corp",
        "tenant_id": "oasis",
    },
]

CONSUMERS_BY_PROFILE: dict[str, list[dict[str, Any]]] = {
    "dev": DEV_CONSUMERS,
    "staging": STAGING_CONSUMERS,
    "prod": [],
}


async def seed(session: AsyncSession, profile: str, *, dry_run: bool = False) -> StepResult:
    """Create consumers for the given profile."""
    consumers = CONSUMERS_BY_PROFILE[profile]
    result = StepResult(name="consumers")
    # consumers.created_at / updated_at are DateTime (tz-naive) in the ORM,
    # asyncpg rejects tz-aware datetimes against them. See fix notes in
    # scripts/seeder/steps/plans.py.
    now = datetime.now(UTC).replace(tzinfo=None)

    for c_def in consumers:
        row = await session.execute(
            text("SELECT COUNT(*) FROM consumers " "WHERE external_id = :eid AND tenant_id = :tid"),
            {"eid": c_def["external_id"], "tid": c_def["tenant_id"]},
        )
        if row.scalar_one() > 0:
            result.skipped += 1
            continue

        if dry_run:
            print(f"  [DRY-RUN] Would create consumer: {c_def['name']}")
            result.created += 1
            continue

        metadata = {"source": "seeder"}
        await session.execute(
            text("""
                INSERT INTO consumers (
                    id, external_id, name, email, company, tenant_id,
                    status, consumer_metadata, created_at, updated_at
                ) VALUES (
                    :id, :eid, :name, :email, :company, :tid,
                    'active', :metadata, :now, :now
                )
            """),
            {
                "id": uuid4(),
                "eid": c_def["external_id"],
                "name": c_def["name"],
                "email": c_def["email"],
                "company": c_def["company"],
                "tid": c_def["tenant_id"],
                "metadata": json.dumps(metadata),
                "now": now,
            },
        )
        result.created += 1
        print(f"  [STEP] consumers: created {c_def['name']}")

    return result


async def check(session: AsyncSession, profile: str) -> list[str]:
    """Check which consumers are missing."""
    consumers = CONSUMERS_BY_PROFILE[profile]
    missing = []
    for c_def in consumers:
        row = await session.execute(
            text("SELECT COUNT(*) FROM consumers " "WHERE external_id = :eid AND tenant_id = :tid"),
            {"eid": c_def["external_id"], "tid": c_def["tenant_id"]},
        )
        if row.scalar_one() == 0:
            missing.append(f"consumer:{c_def['external_id']}")
    return missing


async def reset(session: AsyncSession, profile: str) -> int:
    """Delete seeder-created consumers."""
    consumers = CONSUMERS_BY_PROFILE[profile]
    total = 0
    for c_def in consumers:
        row = await session.execute(
            text(
                "DELETE FROM consumers "
                "WHERE external_id = :eid AND tenant_id = :tid "
                "AND consumer_metadata->>'source' = 'seeder'"
            ),
            {"eid": c_def["external_id"], "tid": c_def["tenant_id"]},
        )
        total += getattr(row, "rowcount", 0) or 0
    return total
