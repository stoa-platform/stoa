---
sidebar_position: 5
title: Observability
description: Monitoring with Prometheus, Grafana, and Loki.
---

# Observability

STOA includes a built-in observability stack with Prometheus for metrics, Grafana for dashboards, and Loki for log aggregation.

## Stack Overview

| Component | Purpose | Access |
|-----------|---------|--------|
| **Prometheus** | Metrics collection and alerting | Internal (in-cluster) |
| **Grafana** | Dashboards and visualization | `https://grafana.gostoa.dev` |
| **Loki** | Log aggregation and search | Via Grafana |

## Metrics

### Control Plane API

The FastAPI backend exposes Prometheus metrics at `/metrics`:

| Metric | Type | Description |
|--------|------|-------------|
| `http_requests_total` | Counter | Total HTTP requests by method, path, status |
| `http_request_duration_seconds` | Histogram | Request latency distribution |
| `db_query_duration_seconds` | Histogram | Database query latency |
| `kafka_events_published_total` | Counter | Events published to Kafka |

### MCP Gateway

| Metric | Type | Description |
|--------|------|-------------|
| `mcp_tool_calls_total` | Counter | Tool invocations by name, tenant, status |
| `mcp_tool_call_duration_seconds` | Histogram | Tool call latency |
| `opa_policy_evaluations_total` | Counter | OPA policy checks by result |
| `mcp_active_connections` | Gauge | Current SSE connections |

### Kafka / Redpanda

| Metric | Type | Description |
|--------|------|-------------|
| `kafka_consumer_lag` | Gauge | Consumer lag per topic/partition |
| `kafka_messages_in_total` | Counter | Messages produced per topic |

## Grafana Dashboards

### Platform Overview

The main dashboard shows:

- Request rate and error rate across all services
- Latency percentiles (p50, p95, p99)
- Active users and sessions
- Database connection pool usage

### MCP Gateway Dashboard

- Tool call rate by tenant and tool name
- OPA policy allow/deny ratio
- SSE connection count
- Metering pipeline throughput

### Tenant Dashboard

Per-tenant view showing:

- API call volume
- Subscription activity
- Error breakdown by API
- Rate limit utilization

## Log Aggregation

### Querying Logs

Access logs via Grafana's Explore view with Loki:

```logql
# All error logs in the last 5 minutes
{job=~".+"} |= "level=error"

# Control Plane API logs for a specific tenant
{app="control-plane-api"} |= "tenant=acme"

# MCP Gateway tool calls
{app="mcp-gateway"} |= "tool.call"

# Slow requests (>1s)
{app="control-plane-api"} | json | duration > 1s
```

### Log Format

All STOA services log in structured JSON format:

```json
{
  "timestamp": "2026-02-04T10:30:00Z",
  "level": "INFO",
  "service": "control-plane-api",
  "message": "API published",
  "tenant": "acme",
  "api": "petstore",
  "version": "1.0.0",
  "trace_id": "abc123"
}
```

Set `LOG_FORMAT=text` for human-readable output during local development.

## Alerting

### Prometheus Alert Rules

STOA ships with default alert rules:

| Alert | Condition | Severity |
|-------|-----------|----------|
| `HighErrorRate` | Error rate > 5% for 5 minutes | Critical |
| `HighLatency` | p99 latency > 2s for 5 minutes | Warning |
| `DatabaseConnectionExhausted` | Connection pool > 90% | Critical |
| `KafkaConsumerLag` | Lag > 10000 for 10 minutes | Warning |
| `MCPGatewayDown` | No healthy pods for 1 minute | Critical |
| `VaultSealed` | Vault sealed status detected | Critical |

### Alert Destinations

Configure alert routing in `alertmanager.yaml`:

- **Slack**: Channel notifications for team alerts
- **PagerDuty**: On-call escalation for critical alerts
- **Email**: Summary digests for non-critical alerts

## Runbooks

STOA includes operational runbooks organized by severity:

### Critical

- [Gateway Down](https://docs.gostoa.dev/runbooks/critical/gateway-down) — Gateway unreachable
- [Database Connection](https://docs.gostoa.dev/runbooks/critical/database-connection) — PostgreSQL connectivity issues
- [Vault Sealed](https://docs.gostoa.dev/runbooks/critical/vault-sealed) — Vault requires unsealing
- [Vault Restore](https://docs.gostoa.dev/runbooks/critical/vault-restore) — Vault disaster recovery

### High Priority

- [Certificate Expiration](https://docs.gostoa.dev/runbooks/high/certificate-expiration) — TLS cert approaching expiry
- [Gateway High Latency](https://docs.gostoa.dev/runbooks/high/gateway-high-latency) — Response time degradation
- [Kafka Lag](https://docs.gostoa.dev/runbooks/high/kafka-lag) — Consumer falling behind

### Medium Priority

- [API Rollback](https://docs.gostoa.dev/runbooks/medium/api-rollback) — Revert a bad API deployment
- [AWX Unreachable](https://docs.gostoa.dev/runbooks/medium/awx-unreachable) — Ansible automation server down

## Health Endpoints

All services expose health check endpoints:

| Endpoint | Purpose |
|----------|---------|
| `/health/ready` | Readiness probe — all dependencies reachable |
| `/health/live` | Liveness probe — process alive |
| `/health/startup` | Startup probe — initialization complete |

```bash
curl https://api.gostoa.dev/health/ready
# {"status": "ok"}
```
