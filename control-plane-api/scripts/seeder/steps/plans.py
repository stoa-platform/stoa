"""Seed subscription plans."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.seeder.models import StepResult

DEV_PLANS: list[dict[str, Any]] = [
    {
        "slug": "standard",
        "name": "Standard",
        "description": "Standard plan — 10 requests/second.",
        "tenant_id": "oasis",
        "rate_limit_per_second": 10,
        "rate_limit_per_minute": 600,
        "daily_request_limit": 50000,
        "monthly_request_limit": 1000000,
    },
    {
        "slug": "premium",
        "name": "Premium",
        "description": "Premium plan — 50 requests/second, approval required.",
        "tenant_id": "oasis",
        "rate_limit_per_second": 50,
        "rate_limit_per_minute": 3000,
        "daily_request_limit": 500000,
        "monthly_request_limit": 10000000,
        "requires_approval": True,
    },
    {
        "slug": "alpha-exploration",
        "name": "Alpha Exploration",
        "description": "Alpha tier — 1000 tokens/min for exploration.",
        "tenant_id": "demo",
        "rate_limit_per_second": 5,
        "rate_limit_per_minute": 100,
        "daily_request_limit": 10000,
        "monthly_request_limit": 100000,
    },
    {
        "slug": "beta-production",
        "name": "Beta Production",
        "description": "Beta tier — 5000 tokens/min for production use.",
        "tenant_id": "demo",
        "rate_limit_per_second": 20,
        "rate_limit_per_minute": 500,
        "daily_request_limit": 100000,
        "monthly_request_limit": 2000000,
    },
]

STAGING_PLANS: list[dict[str, Any]] = [
    {
        "slug": "standard",
        "name": "Standard",
        "description": "Standard plan for staging validation.",
        "tenant_id": "oasis",
        "rate_limit_per_second": 10,
        "rate_limit_per_minute": 600,
        "daily_request_limit": 50000,
        "monthly_request_limit": 1000000,
    },
    {
        "slug": "premium",
        "name": "Premium",
        "description": "Premium plan for staging validation.",
        "tenant_id": "oasis",
        "rate_limit_per_second": 50,
        "rate_limit_per_minute": 3000,
        "daily_request_limit": 500000,
        "monthly_request_limit": 10000000,
        "requires_approval": True,
    },
    {
        "slug": "test-plan",
        "name": "Test Plan",
        "description": "Staging-only test plan.",
        "tenant_id": "staging-test",
        "rate_limit_per_second": 5,
        "rate_limit_per_minute": 100,
        "daily_request_limit": 10000,
        "monthly_request_limit": 100000,
    },
]

PLANS_BY_PROFILE: dict[str, list[dict[str, Any]]] = {
    "dev": DEV_PLANS,
    "staging": STAGING_PLANS,
    "prod": [],
}


async def seed(session: AsyncSession, profile: str, *, dry_run: bool = False) -> StepResult:
    """Create plans for the given profile."""
    plans = PLANS_BY_PROFILE[profile]
    result = StepResult(name="plans")
    now = datetime.now(UTC)

    for plan_def in plans:
        row = await session.execute(
            text("SELECT COUNT(*) FROM plans WHERE slug = :slug AND tenant_id = :tid"),
            {"slug": plan_def["slug"], "tid": plan_def["tenant_id"]},
        )
        if row.scalar_one() > 0:
            result.skipped += 1
            continue

        if dry_run:
            print(f"  [DRY-RUN] Would create plan: {plan_def['name']}")
            result.created += 1
            continue

        pricing_metadata = {"source": "seeder"}
        await session.execute(
            text("""
                INSERT INTO plans (
                    id, slug, name, description, tenant_id,
                    rate_limit_per_second, rate_limit_per_minute,
                    daily_request_limit, monthly_request_limit,
                    requires_approval, status, pricing_metadata, created_at, updated_at
                ) VALUES (
                    :id, :slug, :name, :desc, :tid,
                    :rps, :rpm, :daily, :monthly,
                    :approval, 'active', :pricing, :now, :now
                )
            """),
            {
                "id": uuid4(),
                "slug": plan_def["slug"],
                "name": plan_def["name"],
                "desc": plan_def["description"],
                "tid": plan_def["tenant_id"],
                "rps": plan_def["rate_limit_per_second"],
                "rpm": plan_def["rate_limit_per_minute"],
                "daily": plan_def["daily_request_limit"],
                "monthly": plan_def["monthly_request_limit"],
                "approval": plan_def.get("requires_approval", False),
                "pricing": json.dumps(pricing_metadata),
                "now": now,
            },
        )
        result.created += 1
        print(f"  [STEP] plans: created {plan_def['name']} ({plan_def['tenant_id']})")

    return result


async def check(session: AsyncSession, profile: str) -> list[str]:
    """Check which plans are missing."""
    plans = PLANS_BY_PROFILE[profile]
    missing = []
    for plan_def in plans:
        row = await session.execute(
            text("SELECT COUNT(*) FROM plans WHERE slug = :slug AND tenant_id = :tid"),
            {"slug": plan_def["slug"], "tid": plan_def["tenant_id"]},
        )
        if row.scalar_one() == 0:
            missing.append(f"plan:{plan_def['slug']}")
    return missing


async def reset(session: AsyncSession, profile: str) -> int:
    """Delete seeder-created plans."""
    plans = PLANS_BY_PROFILE[profile]
    total = 0
    for plan_def in plans:
        row = await session.execute(
            text(
                "DELETE FROM plans WHERE slug = :slug AND tenant_id = :tid "
                "AND pricing_metadata->>'source' = 'seeder'"
            ),
            {"slug": plan_def["slug"], "tid": plan_def["tenant_id"]},
        )
        total += getattr(row, "rowcount", 0) or 0
    return total
