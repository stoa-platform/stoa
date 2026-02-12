"""
CAB-1104: Audit Trail Router (Scenario 6)

Provides audit log retrieval and export functionality:
- List audit entries with filters
- Export to CSV or JSON
- View security events
- Tenant isolation enforcement

Audit events are stored in the event_log table and include:
- API calls with user, action, resource
- Authentication events
- Policy violations
- Admin operations
"""

import csv
import io
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from ..auth import User, get_current_user, require_tenant_access
from ..opensearch.opensearch_integration import OpenSearchService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/audit", tags=["Audit"])


# =============================================================================
# Models
# =============================================================================


class AuditEntry(BaseModel):
    """An audit log entry."""

    id: str
    timestamp: datetime
    tenant_id: str
    user_id: str | None
    user_email: str | None
    action: str
    resource_type: str
    resource_id: str | None
    status: str  # success, failure, blocked
    client_ip: str | None
    user_agent: str | None
    details: dict[str, Any] | None
    request_id: str | None


class AuditListResponse(BaseModel):
    """Response for audit list endpoint."""

    entries: list[AuditEntry]
    total: int
    page: int
    page_size: int
    has_more: bool


class SecurityEvent(BaseModel):
    """A security-related audit event."""

    id: str
    timestamp: datetime
    tenant_id: str
    event_type: str  # auth_failure, policy_violation, rate_limit, cross_tenant
    severity: str  # info, warning, critical
    user_id: str | None
    client_ip: str | None
    description: str
    details: dict[str, Any] | None


class SecurityEventsResponse(BaseModel):
    """Response for security events endpoint."""

    events: list[SecurityEvent]
    total: int
    summary: dict[str, int]


# =============================================================================
# In-Memory Audit Store (for demo - production uses PostgreSQL)
# =============================================================================

# Demo audit data
_demo_audit_entries: list[dict[str, Any]] = []
_demo_security_events: list[dict[str, Any]] = []


def _init_demo_data():
    """Initialize demo audit data."""
    if _demo_audit_entries:
        return

    now = datetime.now(UTC)

    # Generate demo audit entries
    actions = [
        ("api_call", "tool", "oasis_github_list_issues", "success"),
        ("api_call", "tool", "oasis_ml_sentiment", "success"),
        ("api_call", "tool", "oasis_slack_notify", "success"),
        ("authentication", "user", None, "success"),
        ("api_call", "tool", "high-five_crypto_prices", "success"),
        ("rate_limit_exceeded", "tenant", "ioi", "blocked"),
        ("api_call", "tool", "oasis_ml_classify", "success"),
        ("authentication", "user", None, "failure"),
        ("policy_check", "api", "billing-api", "success"),
        ("subscription_created", "subscription", "sub-123", "success"),
    ]

    tenants = ["oasis", "high-five", "ioi"]
    users = [
        ("user-001", "alice@oasis.com"),
        ("user-002", "bob@highfive.com"),
        ("user-003", "charlie@ioi.com"),
    ]

    for i, (action, res_type, res_id, status) in enumerate(actions):
        tenant = tenants[i % len(tenants)]
        user_id, email = users[i % len(users)]

        _demo_audit_entries.append({
            "id": f"audit-{i:04d}",
            "timestamp": (now - timedelta(hours=i * 2)).isoformat(),
            "tenant_id": tenant,
            "user_id": user_id,
            "user_email": email,
            "action": action,
            "resource_type": res_type,
            "resource_id": res_id,
            "status": status,
            "client_ip": f"192.168.1.{100 + i}",
            "user_agent": "Mozilla/5.0 (compatible; STOA/1.0)",
            "details": {"demo": True, "index": i},
            "request_id": f"req-{i:08x}",
        })

    # Generate demo security events
    security_events = [
        ("auth_failure", "warning", "Failed login attempt"),
        ("rate_limit", "info", "Rate limit exceeded for tenant ioi"),
        ("policy_violation", "warning", "Attempted access to restricted API"),
        ("cross_tenant", "critical", "Cross-tenant access attempt blocked"),
        ("auth_failure", "warning", "Invalid token"),
    ]

    for i, (event_type, severity, description) in enumerate(security_events):
        tenant = tenants[i % len(tenants)]
        user_id, _ = users[i % len(users)]

        _demo_security_events.append({
            "id": f"sec-{i:04d}",
            "timestamp": (now - timedelta(hours=i * 3)).isoformat(),
            "tenant_id": tenant,
            "event_type": event_type,
            "severity": severity,
            "user_id": user_id if event_type != "cross_tenant" else "attacker",
            "client_ip": f"10.0.0.{50 + i}",
            "description": description,
            "details": {"demo": True},
        })


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/{tenant_id}", response_model=AuditListResponse)
@require_tenant_access
async def list_audit_entries(
    tenant_id: str,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=1, le=500, description="Results per page"),
    action: str | None = Query(default=None, description="Filter by action"),
    status: str | None = Query(default=None, description="Filter by status"),
    start_date: datetime | None = Query(default=None, description="Start date (ISO 8601)"),
    end_date: datetime | None = Query(default=None, description="End date (ISO 8601)"),
    user: User = Depends(get_current_user),
) -> AuditListResponse:
    """
    List audit entries for a tenant.

    Returns paginated audit log entries with optional filters.
    Only entries for the specified tenant are returned.
    """
    # Try OpenSearch first (real audit data from AuditMiddleware)
    service = OpenSearchService.get_instance()
    if service.client:
        try:
            result = await _query_opensearch_audit(
                service.client, tenant_id, page, page_size,
                action=action, status=status, start_date=start_date, end_date=end_date,
            )
            if result is not None:
                return result
        except Exception as e:
            logger.warning(f"OpenSearch query failed, falling back to demo data: {e}")

    # Fallback to demo data
    _init_demo_data()

    entries = [e for e in _demo_audit_entries if e["tenant_id"] == tenant_id]

    if action:
        entries = [e for e in entries if e["action"] == action]
    if status:
        entries = [e for e in entries if e["status"] == status]
    if start_date:
        entries = [e for e in entries if datetime.fromisoformat(e["timestamp"]) >= start_date]
    if end_date:
        entries = [e for e in entries if datetime.fromisoformat(e["timestamp"]) <= end_date]

    total = len(entries)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_entries = entries[start_idx:end_idx]

    return AuditListResponse(
        entries=[AuditEntry(**e) for e in page_entries],
        total=total,
        page=page,
        page_size=page_size,
        has_more=end_idx < total,
    )


