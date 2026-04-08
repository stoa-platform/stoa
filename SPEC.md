# Spec: CAB-2008 — Unify Security Posture Data Sources

## Problem

The Security Posture dashboard shows all zeros because it reads exclusively from the `security_findings` table, which is only populated via a manual `POST /findings/ingest` endpoint (no scanner exists). Meanwhile, real security data lives in 3 disconnected silos: OpenSearch `audit-*` indices (auth failures, rate limits, policy violations), PostgreSQL `security_events` table (Kafka-fed DORA alerts), and the empty `security_findings` table (scanner push model).

## Goal

The `/v1/security/{tenant}/score` and `/v1/security/{tenant}/findings` endpoints return real security data by aggregating all 3 sources. The security score reflects actual security posture — not 100 when no scanner data exists. A data freshness indicator warns when no recent data is available.

## API Contract

### GET /v1/security/{tenant_id}/score

Response adds 1 new field `data_freshness` (backward-compatible):

```json
{
  "tenant_id": "string",
  "score": 72.5,
  "grade": "C",
  "findings_summary": { "critical": 0, "high": 2, "medium": 5, "low": 3, "info": 1 },
  "total_findings": 11,
  "open_findings": 10,
  "last_scan_at": "2026-04-08T12:00:00Z",
  "trend": -2.5,
  "data_freshness": {
    "last_data_at": "2026-04-08T11:55:00Z",
    "status": "fresh",
    "sources": {
      "opensearch_audit": { "last_event_at": "2026-04-08T11:55:00Z", "count": 42 },
      "pg_security_events": { "last_event_at": "2026-04-08T10:30:00Z", "count": 7 },
      "pg_security_findings": { "last_event_at": null, "count": 0 }
    }
  }
}
```

`data_freshness.status` values: `"fresh"` (data < 1h), `"stale"` (1h-24h), `"no_data"` (> 24h or empty).

### GET /v1/security/{tenant_id}/findings

Response shape unchanged. `findings` list now includes derived findings from audit events and security_events, with `scanner` field set to `"audit"` or `"security_event"` respectively.

```json
{
  "findings": [
    {
      "id": "derived-audit-abc123",
      "tenant_id": "oasis",
      "scan_id": "aggregated",
      "scanner": "audit",
      "severity": "high",
      "rule_id": "AUTH_FAILURE_SPIKE",
      "rule_name": "Authentication failure spike",
      "resource_type": "auth",
      "resource_name": "/v1/auth/token",
      "description": "12 auth failures in last hour from 3 IPs",
      "status": "open",
      "created_at": "2026-04-08T11:55:00Z"
    }
  ],
  "total": 15,
  "page": 1,
  "page_size": 50,
  "has_more": false
}
```

### POST /v1/security/{tenant_id}/findings/ingest — UNCHANGED

Push model preserved for future Trivy/Kubescape integration.

## Acceptance Criteria

- [ ] AC1: When OpenSearch has audit events with severity >= warning for a tenant, `GET /score` includes them in the penalty calculation
- [ ] AC2: When `security_events` table has events for a tenant, `GET /score` includes them in the penalty calculation
- [ ] AC3: When all 3 sources are empty for a tenant, score is 0 (not 100) and `data_freshness.status` is `"no_data"`
- [ ] AC4: `GET /findings` returns derived findings from OpenSearch audit events alongside scanner findings, with `scanner="audit"`
- [ ] AC5: `GET /findings` returns derived findings from PG `security_events`, with `scanner="security_event"`
- [ ] AC6: `data_freshness` object is present in score response with per-source breakdown
- [ ] AC7: `data_freshness.status` is `"fresh"` when most recent event < 1 hour old
- [ ] AC8: `data_freshness.status` is `"stale"` when most recent event is 1h-24h old
- [ ] AC9: `POST /findings/ingest` still works — existing push model unbroken
- [ ] AC10: Pagination and severity/status filters work across all sources in `GET /findings`

## Edge Cases

| Case | Input | Expected | Priority |
|------|-------|----------|----------|
| OpenSearch unavailable | Connection timeout | Graceful degradation: score from PG sources only, `opensearch_audit.count = -1` | Must |
| No audit events, only scanner findings | Empty OS, populated `security_findings` | Score uses scanner findings only (current behavior preserved) | Must |
| Severity mapping mismatch | OS `"warning"` vs PG `"medium"` | Normalize: OS `warning` -> `medium`, OS `error` -> `high`, OS `critical` -> `critical` | Must |
| Duplicate events across sources | Same event in OS + PG `security_events` | Deduplicate by `correlation_id` / `event_id` | Should |
| Very large audit-* result set | 10K+ events in OS | Cap aggregation query to last 1000 events, use `aggs` for counts | Must |
| Tenant with no data in any source | New tenant, zero events | Score = 0, grade = "F", `data_freshness.status = "no_data"` | Must |
| Mixed freshness across sources | OS: 5min ago, PG events: 3 days ago, findings: never | `status = "fresh"` (uses most recent across all sources) | Must |

## Out of Scope

- Trivy/Kubescape scanner integration (future ticket)
- Frontend UI changes (current UI consumes the same response shape)
- OpenSearch infrastructure changes (indices, mappings, retention)
- Kafka topic schema changes
- Real-time streaming aggregation (this is request-time aggregation)

## Security Considerations

- [x] Auth required: `@require_tenant_access` decorator (existing)
- [x] Tenant isolation: OpenSearch queries MUST include `tenant_id` filter (already the case in `_query_opensearch_security`)
- [ ] No PII in derived findings: audit events may contain `actor.email` — strip from finding `description`
- [ ] Rate limiting: aggregation queries are heavier than pure PG — consider caching score for 60s

## Dependencies

- OpenSearch `audit-*` indices populated by `AuditMiddleware` (already running)
- PostgreSQL `security_events` table populated by Kafka consumer (already running)
- `_query_opensearch_security()` helper in `routers/audit.py` (reusable query pattern)

## Notes

- New class `SecurityAggregationService` in `services/` composes existing `SecurityScannerService` + OpenSearch client + direct PG queries on `security_events`
- Severity normalization: OpenSearch uses `info/warning/error/critical`, PG `security_events` uses same. Map to 5-level: `warning` -> `medium`, `error` -> `high`. `critical/info` stay as-is, `low` only from scanner findings.
- Score formula stays `max(0, 100 - weighted_penalty)` but sums penalties across all 3 sources
- Key behavioral change: "no data = score 0". Current code returns 100 when `security_findings` is empty. With aggregation, empty across ALL sources yields 0 ("unknown posture" is worse than "clean posture")
- OpenSearch query pattern: reuse `_query_opensearch_security()` from `routers/audit.py:797` — queries `audit-*` with `tenant_id` + severity filter + sort by `@timestamp`
