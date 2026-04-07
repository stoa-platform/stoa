# Spec: CAB-2004 — Replace /logs with Real Gateway Logs via Loki

## Problem

The `/logs` page ("Request Explorer") displays only aggregated Prometheus metrics (total requests, success rate, avg latency, top endpoints). This is 100% redundant with the Call Flow dashboard. The name "Logs" is misleading — users expect actual log entries, not metric charts.

## Goal

Replace `/logs` with a real log viewer showing structured gateway logs from Loki (access logs, errors, auth failures) with filtering, search, and trace correlation. Reuse existing `LokiClient`, `PIIMasker`, and `ConsumerLogsService` patterns.

## API Contract

```
GET /v1/admin/logs
Auth: cpi-admin (all logs) | tenant-admin (own tenant only) | viewer/devops → 403
Query params:
  service:    string  (gateway|api|auth|all)  default: "all"
  level:      string  (debug|info|warning|error)  optional
  search:     string  optional, free-text filter
  start_time: ISO8601 optional, default: now - 1h
  end_time:   ISO8601 optional, default: now
  limit:      int     1-200, default: 50

Response 200:
{
  "logs": [
    {
      "timestamp": "2026-04-07T12:00:00Z",
      "service": "stoa-gateway",
      "level": "info",
      "message": "request completed",
      "trace_id": "abc123",
      "tenant_id": "oasis",
      "request_id": "req-456",
      "duration_ms": 42.5,
      "path": "/mcp/tools/list",
      "method": "GET",
      "status_code": 200,
      "consumer_id": "consumer-789"
    }
  ],
  "total": 1,
  "limit": 50,
  "has_more": false,
  "query_time_ms": 120
}

Response 403: { "detail": "Insufficient permissions" }
Response 503: { "detail": "Loki unavailable" }
```

LogQL generation:
- Base: `{job=~"stoa-gateway|control-plane-api|keycloak"}`
- Service filter: `{job="stoa-gateway"}` when `service=gateway`
- JSON parse: `| json`
- Level filter: `| level="error"` when `level=error`
- Tenant scope: `| tenant_id="oasis"` when requester is tenant-admin
- Free-text: `|~ "search term"` when `search` provided

## Acceptance Criteria

- [ ] AC1: `GET /v1/admin/logs` returns structured log entries from Loki with correct schema
- [ ] AC2: `cpi-admin` sees logs from all tenants; `tenant-admin` sees only own tenant logs
- [ ] AC3: `viewer` and `devops` roles receive 403
- [ ] AC4: PII masking is applied to all log entries via PIIMasker
- [ ] AC5: Service filter restricts logs to selected service (gateway/api/auth/all)
- [ ] AC6: Level filter restricts logs to selected severity
- [ ] AC7: Search param applies free-text filter across log messages
- [ ] AC8: Time range defaults to last 1h, max 24h enforced
- [ ] AC9: Frontend renders log table with timestamp, service badge, level badge, message, duration
- [ ] AC10: Clicking a log row opens detail panel showing full JSON fields
- [ ] AC11: Clicking trace_id navigates to `/call-flow/trace/{trace_id}`
- [ ] AC12: Auto-refresh toggle works (off/5s/15s/30s) with no memory leak on unmount
- [ ] AC13: Empty state shown when Loki unavailable (503) or 0 results
- [ ] AC14: Navigation tab renamed from "Logs" to "Gateway Logs"
- [ ] AC15: `LogsEmbed.tsx` and `/logs/opensearch` route removed (dead code cleanup)

## Edge Cases

| Case | Input | Expected | Priority |
|------|-------|----------|----------|
| Loki unreachable | Loki down | API: 503 + `"Loki unavailable"`. UI: banner, no crash | Must |
| Empty results | Valid query, 0 logs | API: `{"logs":[], "total":0}`. UI: empty state | Must |
| Time range > 24h | start/end > 24h apart | API: 400 `"Max time range is 24 hours"` | Must |
| Malformed log line | Loki returns non-JSON | Skip entry, don't crash; log warning | Must |
| PII in message field | Email in log message | Masked by PIIMasker before response | Must |
| Tenant-admin cross-tenant | tenant-admin queries other tenant | LogQL scoped to own tenant, other logs invisible | Must |
| Very large result | limit=200, busy gateway | Return 200 entries, `has_more=true` | Should |
| Special chars in search | `search=foo"bar` | Escaped in LogQL, no injection | Must |
| Missing trace_id | Log entry has no trace_id | Detail panel: no trace link, field shows "-" | Should |
| Auto-refresh + unmount | Navigate away during refresh | Timer cleared, no state-update-on-unmounted | Must |

## Out of Scope

- CSV export for admin logs (exists for consumer logs, can be added later)
- Log alerting / notifications
- Log retention configuration (Loki 7-day retention is pre-configured)
- OpenSearch integration (being removed, not replaced)
- Consumer-scoped logs (already exists at `/v1/logs/calls`)

## Security Considerations

- [x] Auth required: `cpi-admin` (all) or `tenant-admin` (own tenant). Others → 403
- [x] PII handling: PIIMasker applied to every log entry before response
- [x] Tenant isolation: LogQL stream selector scoped by `tenant_id` for non-admin
- [x] LogQL injection: search param must be escaped (no raw interpolation into LogQL)
- [ ] Rate limiting: not needed (admin endpoint, low cardinality)

## Dependencies

- Loki operational at `stoa-loki:3100` (already deployed, 7-day retention)
- Promtail scraping `stoa-*` containers (already configured)
- Gateway structured access logs (`access_log.rs`) — already shipping JSON to Loki
- `LokiClient.query_range()` — already production (`loki_client.py:50`)
- `PIIMasker.for_tenant()` — already production (`core/pii/masker.py:105`)
- `LogEntryResponse` schema — already defined (`schemas/logs.py:46`), extend for admin fields

## Notes

- Follow `self_service_logs.py` pattern: router → service → LokiClient → PIIMasker
- Create `AdminLogsService` mirroring `ConsumerLogsService` but with admin-level LogQL
- Job mapping: `gateway` → `stoa-gateway`, `api` → `control-plane-api`, `auth` → `keycloak`
- Frontend: full rewrite of `RequestExplorer/` — no salvageable code from Prometheus dashboard
- `LogsEmbed.tsx` (129 LOC) is dead code (OpenSearch iframe, unused) — delete
- Schema `LogEntryResponse` already has most fields; add `service`, `consumer_id` for admin view
- Gateway logs fields from `access_log.rs:108-121`: method, path, status, duration_ms, tenant_id, consumer_id, user_agent, trace_id