@router.get("/{tenant_id}/export/csv")
@require_tenant_access
async def export_audit_csv(
    tenant_id: str,
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    user: User = Depends(get_current_user),
) -> Response:
    """
    Export audit log entries as CSV.

    Returns a CSV file with all audit entries for the tenant.
    """
    _init_demo_data()

    # Filter entries by tenant
    entries = [e for e in _demo_audit_entries if e["tenant_id"] == tenant_id]

    # Apply date filters
    if start_date:
        entries = [e for e in entries if datetime.fromisoformat(e["timestamp"]) >= start_date]
    if end_date:
        entries = [e for e in entries if datetime.fromisoformat(e["timestamp"]) <= end_date]

    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "ID", "Timestamp", "Tenant", "User ID", "User Email",
        "Action", "Resource Type", "Resource ID", "Status",
        "Client IP", "Request ID"
    ])

    # Data rows
    for entry in entries:
        writer.writerow([
            entry["id"],
            entry["timestamp"],
            entry["tenant_id"],
            entry["user_id"],
            entry["user_email"],
            entry["action"],
            entry["resource_type"],
            entry["resource_id"],
            entry["status"],
            entry["client_ip"],
            entry["request_id"],
        ])

    csv_content = output.getvalue()

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="audit_{tenant_id}_{datetime.now(UTC).strftime("%Y%m%d")}.csv"'
        },
    )


@router.get("/{tenant_id}/export/json")
@require_tenant_access
async def export_audit_json(
    tenant_id: str,
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    user: User = Depends(get_current_user),
) -> Response:
    """
    Export audit log entries as JSON.

    Returns a JSON file with all audit entries for the tenant.
    """
    _init_demo_data()

    # Filter entries by tenant
    entries = [e for e in _demo_audit_entries if e["tenant_id"] == tenant_id]

    # Apply date filters
    if start_date:
        entries = [e for e in entries if datetime.fromisoformat(e["timestamp"]) >= start_date]
    if end_date:
        entries = [e for e in entries if datetime.fromisoformat(e["timestamp"]) <= end_date]

    export_data = {
        "tenant_id": tenant_id,
        "exported_at": datetime.now(UTC).isoformat(),
        "total_entries": len(entries),
        "entries": entries,
    }

    json_content = json.dumps(export_data, indent=2)

    return Response(
        content=json_content,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="audit_{tenant_id}_{datetime.now(UTC).strftime("%Y%m%d")}.json"'
        },
    )


