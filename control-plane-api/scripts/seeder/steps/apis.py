"""Seed API catalog entries."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.seeder.models import StepResult

DEV_APIS: list[dict[str, Any]] = [
    {
        "api_id": "weather-api-v1",
        "api_name": "Weather API",
        "version": "1.0.0",
        "category": "data",
        "tags": ["weather", "forecast", "public"],
        "audience": "public",
        "tenant_id": "demo",
    },
    {
        "api_id": "crm-api-v2",
        "api_name": "CRM API",
        "version": "2.1.0",
        "category": "business",
        "tags": ["crm", "contacts", "internal"],
        "audience": "internal",
        "tenant_id": "demo",
    },
    {
        "api_id": "payments-api-v1",
        "api_name": "Payment Gateway API",
        "version": "1.3.0",
        "category": "financial",
        "tags": ["payments", "charges", "partner"],
        "audience": "partner",
        "tenant_id": "demo",
    },
    {
        "api_id": "petstore-v1",
        "api_name": "Petstore API",
        "version": "1.0.0",
        "category": "demo",
        "tags": ["demo", "petstore"],
        "audience": "public",
        "tenant_id": "oasis",
    },
    {
        "api_id": "account-mgmt-v1",
        "api_name": "Account Management API",
        "version": "2.0.0",
        "category": "business",
        "tags": ["accounts", "users"],
        "audience": "internal",
        "tenant_id": "oasis",
    },
    {
        "api_id": "notification-api-v1",
        "api_name": "Notification Service API",
        "version": "1.0.0",
        "category": "infrastructure",
        "tags": ["notifications", "email", "sms"],
        "audience": "internal",
        "tenant_id": "oasis",
    },
    {
        "api_id": "inventory-api-v1",
        "api_name": "Inventory API",
        "version": "1.2.0",
        "category": "business",
        "tags": ["inventory", "stock"],
        "audience": "partner",
        "tenant_id": "demo",
    },
    {
        "api_id": "auth-api-v1",
        "api_name": "Auth Service API",
        "version": "3.0.0",
        "category": "security",
        "tags": ["auth", "oauth2", "oidc"],
        "audience": "internal",
        "tenant_id": "oasis",
    },
    {
        "api_id": "analytics-api-v1",
        "api_name": "Analytics API",
        "version": "1.0.0",
        "category": "data",
        "tags": ["analytics", "metrics"],
        "audience": "internal",
        "tenant_id": "oasis",
    },
    {
        "api_id": "shipping-api-v1",
        "api_name": "Shipping API",
        "version": "1.1.0",
        "category": "logistics",
        "tags": ["shipping", "tracking"],
        "audience": "partner",
        "tenant_id": "demo",
    },
]

STAGING_APIS: list[dict[str, Any]] = [
    {
        "api_id": "petstore-v1",
        "api_name": "Petstore API",
        "version": "1.0.0",
        "category": "demo",
        "tags": ["demo", "petstore"],
        "audience": "public",
        "tenant_id": "oasis",
    },
    {
        "api_id": "weather-api-v1",
        "api_name": "Weather API",
        "version": "1.0.0",
        "category": "data",
        "tags": ["weather"],
        "audience": "public",
        "tenant_id": "oasis",
    },
    {
        "api_id": "crm-api-v2",
        "api_name": "CRM API",
        "version": "2.1.0",
        "category": "business",
        "tags": ["crm"],
        "audience": "internal",
        "tenant_id": "oasis",
    },
    {
        "api_id": "payments-api-v1",
        "api_name": "Payment Gateway API",
        "version": "1.3.0",
        "category": "financial",
        "tags": ["payments"],
        "audience": "partner",
        "tenant_id": "staging-test",
    },
    {
        "api_id": "account-mgmt-v1",
        "api_name": "Account Management API",
        "version": "2.0.0",
        "category": "business",
        "tags": ["accounts"],
        "audience": "internal",
        "tenant_id": "staging-test",
    },
]


APIS_BY_PROFILE: dict[str, list[dict[str, Any]]] = {
    "dev": DEV_APIS,
    "staging": STAGING_APIS,
    "prod": [],
}


async def seed(session: AsyncSession, profile: str, *, dry_run: bool = False) -> StepResult:
    """Create API catalog entries for the given profile."""
    apis = APIS_BY_PROFILE[profile]
    result = StepResult(name="apis")

    for api_def in apis:
        row = await session.execute(
            text(
                "SELECT COUNT(*) FROM api_catalog " "WHERE api_id = :api_id AND tenant_id = :tid AND deleted_at IS NULL"
            ),
            {"api_id": api_def["api_id"], "tid": api_def["tenant_id"]},
        )
        if row.scalar_one() > 0:
            result.skipped += 1
            continue

        if dry_run:
            print(f"  [DRY-RUN] Would create API: {api_def['api_name']}")
            result.created += 1
            continue

        metadata = {
            "source": "seeder",
            "name": api_def["api_name"],
            "version": api_def["version"],
        }
        await session.execute(
            text("""
                INSERT INTO api_catalog (
                    id, tenant_id, api_id, api_name, version, status,
                    category, tags, audience, portal_published, metadata
                ) VALUES (
                    :id, :tid, :api_id, :api_name, :version, 'active',
                    :category, :tags, :audience, true, :metadata
                )
            """),
            {
                "id": uuid4(),
                "tid": api_def["tenant_id"],
                "api_id": api_def["api_id"],
                "api_name": api_def["api_name"],
                "version": api_def["version"],
                "category": api_def["category"],
                "tags": json.dumps(api_def["tags"]),
                "audience": api_def["audience"],
                "metadata": json.dumps(metadata),
            },
        )
        result.created += 1
        print(f"  [STEP] apis: created {api_def['api_name']}")

    return result


async def check(session: AsyncSession, profile: str) -> list[str]:
    """Check which APIs are missing."""
    apis = APIS_BY_PROFILE[profile]
    missing = []
    for api_def in apis:
        row = await session.execute(
            text(
                "SELECT COUNT(*) FROM api_catalog " "WHERE api_id = :api_id AND tenant_id = :tid AND deleted_at IS NULL"
            ),
            {"api_id": api_def["api_id"], "tid": api_def["tenant_id"]},
        )
        if row.scalar_one() == 0:
            missing.append(f"api:{api_def['api_id']}")
    return missing


async def reset(session: AsyncSession, profile: str) -> int:
    """Delete seeder-created APIs."""
    apis = APIS_BY_PROFILE[profile]
    total = 0
    for api_def in apis:
        row = await session.execute(
            text(
                "DELETE FROM api_catalog "
                "WHERE api_id = :api_id AND tenant_id = :tid AND metadata->>'source' = 'seeder'"
            ),
            {"api_id": api_def["api_id"], "tid": api_def["tenant_id"]},
        )
        total += getattr(row, "rowcount", 0) or 0
    return total
