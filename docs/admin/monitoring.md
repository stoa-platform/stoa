# Monitoring

## Stack Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Prometheus   │────▶│ Grafana      │     │ OpenSearch   │
│ (metrics)    │     │ (dashboards) │     │ (logs/traces)│
└──────┬───────┘     └─────────────┘     └──────┬───────┘
       │                                         │
       ▼                                         ▼
  /metrics endpoints                     structured JSON logs
  on all components                      from all pods
```

## Prometheus Metrics

### Control Plane API

| Metric | Type | Description |
|--------|------|-------------|
| `http_requests_total` | Counter | Total HTTP requests by method, path, status |
| `http_request_duration_seconds` | Histogram | Request latency |
| `db_query_duration_seconds` | Histogram | Database query latency |
| `active_tenants` | Gauge | Number of active tenants |
| `api_catalog_size` | Gauge | Number of APIs in catalog |
| `subscriptions_total` | Counter | Subscription events |

### MCP Gateway

| Metric | Type | Description |
|--------|------|-------------|
| `mcp_tool_calls_total` | Counter | Tool invocations by tool, tenant, status |
| `mcp_tool_call_duration_seconds` | Histogram | Tool call latency |
| `mcp_circuit_breaker_state` | Gauge | Circuit breaker state (0=closed, 1=open, 2=half-open) |
| `opa_policy_evaluations_total` | Counter | OPA policy checks |
| `opa_policy_evaluation_duration_seconds` | Histogram | OPA evaluation latency |

### STOA Gateway (Rust)

| Metric | Type | Description |
|--------|------|-------------|
| `gateway_requests_total` | Counter | Proxied requests by route, status |
| `gateway_request_duration_seconds` | Histogram | End-to-end request latency |
| `gateway_active_connections` | Gauge | Current active connections |
| `gateway_upstream_errors_total` | Counter | Backend errors by upstream |

## Grafana Dashboards

Recommended dashboards:

| Dashboard | UID | Purpose |
|-----------|-----|---------|
| Platform Overview | `stoa-platform-overview` | All components at a glance |
| MCP Tools | `stoa-mcp-tools` | Tool call rates, latencies, errors |
| Security Events | `stoa-security-events` | Auth failures, policy violations |

Access Grafana at `https://grafana.<BASE_DOMAIN>`.

## Recommended Alerts

### P0 — Critical (Page immediately)

| Alert | Condition | Action |
|-------|-----------|--------|
| API Down | `up{job="control-plane-api"} == 0` for 2m | Check pods, restart deployment |
| Gateway Down | `up{job="mcp-gateway"} == 0` for 2m | Check pods, check OPA config |
| Error Rate Spike | `rate(http_requests_total{status=~"5.."}[5m]) > 0.1` | Check logs, identify failing endpoint |
| Database Unreachable | `db_query_duration_seconds > 30` | Check PostgreSQL, network policies |

### P1 — Warning (Investigate within 1h)

| Alert | Condition | Action |
|-------|-----------|--------|
| High Latency | `histogram_quantile(0.95, http_request_duration_seconds) > 2` | Profile slow endpoints |
| Pod Restarts | `kube_pod_container_status_restarts_total > 3` in 1h | Check logs, OOM, liveness probes |
| Circuit Breaker Open | `mcp_circuit_breaker_state == 1` | Check upstream health |
| Disk Usage High | `kubelet_volume_stats_used_bytes / kubelet_volume_stats_capacity_bytes > 0.85` | Expand PVC or clean data |

### P2 — Info (Review daily)

| Alert | Condition | Action |
|-------|-----------|--------|
| Certificate Expiry | `certmanager_certificate_expiration_timestamp_seconds - time() < 7*24*3600` | Check cert-manager |
| Slow OPA Evaluations | `opa_policy_evaluation_duration_seconds > 0.5` | Review Rego policies |

## OpenSearch

### Log Pipeline

All pods emit structured JSON logs. OpenSearch ingests via Fluent Bit:

```
Pod stdout → Fluent Bit (DaemonSet) → OpenSearch → Dashboards
```

### Index Patterns

| Pattern | Retention | Content |
|---------|----------|---------|
| `stoa-api-*` | 30 days | Control Plane API logs |
| `stoa-gateway-*` | 30 days | MCP Gateway logs |
| `stoa-audit-*` | 90 days | Audit trail (auth, RBAC decisions) |
| `stoa-metering-*` | 365 days | Tool call metering events |

### GDPR Pipeline

Metering events pass through a GDPR pipeline before indexing:

1. **Redact**: PII fields (email, IP) are hashed
2. **Retain**: Hashed data retained per policy
3. **Delete**: Raw logs purged after retention window

### Useful Queries

```json
// Find errors in the last hour
{
  "query": {
    "bool": {
      "must": [
        { "range": { "@timestamp": { "gte": "now-1h" } } },
        { "match": { "level": "ERROR" } }
      ]
    }
  }
}

// Trace a request by trace_id
{
  "query": {
    "match": { "trace_id": "abc-123-def" }
  },
  "sort": [{ "@timestamp": "asc" }]
}
```

## Quick Checks

```bash
# Prometheus targets status
curl -s https://prometheus.<BASE_DOMAIN>/api/v1/targets | python3 -c "
import sys, json
data = json.load(sys.stdin)
for t in data['data']['activeTargets']:
    print(f\"{t['labels'].get('job','?'):30s} {t['health']}\")"

# Check pod resource usage
kubectl top pods -n stoa-system

# Check node resource usage
kubectl top nodes
```