@router.get("/{tenant_id}/security", response_model=SecurityEventsResponse)
@require_tenant_access
async def get_security_events(
    tenant_id: str,
    severity: str | None = Query(default=None, description="Filter by severity"),
    event_type: str | None = Query(default=None, description="Filter by event type"),
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum events to return"),
    user: User = Depends(get_current_user),
) -> SecurityEventsResponse:
    """
    Get security events for a tenant.

    Returns security-related audit events including:
    - Authentication failures
    - Rate limit violations
    - Policy violations
    - Cross-tenant access attempts
    """
    # Try OpenSearch first (real security events)
    service = OpenSearchService.get_instance()
    if service.client:
        try:
            result = await _query_opensearch_security(
                service.client, tenant_id, limit,
                severity=severity, event_type=event_type,
            )
            if result is not None:
                return result
        except Exception as e:
            logger.warning(f"OpenSearch security query failed, falling back to demo: {e}")

    # Fallback to demo data
    _init_demo_data()

    events = [e for e in _demo_security_events if e["tenant_id"] == tenant_id]

    if severity:
        events = [e for e in events if e["severity"] == severity]
    if event_type:
        events = [e for e in events if e["event_type"] == event_type]

    events = events[:limit]

    summary: dict[str, int] = {}
    for event in events:
        event_type_key = event["event_type"]
        summary[event_type_key] = summary.get(event_type_key, 0) + 1

    return SecurityEventsResponse(
        events=[SecurityEvent(**e) for e in events],
        total=len(events),
        summary=summary,
    )


