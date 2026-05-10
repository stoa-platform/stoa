"""Seed synthetic audit-log events for dev and demo staging only."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.seeder.models import StepResult

FIXTURE_BATCH = "observability-data-visibility-2026-05-09"
TARGET_TENANT_ID = "demo"
TARGET_EVENT_COUNT = 100
OPT_IN_ENV = "STOA_OBSERVABILITY_AUDIT_FIXTURES"
FIXTURE_PROFILE_ENV = "STOA_OBSERVABILITY_AUDIT_FIXTURE_PROFILE"
_PROD_VALUES = {"prod", "production"}
_TRUTHY_VALUES = {"1", "true", "yes", "on", "enabled"}
_VALID_FIXTURE_PROFILES = {"dev", "staging-demo", "staging-prodlike", "prod"}

SYNTHETIC_DETAILS = {
    "synthetic": True,
    "source": "seed",
    "fixture_batch": FIXTURE_BATCH,
}

_ACTIONS = [
    ("create", "POST", "api", 201),
    ("update", "PATCH", "api", 200),
    ("delete", "DELETE", "subscription", 204),
    ("login", "POST", "session", 200),
    ("logout", "POST", "session", 204),
    ("access_denied", "GET", "gateway", 403),
    ("config_change", "PATCH", "policy", 200),
    ("export", "GET", "audit", 200),
    ("deploy", "POST", "deployment", 202),
    ("chat_tool_call", "POST", "mcp_tool", 200),
]

_OUTCOMES = ["success", "failure", "denied", "error"]

_ACTORS = [
    ("demo-admin", "admin@demo.gostoa.dev", "user"),
    ("demo-devops", "devops@demo.gostoa.dev", "user"),
    ("demo-viewer", "viewer@demo.gostoa.dev", "user"),
    ("api-key-demo", None, "api_key"),
    ("system-seed", None, "system"),
]


def _env_value(name: str) -> str:
    return os.environ.get(name, "").strip().lower()


def _prod_environment_enabled() -> bool:
    return _env_value("ENVIRONMENT") in _PROD_VALUES or _env_value("STOA_ENVIRONMENT") in _PROD_VALUES


def _truthy_env(name: str) -> bool:
    return _env_value(name) in _TRUTHY_VALUES


def _fixture_profile(seed_profile: str) -> str:
    explicit = _env_value(FIXTURE_PROFILE_ENV)
    if explicit:
        profile = explicit
    elif seed_profile == "staging":
        profile = "staging-prodlike"
    else:
        profile = seed_profile

    if profile not in _VALID_FIXTURE_PROFILES:
        valid = ", ".join(sorted(_VALID_FIXTURE_PROFILES))
        raise ValueError(f"{FIXTURE_PROFILE_ENV}={profile!r} is invalid. Valid: {valid}")
    return profile


def _fixtures_enabled(seed_profile: str) -> bool:
    if _prod_environment_enabled():
        raise RuntimeError("Synthetic audit fixtures are forbidden when ENVIRONMENT is production/prod")

    profile = _fixture_profile(seed_profile)
    if profile == "prod":
        raise RuntimeError("Synthetic audit fixtures are forbidden in prod profile")
    if profile == "dev":
        return True
    if profile == "staging-demo":
        return _truthy_env(OPT_IN_ENV)
    if profile == "staging-prodlike":
        return False
    return False


def _event_id(index: int) -> str:
    return str(uuid5(NAMESPACE_URL, f"stoa:{FIXTURE_BATCH}:{TARGET_TENANT_ID}:{index}"))


def _event_payload(index: int, now: datetime) -> dict[str, Any]:
    action, method, resource_type, status_code = _ACTIONS[index % len(_ACTIONS)]
    outcome = _OUTCOMES[(index // len(_ACTIONS)) % len(_OUTCOMES)]
    actor_id, actor_email, actor_type = _ACTORS[index % len(_ACTORS)]
    resource_id = f"{resource_type}-{index % 25:02d}"
    created_at = now - timedelta(days=index % 30, minutes=(index * 17) % 1440)

    return {
        "id": _event_id(index),
        "tenant_id": TARGET_TENANT_ID,
        "actor_id": actor_id,
        "actor_email": actor_email,
        "actor_type": actor_type,
        "action": action,
        "method": method,
        "path": f"/v1/{resource_type}s/{resource_id}",
        "resource_type": resource_type,
        "resource_id": resource_id,
        "resource_name": f"Demo {resource_type} {index % 25:02d}",
        "outcome": outcome,
        "status_code": status_code if outcome == "success" else _failure_status(outcome),
        "client_ip": f"10.42.{index % 10}.{20 + index % 200}",
        "user_agent": "stoa-seeder/observability-fixtures",
        "correlation_id": str(uuid5(NAMESPACE_URL, f"stoa:{FIXTURE_BATCH}:correlation:{index}")),
        "details": json.dumps(SYNTHETIC_DETAILS, sort_keys=True),
        "duration_ms": 25 + (index * 13) % 750,
        "created_at": created_at,
    }


def _failure_status(outcome: str) -> int:
    if outcome == "denied":
        return 403
    if outcome == "error":
        return 500
    return 400


async def seed(session: AsyncSession, profile: str, *, dry_run: bool = False) -> StepResult:
    """Seed synthetic audit events for the configured non-production profile."""
    result = StepResult(name="observability_fixtures")
    if not _fixtures_enabled(profile):
        return result

    now = datetime.now(UTC)
    for index in range(TARGET_EVENT_COUNT):
        payload = _event_payload(index, now)
        existing = await session.execute(
            text("SELECT COUNT(*) FROM audit_events WHERE id = :id"),
            {"id": payload["id"]},
        )
        if existing.scalar_one() > 0:
            result.skipped += 1
            continue

        if dry_run:
            print(f"  [DRY-RUN] Would create synthetic audit_event: {payload['id']}")
            result.created += 1
            continue

        await session.execute(
            text("""
                INSERT INTO audit_events (
                    id, tenant_id, actor_id, actor_email, actor_type,
                    action, method, path, resource_type, resource_id, resource_name,
                    outcome, status_code, client_ip, user_agent, correlation_id,
                    details, duration_ms, created_at
                ) VALUES (
                    :id, :tenant_id, :actor_id, :actor_email, :actor_type,
                    :action, :method, :path, :resource_type, :resource_id, :resource_name,
                    :outcome, :status_code, :client_ip, :user_agent, :correlation_id,
                    CAST(:details AS jsonb), :duration_ms, :created_at
                )
            """),
            payload,
        )
        result.created += 1

    return result


async def check(session: AsyncSession, profile: str) -> list[str]:
    """Check whether the expected synthetic audit fixture batch exists."""
    if not _fixtures_enabled(profile):
        return []

    row = await session.execute(
        text("""
            SELECT COUNT(*) FROM audit_events
            WHERE tenant_id = :tenant_id
              AND details->>'synthetic' = 'true'
              AND details->>'source' = 'seed'
              AND details->>'fixture_batch' = :fixture_batch
        """),
        {"tenant_id": TARGET_TENANT_ID, "fixture_batch": FIXTURE_BATCH},
    )
    if row.scalar_one() < TARGET_EVENT_COUNT:
        return [f"audit_events:{TARGET_TENANT_ID}:{FIXTURE_BATCH} (incomplete)"]
    return []


async def reset(session: AsyncSession, profile: str) -> int:
    """Delete only the synthetic audit fixture batch."""
    if not _fixtures_enabled(profile):
        return 0

    result = await session.execute(
        text("""
            DELETE FROM audit_events
            WHERE tenant_id = :tenant_id
              AND details->>'synthetic' = 'true'
              AND details->>'source' = 'seed'
              AND details->>'fixture_batch' = :fixture_batch
        """),
        {"tenant_id": TARGET_TENANT_ID, "fixture_batch": FIXTURE_BATCH},
    )
    return getattr(result, "rowcount", 0) or 0
