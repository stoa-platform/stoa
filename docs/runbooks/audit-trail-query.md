# Runbook: Audit Trail Query Procedures

**Severity**: Medium
**Last updated**: 2026-04-04
**Owner**: Platform Team

## When to Use This Runbook

- A client/admin asks "who connected to prod on date X?"
- P1 incident investigation requiring root cause analysis
- DORA Article 11 compliance audit
- GDPR data access request (who accessed what)

## Architecture

```
FastAPI Middleware (AuditMiddleware) → dual-write:
  ├── PostgreSQL: audit_events table (compliance-grade, append-only)
  └── OpenSearch: audit-* index (search/analytics)
```

- **PostgreSQL** = source of truth for compliance (immutable, indexed)
- **OpenSearch** = analytics, full-text search, dashboards
- **Retention**: configurable per-tenant via `AuditService.purge_before()`

## Common Queries

### 1. Who connected on a specific date?

**SQL (PostgreSQL)**:
```sql
SELECT actor_email, actor_id, client_ip, action, path, created_at
FROM audit_events
WHERE created_at >= '2026-04-03T00:00:00Z'
  AND created_at < '2026-04-04T00:00:00Z'
  AND tenant_id = 'your-tenant-id'
ORDER BY created_at;
```

**API**:
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "${STOA_API_URL}/v1/audit/${TENANT_ID}?start_date=2026-04-03T00:00:00Z&end_date=2026-04-04T00:00:00Z&page_size=500"
```

### 2. What did a specific user do?

**SQL**:
```sql
SELECT action, method, path, resource_type, resource_id, outcome, status_code, created_at
FROM audit_events
WHERE actor_id = 'user-uuid-here'
  AND tenant_id = 'your-tenant-id'
ORDER BY created_at DESC
LIMIT 100;
```

**API**:
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "${STOA_API_URL}/v1/audit/${TENANT_ID}?actor_id=user-uuid-here&page_size=100"
```

### 3. Who modified a specific API/resource?

**SQL**:
```sql
SELECT actor_email, action, method, outcome, details, diff, created_at
FROM audit_events
WHERE resource_type = 'api'
  AND resource_id = 'api-uuid-here'
  AND tenant_id = 'your-tenant-id'
ORDER BY created_at DESC;
```

### 4. Failed operations (access denied, errors)

**SQL**:
```sql
SELECT actor_email, action, path, outcome, client_ip, created_at
FROM audit_events
WHERE outcome IN ('failure', 'denied', 'error')
  AND tenant_id = 'your-tenant-id'
  AND created_at >= NOW() - INTERVAL '24 hours'
ORDER BY created_at DESC;
```

### 5. Security events (intrusion attempts)

**API** (requires cpi-admin or tenant-admin role):
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "${STOA_API_URL}/v1/audit/${TENANT_ID}/security?severity=critical"
```

## Export for Investigation

**CSV** (requires tenant-admin or cpi-admin):
```bash
curl -H "Authorization: Bearer $TOKEN" \
  -o "audit-export-$(date +%Y%m%d).csv" \
  "${STOA_API_URL}/v1/audit/${TENANT_ID}/export/csv?start_date=2026-04-01&end_date=2026-04-04"
```

**JSON**:
```bash
curl -H "Authorization: Bearer $TOKEN" \
  -o "audit-export-$(date +%Y%m%d).json" \
  "${STOA_API_URL}/v1/audit/${TENANT_ID}/export/json?start_date=2026-04-01&end_date=2026-04-04&limit=50000"
```

## Access Control (RBAC)

| Endpoint | Allowed Roles | Contains PII |
|----------|--------------|--------------|
| List entries | All authenticated (tenant-scoped) | Emails, IPs |
| Export CSV/JSON | cpi-admin, tenant-admin | Bulk PII |
| Security events | cpi-admin, tenant-admin | IPs, user agents |
| Global summary | cpi-admin only | Aggregated stats |
| GDPR erasure | cpi-admin only | Deletes PII |

## What is Captured

Each audit event records:

| Field | Description | Example |
|-------|-------------|---------|
| `actor_id` | Keycloak user UUID (JWT `sub`) | `a1b2c3d4-...` |
| `actor_email` | User email | `alice@acme.com` |
| `actor_type` | user / system / api_key / service | `user` |
| `action` | Operation category | `create`, `update`, `delete`, `deploy` |
| `method` | HTTP method | `POST`, `PUT`, `DELETE` |
| `path` | Request path | `/v1/tenants/acme/apis` |
| `resource_type` | Target resource | `api`, `tool`, `subscription` |
| `resource_id` | Target resource UUID | `uuid-...` |
| `outcome` | Result | `success`, `failure`, `denied`, `error` |
| `status_code` | HTTP status | `200`, `403`, `500` |
| `client_ip` | Source IP | `192.168.1.100` |
| `user_agent` | Browser/client | `Mozilla/5.0...` |
| `correlation_id` | Request trace ID | `uuid-...` |
| `duration_ms` | Request latency | `42` |
| `created_at` | UTC timestamp (immutable) | `2026-04-04T10:30:00Z` |

## Known Limitations

| Gap | Impact | Workaround |
|-----|--------|------------|
| Keycloak login/logout events not forwarded | "Who logged in" only shows API calls, not KC sessions | Check Keycloak admin events directly: KC Admin Console > Events > Login Events |
| Gateway (data plane) access logs separate | MCP tool calls not in control plane audit | Check stoa-gateway logs: `kubectl logs -n stoa-system deploy/stoa-gateway` |
| Audit of GET requests only in OpenSearch | PostgreSQL dual-write is mutations only (POST/PUT/PATCH/DELETE) | Query OpenSearch `audit-*` index for read-access audit |
| Export operations not audited in PG | Admin exporting 50K rows leaves no PG trace | OpenSearch captures the GET request |

## Escalation

1. **Control plane data** (API calls, mutations): query `audit_events` table or `/v1/audit` API
2. **Keycloak sessions** (login/logout): Keycloak Admin Console > Events tab
3. **Gateway traffic** (MCP/API calls through data plane): `kubectl logs` on stoa-gateway pods
4. **Infrastructure access** (SSH, kubectl): check VPS auth logs and K8s audit logs (API server)

## Console UI

The Audit Log page is available at `/audit-log` in the Console (Governance section).
- All authenticated users can view paginated entries
- Only `cpi-admin` and `tenant-admin` can export and view security events
- Auto-refreshes every 30 seconds