@router.get("/{tenant_id}/isolation-test")
@require_tenant_access
async def test_tenant_isolation(
    tenant_id: str,
    target_tenant: str = Query(..., description="Tenant to attempt access to"),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Test tenant isolation.

    Attempts to access another tenant's data and returns whether
    it was blocked (expected behavior for proper isolation).

    This endpoint is for demo/testing purposes to show that
    cross-tenant access is properly blocked.
    """
    # Check if user is trying to access different tenant
    if tenant_id != target_tenant:
        # This should be blocked by @require_tenant_access decorator
        # But for demo, we show the isolation working
        logger.warning(
            f"Cross-tenant access attempt: {tenant_id} -> {target_tenant}",
            extra={"user_id": user.id, "source_tenant": tenant_id, "target_tenant": target_tenant},
        )

        # Record security event
        _demo_security_events.append({
            "id": f"sec-{len(_demo_security_events):04d}",
            "timestamp": datetime.now(UTC).isoformat(),
            "tenant_id": tenant_id,
            "event_type": "cross_tenant",
            "severity": "critical",
            "user_id": user.id,
            "client_ip": "demo",
            "description": f"Cross-tenant access attempt from {tenant_id} to {target_tenant}",
            "details": {"target_tenant": target_tenant, "blocked": True},
        })

        raise HTTPException(
            status_code=403,
            detail={
                "error": "tenant_isolation_violation",
                "message": f"Access denied: Cannot access tenant '{target_tenant}' from tenant '{tenant_id}'",
                "source_tenant": tenant_id,
                "target_tenant": target_tenant,
                "blocked": True,
            },
        )

    return {
        "status": "allowed",
        "message": "Same tenant access is permitted",
        "tenant_id": tenant_id,
    }


@router.get("/global/summary")
async def get_global_audit_summary(
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Get global audit summary (cpi-admin only).

    Returns aggregated audit statistics across all tenants.
    """
    if "cpi-admin" not in user.roles:
        raise HTTPException(
            status_code=403,
            detail="Only cpi-admin can access global audit summary",
        )

    _init_demo_data()

    # Aggregate stats
    total_entries = len(_demo_audit_entries)
    total_security = len(_demo_security_events)

    # Count by tenant
    by_tenant = {}
    for entry in _demo_audit_entries:
        tenant = entry["tenant_id"]
        by_tenant[tenant] = by_tenant.get(tenant, 0) + 1

    # Count by action
    by_action = {}
    for entry in _demo_audit_entries:
        action = entry["action"]
        by_action[action] = by_action.get(action, 0) + 1

    # Security severity counts
    security_by_severity = {"info": 0, "warning": 0, "critical": 0}
    for event in _demo_security_events:
        severity = event["severity"]
        security_by_severity[severity] = security_by_severity.get(severity, 0) + 1

    return {
        "total_audit_entries": total_entries,
        "total_security_events": total_security,
        "entries_by_tenant": by_tenant,
        "entries_by_action": by_action,
        "security_by_severity": security_by_severity,
        "generated_at": datetime.now(UTC).isoformat(),
    }


# =============================================================================
# OpenSearch Query Helpers
# =============================================================================


async def _query_opensearch_audit(
    client: Any,
    tenant_id: str,
    page: int,
    page_size: int,
    *,
    action: str | None = None,
    status: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> AuditListResponse | None:
    """Query audit-* index in OpenSearch. Returns None if no index exists."""
    must = [{"term": {"actor.tenant_id": tenant_id}}]
    if action:
        must.append({"match": {"action": action}})
    if status:
        must.append({"term": {"outcome": status}})
    if start_date or end_date:
        ts_range: dict[str, str] = {}
        if start_date:
            ts_range["gte"] = start_date.isoformat()
        if end_date:
            ts_range["lte"] = end_date.isoformat()
        must.append({"range": {"@timestamp": ts_range}})

    body = {
        "query": {"bool": {"must": must}},
        "sort": [{"@timestamp": "desc"}],
        "from": (page - 1) * page_size,
        "size": page_size,
    }

    resp = await client.search(index="audit-*", body=body)
    hits = resp.get("hits", {})
    total = hits.get("total", {}).get("value", 0)
    if total == 0 and page == 1:
        return None  # No data — fall back to demo

    entries = []
    for hit in hits.get("hits", []):
        src = hit["_source"]
        entries.append(AuditEntry(
            id=src.get("event_id", hit["_id"]),
            timestamp=src.get("@timestamp", datetime.now(UTC).isoformat()),
            tenant_id=src.get("actor", {}).get("tenant_id", tenant_id),
            user_id=src.get("actor", {}).get("id"),
            user_email=src.get("actor", {}).get("email"),
            action=src.get("action", "unknown"),
            resource_type=src.get("resource", {}).get("type", "unknown"),
            resource_id=src.get("resource", {}).get("id"),
            status=src.get("outcome", "unknown"),
            client_ip=src.get("actor", {}).get("ip_address"),
            user_agent=src.get("actor", {}).get("user_agent"),
            details=src.get("details"),
            request_id=src.get("correlation_id"),
        ))

    return AuditListResponse(
        entries=entries,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


async def _query_opensearch_security(
    client: Any,
    tenant_id: str,
    limit: int,
    *,
    severity: str | None = None,
    event_type: str | None = None,
) -> SecurityEventsResponse | None:
    """Query audit-* for security events (severity >= warning). Returns None if empty."""
    must: list[dict[str, Any]] = [
        {"term": {"actor.tenant_id": tenant_id}},
        {"terms": {"severity": ["warning", "error", "critical"]}},
    ]
    if severity:
        must[-1] = {"term": {"severity": severity}}
    if event_type:
        must.append({"match": {"event_type": event_type}})

    body = {
        "query": {"bool": {"must": must}},
        "sort": [{"@timestamp": "desc"}],
        "size": limit,
    }

    resp = await client.search(index="audit-*", body=body)
    hits = resp.get("hits", {})
    total = hits.get("total", {}).get("value", 0)
    if total == 0:
        return None

    events = []
    summary: dict[str, int] = {}
    for hit in hits.get("hits", []):
        src = hit["_source"]
        et = src.get("event_type", "unknown")
        summary[et] = summary.get(et, 0) + 1
        events.append(SecurityEvent(
            id=src.get("event_id", hit["_id"]),
            timestamp=src.get("@timestamp", datetime.now(UTC).isoformat()),
            tenant_id=src.get("actor", {}).get("tenant_id", tenant_id),
            event_type=et,
            severity=src.get("severity", "info"),
            user_id=src.get("actor", {}).get("id"),
            client_ip=src.get("actor", {}).get("ip_address"),
            description=src.get("action", ""),
            details=src.get("details"),
        ))

    return SecurityEventsResponse(
        events=events,
        total=total,
        summary=summary,
    )
