# STOA Platform Observability Stack

This document describes the observability setup for the STOA Platform, including Prometheus metrics, Grafana dashboards, and Loki log aggregation.

## Architecture Overview

```
                                    +-------------------+
                                    |    Grafana        |
                                    | grafana.stoa...   |
                                    +--------+----------+
                                             |
              +------------------------------+------------------------------+
              |                              |                              |
    +---------v---------+        +-----------v-----------+       +----------v----------+
    |    Prometheus     |        |         Loki          |       |   AlertManager      |
    | prometheus.stoa...|        |    loki.stoa...       |       | (kube-prom-stack)   |
    +-------------------+        +-----------------------+       +---------------------+
              |                              ^
              |                              |
    +---------v---------+        +-----------+-----------+
    |  ServiceMonitors  |        |       Promtail        |
    | - control-plane   |        |     (DaemonSet)       |
    | - mcp-gateway     |        +-----------------------+
    +-------------------+                    |
              |                              |
    +---------v---------+        +-----------v-----------+
    | Control-Plane API |        |     Pod Logs          |
    |   MCP Gateway     |        | (stoa-* namespaces)   |
    +-------------------+        +-----------------------+
```

## Components

### Namespaces

| Namespace | Components |
|-----------|------------|
| `stoa-monitoring` | Prometheus, Grafana, AlertManager (kube-prometheus-stack) |
| `stoa-system` | Loki, Promtail, Control-Plane API, MCP Gateway |

### URLs

| Service | URL | Description |
|---------|-----|-------------|
| Grafana | https://grafana.stoa.cab-i.com | Dashboards & Visualization |
| Prometheus | https://prometheus.stoa.cab-i.com | Metrics & Alerting |
| Loki | https://loki.stoa.cab-i.com | Log Aggregation |

### Authentication

All observability endpoints are secured with Keycloak OIDC authentication:

- **Grafana**: Native OIDC integration
- **Prometheus**: OAuth2-proxy sidecar
- **Loki**: OAuth2-proxy sidecar

Users can login with their Keycloak credentials (e.g., `admin@cab-i.com`).

## Installation

### Prerequisites

- Kubernetes cluster with nginx-ingress controller
- cert-manager with `letsencrypt-prod` ClusterIssuer
- Helm 3.x

### 1. Install kube-prometheus-stack

```bash
# Add Helm repo
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Install kube-prometheus-stack in stoa-monitoring namespace
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace stoa-monitoring \
  --create-namespace \
  --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false \
  --set prometheus.prometheusSpec.podMonitorSelectorNilUsesHelmValues=false
```

### 2. Apply Observability Ingresses

```bash
# Apply Grafana and Prometheus Ingresses
kubectl apply -f deploy/observability/grafana-ingress.yaml
kubectl apply -f deploy/observability/prometheus-ingress.yaml
```

### 3. Deploy STOA Platform (includes Loki, Promtail)

```bash
# Deploy stoa-platform Helm chart
helm upgrade --install stoa-platform ./charts/stoa-platform \
  --namespace stoa-system \
  --create-namespace
```

This deploys:
- Loki StatefulSet for log storage
- Promtail DaemonSet for log collection
- Loki Ingress for external access
- ServiceMonitors for Control-Plane API and MCP Gateway

### 4. Enable Keycloak Authentication (Optional)

To enable Keycloak SSO for all observability endpoints:

#### Step 1: Create Keycloak Client

1. Go to https://auth.stoa.cab-i.com
2. Login as admin
3. Select realm: `stoa`
4. Go to **Clients** > **Create Client**
5. Configure:
   - Client ID: `observability`
   - Client Protocol: `openid-connect`
   - Access Type: `confidential`
6. Set **Valid Redirect URIs**:
   ```
   https://grafana.stoa.cab-i.com/*
   https://prometheus.stoa.cab-i.com/oauth2/callback
   https://loki.stoa.cab-i.com/oauth2/callback
   ```
7. Save and go to **Credentials** tab
8. Copy the **Client Secret**

