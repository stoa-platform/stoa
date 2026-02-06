# STOA Platform - Grafana Dashboards

## Folder Structure

| Folder | Purpose | Audience |
|--------|---------|----------|
| **01-Overview** | Platform overview, SLO dashboards | All users |
| **02-Operations** | Incident response, deployment health, infrastructure | DevOps, SRE |
| **03-Gateway** | MCP Gateway metrics, tracing, token optimization | Platform team |
| **04-Security** | Security events, audit trails | Security, Compliance |
| **05-Tenant** | Multi-tenant views, tenant-scoped analytics | CPI Admins, Tenant Admins |
| **06-Business** | Business metrics, adoption, revenue indicators | Product Owners |

## Dashboard Inventory

### 01-Overview
- `demo-overview.json` - Demo overview dashboard

### 02-Operations
- `incident-response.json` - Golden signals for incident response (APDEX, error rate, latency)
- `infrastructure-networking.json` - Infrastructure networking dashboard

### 03-Gateway
- `mcp-gateway-traceability.json` - MCP Gateway real-time logs and tracing
- `stoa-gateway.json` - STOA Gateway (Rust) metrics

### 04-Security
- `security-events.json` - Security events monitoring

### 05-Tenant
- `multi-tenant-overview.json` - Multi-tenant platform overview (admin view)
- `tenant-analytics.json` - Tenant-scoped analytics (uses `$tenant_id` variable)

### 06-Business
- `business-analytics.json` - Business metrics: adoption, engagement, revenue

## Deployment

### Using Kustomize (Recommended)
```bash
kubectl apply -k deploy/grafana/dashboards/ -n stoa-monitoring
```

### Manual ConfigMap deployment
```bash
kubectl apply -f deploy/grafana/dashboards/mcp-gateway-configmap.yaml -n stoa-monitoring
```

## Grafana Sidecar

Dashboards are automatically loaded by the Grafana sidecar when deployed as ConfigMaps with:
- Label: `grafana_dashboard: "1"`
- Annotation: `grafana_folder: "<folder-name>"` (determines folder placement)

## Naming Convention

Dashboard UIDs follow the pattern: `stoa-<domain>-<purpose>`
- `stoa-incident-response`
- `stoa-mcp-traceability`
- `stoa-tenant-analytics`
- `stoa-business-analytics`

## Links to Console UI

Each dashboard includes links back to the STOA Console UI pages:
- Operations Dashboard → `/operations`
- Tenant Dashboard → `/my-usage`
- Business Dashboard → `/business`

## Recording Rules

SLO metrics used in dashboards are pre-computed via recording rules:
- `deploy/prometheus/rules/stoa-slo.yaml` - Availability, latency, APDEX, error budget
- `docker/observability/prometheus/rules/mcp-migration-alerts.yaml` - Migration alerts
