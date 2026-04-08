"""Seed demo prospects (dev profile only)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.seeder.models import StepResult

DEV_PROSPECTS: list[dict[str, Any]] = [
    {"email": "jean.dupont@enterprise.fr", "company": "Enterprise SA", "status": "converted", "source": "demo_seed"},
    {"email": "marie.curie@research.eu", "company": "Research EU", "status": "opened", "source": "demo_seed"},
    {"email": "hans.mueller@techgmbh.de", "company": "TechGmbH", "status": "pending", "source": "demo_seed"},
    {"email": "sofia.rossi@finanza.it", "company": "Finanza IT", "status": "converted", "source": "demo_seed"},
    {"email": "james.smith@cloudco.uk", "company": "CloudCo UK", "status": "expired", "source": "demo_seed"},
    {"email": "li.wei@techasia.cn", "company": "TechAsia", "status": "opened", "source": "demo_seed"},
    {"email": "anna.svensson@nordicapi.se", "company": "Nordic API", "status": "pending", "source": "demo_seed"},
    {"email": "carlos.garcia@apilatam.mx", "company": "API Latam", "status": "converted", "source": "demo_seed"},
    {"email": "priya.sharma@indiatech.in", "company": "IndiaTech", "status": "opened", "source": "demo_seed"},
    {"email": "olga.petrov@rusdev.ru", "company": "RusDev", "status": "pending", "source": "demo_seed"},
    {"email": "ahmed.hassan@mideast.ae", "company": "MidEast Tech", "status": "converted", "source": "demo_seed"},
    {"email": "yuki.tanaka@jptech.jp", "company": "JP Tech", "status": "opened", "source": "demo_seed"},
]

PROSPECTS_BY_PROFILE: dict[str, list[dict[str, Any]]] = {
    "dev": DEV_PROSPECTS,
    "staging": [],
    "prod": [],
}


async def seed(session: AsyncSession, profile: str, *, dry_run: bool = False) -> StepResult:
    """Create prospects for the given profile."""
    prospects = PROSPECTS_BY_PROFILE[profile]
    result = StepResult(name="prospects")
    now = datetime.now(UTC)

    for p_def in prospects:
        row = await session.execute(
            text("SELECT COUNT(*) FROM prospects WHERE email = :email"),
            {"email": p_def["email"]},
        )
        if row.scalar_one() > 0:
            result.skipped += 1
            continue

        if dry_run:
            print(f"  [DRY-RUN] Would create prospect: {p_def['email']}")
            result.created += 1
            continue

        await session.execute(
            text("""
                INSERT INTO prospects (
                    id, email, company, status, source, metadata, created_at, updated_at
                ) VALUES (
                    :id, :email, :company, :status, :source, :metadata, :now, :now
                )
            """),
            {
                "id": uuid4(),
                "email": p_def["email"],
                "company": p_def["company"],
                "status": p_def["status"],
                "source": p_def["source"],
                "metadata": json.dumps({"source": "seeder"}),
                "now": now,
            },
        )
        result.created += 1

    if result.created > 0:
        print(f"  [STEP] prospects: created {result.created}")

    return result


async def check(session: AsyncSession, profile: str) -> list[str]:
    """Check which prospects are missing."""
    prospects = PROSPECTS_BY_PROFILE[profile]
    missing = []
    for p_def in prospects:
        row = await session.execute(
            text("SELECT COUNT(*) FROM prospects WHERE email = :email"),
            {"email": p_def["email"]},
        )
        if row.scalar_one() == 0:
            missing.append(f"prospect:{p_def['email']}")
    return missing


async def reset(session: AsyncSession, profile: str) -> int:
    """Delete seeder-created prospects."""
    row = await session.execute(text("DELETE FROM prospects WHERE source = 'demo_seed'"))
    return getattr(row, "rowcount", 0) or 0