#### Step 2: Run Setup Script

```bash
# Replace <CLIENT_SECRET> with the secret from Keycloak
./deploy/observability/setup-keycloak-auth.sh <CLIENT_SECRET>
```

This script will:
- Create oauth2-proxy secrets
- Deploy oauth2-proxy for Prometheus and Loki
- Update Ingresses to use oauth2-proxy
- Configure Grafana with native OIDC

#### Manual Setup (Alternative)

If you prefer manual setup:

```bash
# Generate cookie secret
COOKIE_SECRET=$(openssl rand -base64 32 | tr -- '+/' '-_')
CLIENT_SECRET="<your-keycloak-client-secret>"

# Create secrets
kubectl create secret generic oauth2-proxy-secret -n stoa-monitoring \
  --from-literal=cookie-secret="$COOKIE_SECRET" \
  --from-literal=client-secret="$CLIENT_SECRET"

kubectl create secret generic oauth2-proxy-secret -n stoa-system \
  --from-literal=cookie-secret="$COOKIE_SECRET" \
  --from-literal=client-secret="$CLIENT_SECRET"

kubectl create secret generic grafana-oidc-secret -n stoa-monitoring \
  --from-literal=GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET="$CLIENT_SECRET"

# Deploy oauth2-proxy
kubectl apply -f deploy/observability/oauth2-proxy-prometheus.yaml
kubectl apply -f deploy/observability/oauth2-proxy-loki.yaml

# Update Ingresses
kubectl apply -f deploy/observability/prometheus-ingress.yaml
kubectl apply -f deploy/observability/loki-ingress.yaml

# Upgrade Grafana with OIDC
helm upgrade kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  -n stoa-monitoring \
  -f deploy/observability/values-grafana-oidc.yaml \
  --reuse-values
```

## Metrics

### Control-Plane API Metrics

Prefix: `stoa_control_plane_`

| Metric | Type | Description |
|--------|------|-------------|
| `stoa_control_plane_http_requests_total` | Counter | Total HTTP requests |
| `stoa_control_plane_http_request_duration_seconds` | Histogram | Request duration |
| `stoa_control_plane_http_requests_in_progress` | Gauge | Requests currently being processed |

Labels: `method`, `endpoint`, `status`

### MCP Gateway Metrics

Prefix: `stoa_mcp_gateway_`

| Metric | Type | Description |
|--------|------|-------------|
| `stoa_mcp_gateway_http_requests_total` | Counter | Total HTTP requests |
| `stoa_mcp_gateway_http_request_duration_seconds` | Histogram | Request duration |
| `stoa_mcp_gateway_tool_invocations_total` | Counter | Tool invocations |
| `stoa_mcp_gateway_auth_requests_total` | Counter | Auth operations |

### SLO Recording Rules

Pre-computed SLO metrics (defined in `prometheus-rules.yaml`):

| Metric | Description |
|--------|-------------|
| `slo:api_availability:ratio` | Overall API availability (non-5xx / total) |
| `slo:api_latency_p95:seconds` | 95th percentile latency |
| `slo:api_latency_p99:seconds` | 99th percentile latency |
| `slo:api_error_rate:ratio` | Error rate (5xx / total) |
| `slo:error_budget:remaining_ratio` | Remaining error budget |

## Grafana Dashboards

Dashboards are located in `docker/observability/grafana/dashboards/`:

| Dashboard | File | Description |
|-----------|------|-------------|
| Platform Overview | `platform-overview.json` | High-level platform health |
| Control-Plane API | `control-plane-api.json` | API metrics detail |
| MCP Gateway | `mcp-gateway.json` | Gateway metrics detail |
| SLO Dashboard | `slo-dashboard.json` | SLO compliance tracking |
| Logs Explorer | `logs-explorer.json` | Log search and analysis |

### Importing Dashboards

1. Open Grafana at https://grafana.stoa.cab-i.com
2. Go to **Dashboards** > **Import**
3. Upload JSON file or paste contents
4. Select **Prometheus** as data source for metrics dashboards
5. Select **Loki** as data source for log dashboards

