"""Seed security posture demo data (CAB-2008).

Populates security_events and security_findings so the Security Posture
dashboard shows realistic data out of the box (dev/staging profiles).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.seeder.models import StepResult

SEEDER_TAG = "demo_seed"

# --- Security events (PG) — simulates Kafka-fed DORA alerts ---

_SECURITY_EVENTS: list[dict[str, Any]] = [
    {
        "event_type": "auth.failure",
        "severity": "warning",
        "source": "keycloak",
        "payload": {"reason": "invalid_credentials", "user": "test-user@oasis.dev", "ip": "10.0.0.42"},
        "hours_ago": 0.5,
    },
    {
        "event_type": "auth.failure",
        "severity": "warning",
        "source": "keycloak",
        "payload": {"reason": "account_locked", "user": "brute-force@attacker.net", "ip": "185.220.101.1"},
        "hours_ago": 1,
    },
    {
        "event_type": "rate_limit_exceeded",
        "severity": "warning",
        "source": "stoa-gateway",
        "payload": {"path": "/v1/tools/call", "consumer": "api-consumer-1", "limit": 100, "actual": 347},
        "hours_ago": 2,
    },
    {
        "event_type": "policy_violation",
        "severity": "error",
        "source": "stoa-gateway",
        "payload": {"policy": "cors-strict", "origin": "https://evil.com", "path": "/v1/mcp/tools/list"},
        "hours_ago": 3,
    },
    {
        "event_type": "unauthorized_access",
        "severity": "critical",
        "source": "stoa-gateway",
        "payload": {"path": "/admin/config", "method": "DELETE", "user": "viewer-role@oasis.dev"},
        "hours_ago": 6,
    },
    {
        "event_type": "certificate_expiring",
        "severity": "warning",
        "source": "cert-monitor",
        "payload": {"domain": "mcp.gostoa.dev", "days_remaining": 14},
        "hours_ago": 12,
    },
    {
        "event_type": "suspicious_payload",
        "severity": "error",
        "source": "guardrails",
        "payload": {"type": "sql_injection", "path": "/v1/apis", "pattern": "'; DROP TABLE --"},
        "hours_ago": 18,
    },
    {
        "event_type": "auth.failure",
        "severity": "warning",
        "source": "keycloak",
        "payload": {"reason": "expired_token", "user": "dev@oasis.dev", "ip": "10.0.0.5"},
        "hours_ago": 24,
    },
]

# --- Security findings (PG) — simulates scanner output ---

_SECURITY_FINDINGS: list[dict[str, Any]] = [
    {
        "scanner": "trivy",
        "severity": "high",
        "rule_id": "CVE-2024-6345",
        "rule_name": "setuptools: Remote code execution via download functions",
        "resource_type": "python-pkg",
        "resource_name": "setuptools@69.1.0",
        "description": "setuptools before 70.0 allows RCE via crafted package URLs.",
        "remediation": "Upgrade setuptools to >= 70.0",
    },
    {
        "scanner": "trivy",
        "severity": "medium",
        "rule_id": "CVE-2024-3651",
        "rule_name": "idna: Denial of service via resource consumption",
        "resource_type": "python-pkg",
        "resource_name": "idna@3.6",
        "description": "The idna package before 3.7 is vulnerable to DoS via long domain names.",
        "remediation": "Upgrade idna to >= 3.7",
    },
    {
        "scanner": "kubescape",
        "severity": "medium",
        "rule_id": "C-0034",
        "rule_name": "Automatic mapping of service account",
        "resource_type": "k8s-deployment",
        "resource_name": "control-plane-api",
        "description": "Service account token is automatically mounted. Set automountServiceAccountToken: false.",
        "remediation": "Add automountServiceAccountToken: false to pod spec.",
    },
    {
        "scanner": "kubescape",
        "severity": "low",
        "rule_id": "C-0009",
        "rule_name": "Resource limits not set",
        "resource_type": "k8s-deployment",
        "resource_name": "stoa-gateway",
        "description": "Container does not have CPU/memory limits configured.",
        "remediation": "Add resources.limits to container spec.",
    },
    {
        "scanner": "trivy",
        "severity": "critical",
        "rule_id": "CVE-2024-47554",
        "rule_name": "commons-io: Denial of service via XmlStreamReader",
        "resource_type": "java-jar",
        "resource_name": "commons-io@2.11.0",
        "description": "Apache Commons IO before 2.14.0 has a DoS via XmlStreamReader.",
        "remediation": "Upgrade commons-io to >= 2.14.0 (affects webMethods gateway).",
    },
]

EVENTS_BY_PROFILE: dict[str, list[dict]] = {
    "dev": _SECURITY_EVENTS,
    "staging": _SECURITY_EVENTS[:4],  # Fewer events for staging
    "prod": [],  # Never seed prod with fake security data
}

FINDINGS_BY_PROFILE: dict[str, list[dict]] = {
    "dev": _SECURITY_FINDINGS,
    "staging": _SECURITY_FINDINGS[:2],
    "prod": [],
}


async def seed(session: AsyncSession, profile: str, *, dry_run: bool = False) -> StepResult:
    """Seed security_events and security_findings for the Security Posture dashboard."""
    result = StepResult(name="security_posture")
    # security_events.created_at is DateTime (tz-naive); asyncpg rejects
    # tz-aware values. Use naive UTC — derived (now - timedelta) inherits it.
    now = datetime.now(UTC).replace(tzinfo=None)
    tenant_id = "oasis"
    scan_id = uuid4()

    # --- Security events ---
    events = EVENTS_BY_PROFILE.get(profile, [])
    for evt_def in events:
        # Check idempotent: skip if event_type + source + similar timestamp exists
        check = await session.execute(
            text(
                "SELECT COUNT(*) FROM security_events "
                "WHERE tenant_id = :tid AND event_type = :et AND source = :src "
                "AND payload::text LIKE :tag"
            ),
            {"tid": tenant_id, "et": evt_def["event_type"], "src": evt_def["source"], "tag": f"%{SEEDER_TAG}%"},
        )
        if check.scalar_one() > 0:
            result.skipped += 1
            continue

        if dry_run:
            print(f"  [DRY-RUN] Would create security_event: {evt_def['event_type']}")
            result.created += 1
            continue

        payload = {**evt_def["payload"], "source": SEEDER_TAG}
        created_at = now - timedelta(hours=evt_def.get("hours_ago", 0))

        await session.execute(
            text("""
                INSERT INTO security_events (
                    id, event_id, tenant_id, event_type, severity, source, payload, created_at
                ) VALUES (
                    :id, :event_id, :tid, :et, :sev, :src, :payload, :created_at
                )
            """),
            {
                "id": uuid4(),
                "event_id": uuid4(),
                "tid": tenant_id,
                "et": evt_def["event_type"],
                "sev": evt_def["severity"],
                "src": evt_def["source"],
                "payload": json.dumps(payload),
                "created_at": created_at,
            },
        )
        result.created += 1

    # --- Security scan record (parent for findings) ---
    findings = FINDINGS_BY_PROFILE.get(profile, [])
    if findings and not dry_run:
        scan_exists = await session.execute(
            text("SELECT COUNT(*) FROM security_scans " "WHERE tenant_id = :tid AND scanner = 'seeder'"),
            {"tid": tenant_id},
        )
        if scan_exists.scalar_one() == 0:
            await session.execute(
                text("""
                    INSERT INTO security_scans (
                        id, tenant_id, scanner, status, findings_count, score, started_at, completed_at
                    ) VALUES (
                        :id, :tid, 'seeder', 'completed', :cnt, NULL, :now, :now
                    )
                """),
                {"id": scan_id, "tid": tenant_id, "cnt": len(findings), "now": now},
            )
        else:
            row = await session.execute(
                text("SELECT id FROM security_scans WHERE tenant_id = :tid AND scanner = 'seeder' LIMIT 1"),
                {"tid": tenant_id},
            )
            scan_id = row.scalar_one()

    # --- Security findings ---
    for f_def in findings:
        check = await session.execute(
            text(
                "SELECT COUNT(*) FROM security_findings "
                "WHERE tenant_id = :tid AND rule_id = :rid AND scanner = :scanner"
            ),
            {"tid": tenant_id, "rid": f_def["rule_id"], "scanner": f_def["scanner"]},
        )
        if check.scalar_one() > 0:
            result.skipped += 1
            continue

        if dry_run:
            print(f"  [DRY-RUN] Would create security_finding: {f_def['rule_id']}")
            result.created += 1
            continue

        await session.execute(
            text("""
                INSERT INTO security_findings (
                    id, tenant_id, scan_id, scanner, severity, rule_id, title,
                    resource_type, resource_name, description, remediation,
                    details, status, created_at
                ) VALUES (
                    :id, :tid, :scan_id, :scanner, :sev, :rid, :title,
                    :rtype, :rname, :desc, :remed,
                    :details, 'open', :now
                )
            """),
            {
                "id": uuid4(),
                "tid": tenant_id,
                "scan_id": scan_id,
                "scanner": f_def["scanner"],
                "sev": f_def["severity"],
                "rid": f_def["rule_id"],
                "title": f_def["rule_name"],
                "rtype": f_def.get("resource_type"),
                "rname": f_def.get("resource_name"),
                "desc": f_def.get("description"),
                "remed": f_def.get("remediation"),
                "details": json.dumps({"source": SEEDER_TAG}),
                "now": now,
            },
        )
        result.created += 1

    return result


async def check(session: AsyncSession, profile: str) -> list[str]:
    """Check which security posture data is missing."""
    missing: list[str] = []

    events = EVENTS_BY_PROFILE.get(profile, [])
    if events:
        row = await session.execute(
            text("SELECT COUNT(*) FROM security_events WHERE tenant_id = 'oasis' AND payload::text LIKE :tag"),
            {"tag": f"%{SEEDER_TAG}%"},
        )
        if row.scalar_one() < len(events):
            missing.append("security_events:oasis (incomplete)")

    findings = FINDINGS_BY_PROFILE.get(profile, [])
    if findings:
        row = await session.execute(
            text("SELECT COUNT(*) FROM security_findings WHERE tenant_id = 'oasis'"),
        )
        if row.scalar_one() < len(findings):
            missing.append("security_findings:oasis (incomplete)")

    return missing


async def reset(session: AsyncSession, profile: str) -> int:
    """Delete seeder-created security posture data."""
    deleted = 0
    r1 = await session.execute(
        text("DELETE FROM security_findings WHERE details::text LIKE :tag"),
        {"tag": f"%{SEEDER_TAG}%"},
    )
    deleted += getattr(r1, "rowcount", 0) or 0

    r2 = await session.execute(
        text("DELETE FROM security_scans WHERE scanner = 'seeder'"),
    )
    deleted += getattr(r2, "rowcount", 0) or 0

    r3 = await session.execute(
        text("DELETE FROM security_events WHERE payload::text LIKE :tag"),
        {"tag": f"%{SEEDER_TAG}%"},
    )
    deleted += getattr(r3, "rowcount", 0) or 0

    return deleted