## Log Aggregation

### Loki Configuration

- **Retention**: 30 days (720h)
- **Storage**: Persistent volume (50Gi default)
- **Schema**: TSDB with v13 schema

### Promtail Collection

Promtail runs as a DaemonSet and collects logs from:
- Namespaces matching: `stoa-system|stoa-.*`
- All containers in matching pods

### Structured Logging

The Control-Plane API uses structured JSON logging for Loki compatibility:

```python
from src.logging_config import get_logger

logger = get_logger(__name__)
logger.info("Processing request", tenant_id="acme", api_id="123", method="POST")
```

Output:
```json
{
  "timestamp": "2024-01-07T12:00:00.000Z",
  "level": "info",
  "logger": "src.routers.apis",
  "message": "Processing request",
  "tenant_id": "acme",
  "api_id": "123",
  "method": "POST"
}
```

### LogQL Queries

Example queries for Grafana:

```logql
# All logs from control-plane-api
{namespace="stoa-system", app="control-plane-api"}

# Error logs only
{namespace="stoa-system"} |= "error" | json | level="error"

# Logs for specific tenant
{namespace="stoa-system"} | json | tenant_id="acme"

# Requests by endpoint
{namespace="stoa-system", app="control-plane-api"} | json | endpoint="/v1/apis"
```

## Alerting

### SLO Alerts (defined in `prometheus-rules.yaml`)

| Alert | Condition | Severity |
|-------|-----------|----------|
| SLOAvailabilityBreach | Availability < 99.9% for 5m | Critical |
| SLOAvailabilityWarning | Availability < 99.5% for 10m | Warning |
| SLOLatencyP95Breach | p95 > 500ms for 5m | Warning |
| SLOLatencyP99Breach | p99 > 1000ms for 5m | Warning |
| SLOErrorRateBreach | Error rate > 0.1% for 5m | Critical |
| ErrorBudgetLow | Budget < 20% for 15m | Warning |
| ErrorBudgetExhausted | Budget < 5% for 5m | Critical |

### Configuring AlertManager

To enable alerting:

1. Update `values.yaml`:
```yaml
monitoring:
  alerting:
    enabled: true
```

2. Configure AlertManager in `alertmanager-config.yaml` with your Slack/PagerDuty/email settings.

## Troubleshooting

### Prometheus Not Scraping Targets

1. Check ServiceMonitor exists:
```bash
kubectl get servicemonitor -n stoa-system
```

2. Verify Prometheus is watching all namespaces:
```bash
kubectl get prometheus -n stoa-monitoring -o yaml | grep serviceMonitorSelector
```

3. Check service labels match ServiceMonitor selector

### Loki Not Receiving Logs

1. Check Promtail is running:
```bash
kubectl get pods -n stoa-system -l app.kubernetes.io/component=promtail
```

2. Check Promtail logs:
```bash
kubectl logs -n stoa-system -l app.kubernetes.io/component=promtail
```

3. Verify namespace regex in Promtail config matches your namespaces

### Grafana Data Source Issues

1. Add Prometheus data source:
   - URL: `http://kube-prometheus-stack-prometheus.stoa-monitoring:9090`

2. Add Loki data source:
   - URL: `http://stoa-platform-loki.stoa-system:3100`

## Configuration Reference

### Helm Values (charts/stoa-platform/values.yaml)

```yaml
# Loki configuration
loki:
  enabled: true
  retention: 720h  # 30 days
  persistence:
    size: 50Gi

# Promtail configuration
promtail:
  enabled: true
  namespaceRegex: "stoa-system|stoa-.*"
  tenantId: stoa

# Monitoring
monitoring:
  enabled: true
  interval: 30s

# Observability ingress
observability:
  namespace: stoa-monitoring
  ingress:
    enabled: true
```

## Related Documentation

- [SLO/SLA Documentation](SLO-SLA.md)
- [Architecture Overview](ARCHITECTURE-PRESENTATION.md)
- [Runbooks](runbooks/)
