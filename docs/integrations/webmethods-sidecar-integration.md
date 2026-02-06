# WebMethods Gateway + STOA Sidecar Integration

This guide explains how to deploy Software AG webMethods API Gateway with STOA sidecar for policy enforcement, rate limiting, and usage metering.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Kubernetes Pod                           │
│  ┌──────────────────────┐    ┌───────────────────────────────┐  │
│  │   webMethods API     │    │      STOA Sidecar             │  │
│  │      Gateway         │    │    (sidecar mode)             │  │
│  │                      │    │                               │  │
│  │  ┌────────────────┐  │    │  ┌─────────────────────────┐  │  │
│  │  │   ext_authz    │──┼────┼──│  /authz endpoint       │  │  │
│  │  │   filter       │  │    │  │  - OPA policies        │  │  │
│  │  └────────────────┘  │    │  │  - Rate limiting       │  │  │
│  │                      │    │  │  - Token validation    │  │  │
│  │  Port: 9072          │    │  └─────────────────────────┘  │  │
│  │  (API traffic)       │    │                               │  │
│  └──────────────────────┘    │  Port: 8081                   │  │
│                              │  (internal only)              │  │
│                              │                               │  │
│                              │  ┌─────────────────────────┐  │  │
│                              │  │  Auto-registration      │  │  │
│                              │  │  → Control Plane        │  │  │
│                              │  └─────────────────────────┘  │  │
│                              └───────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Prerequisites

1. STOA Control Plane deployed and accessible
2. Keycloak realm `stoa` configured
3. Gateway API keys configured in Control Plane

## Deployment

### 1. Create Secrets

```bash
kubectl create secret generic stoa-sidecar-secrets \
  --namespace stoa-system \
  --from-literal=control-plane-api-key="gw_your_api_key_here" \
  --from-literal=keycloak-client-secret="your_keycloak_secret"
```

### 2. Configure Helm Values

Create a `values-webmethods.yaml` file:

```yaml
stoaSidecar:
  enabled: true
  targetGateway: webmethods

  # STOA Sidecar configuration
  image:
    repository: 848853684735.dkr.ecr.eu-west-1.amazonaws.com/apim/stoa-gateway
    tag: latest

  environment: prod
  controlPlaneUrl: "https://api.gostoa.dev"
  keycloakUrl: "https://auth.gostoa.dev"
  keycloakRealm: stoa
  keycloakClientId: stoa-sidecar
  secretName: stoa-sidecar-secrets

  # webMethods Gateway configuration
  mainGateway:
    enabled: true
    image:
      repository: softwareag/webmethods-api-gateway
      tag: "10.15"
    port: 9072
    env:
      - name: JAVA_OPTS
        value: "-Xms1g -Xmx2g"
      - name: SAG_IS_LICENSE_KEY
        valueFrom:
          secretKeyRef:
            name: webmethods-license
            key: license-key
      # Enable ext_authz to point to STOA sidecar
      - name: apigw_ext_authz_enabled
        value: "true"
      - name: apigw_ext_authz_url
        value: "http://127.0.0.1:8081/authz"
    resources:
      requests:
        cpu: 1000m
        memory: 2Gi
      limits:
        cpu: 4000m
        memory: 8Gi
```

### 3. Deploy

```bash
helm upgrade --install stoa-webmethods ./charts/stoa-platform \
  --namespace stoa-system \
  --values values-webmethods.yaml
```

## How It Works

### 1. Auto-Registration

When the pod starts, the STOA sidecar automatically registers with the Control Plane:

```json
POST /v1/internal/gateways/register
{
  "hostname": "webmethods-with-stoa-sidecar-xyz",
  "mode": "sidecar",
  "version": "0.1.0",
  "environment": "prod",
  "capabilities": ["ext_authz", "rate_limiting", "metering", "oidc"],
  "admin_url": "http://10.0.1.50:8081"
}
```

### 2. Request Flow

1. **Client** → webMethods Gateway (port 9072)
2. webMethods → **ext_authz** → STOA sidecar (port 8081)
3. STOA sidecar evaluates:
   - OPA policies (loaded from Control Plane)
   - Rate limits (per tenant/API/user)
   - JWT token validation (via Keycloak)
4. **Decision** returned to webMethods (allow/deny)
5. If allowed, webMethods → **Backend API**
6. STOA sidecar → **Kafka** (usage metrics)

### 3. Heartbeat

The sidecar sends heartbeats every 30 seconds:

```json
POST /v1/internal/gateways/heartbeat/{gateway_id}
{
  "uptime_seconds": 3600,
  "routes_count": 0,
  "policies_count": 5,
  "requests_total": 10000,
  "error_rate": 0.01
}
```

## Monitoring

### Console View

The webMethods + STOA sidecar appears in the STOA Console at `/gateways`:

| Name | Type | Status | Environment |
|------|------|--------|-------------|
| webmethods-prod-abc123 | stoa_sidecar | ONLINE | prod |

### Observability Dashboard

View aggregated metrics at `/gateway-observability`:
- Gateway health (online/offline/degraded)
- Request throughput
- Error rates
- Policy enforcement stats

### Prometheus Metrics

The sidecar exposes Prometheus metrics at `http://localhost:8081/metrics`:

```prometheus
stoa_sidecar_requests_total{tenant="acme",api="billing",status="allowed"} 9500
stoa_sidecar_requests_total{tenant="acme",api="billing",status="denied"} 500
stoa_sidecar_policy_evaluation_duration_seconds_bucket{le="0.01"} 9800
stoa_sidecar_rate_limit_hits_total{tenant="acme"} 150
```

## Policies

### Creating a Rate Limit Policy

```bash
curl -X POST https://api.gostoa.dev/v1/admin/policies \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "rate-limit-100rpm",
    "policy_type": "rate_limit",
    "scope": "api",
    "config": {
      "requests_per_minute": 100,
      "burst_size": 10
    },
    "priority": 100
  }'
```

### Binding Policy to Gateway

```bash
curl -X POST https://api.gostoa.dev/v1/admin/policies/bindings \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "policy_id": "UUID_FROM_ABOVE",
    "gateway_instance_id": "UUID_OF_WEBMETHODS_SIDECAR"
  }'
```

## Troubleshooting

### Sidecar Not Registering

Check logs:
```bash
kubectl logs -n stoa-system deployment/webmethods-with-stoa-sidecar -c stoa-sidecar
```

Verify Control Plane URL is reachable:
```bash
kubectl exec -n stoa-system deployment/webmethods-with-stoa-sidecar -c stoa-sidecar -- \
  curl -s http://control-plane-api.stoa-system.svc.cluster.local:8000/health
```

### ext_authz Errors

Check webMethods logs for ext_authz connection issues:
```bash
kubectl logs -n stoa-system deployment/webmethods-with-stoa-sidecar -c webmethods
```

Test ext_authz endpoint directly:
```bash
kubectl exec -n stoa-system deployment/webmethods-with-stoa-sidecar -c webmethods -- \
  curl -s http://127.0.0.1:8081/authz -X POST -H "Content-Type: application/json" -d '{}'
```

### Gateway Shows OFFLINE

If the gateway shows OFFLINE in Console but is running:

1. Check heartbeat is being sent:
   ```bash
   kubectl logs -n stoa-system deployment/webmethods-with-stoa-sidecar -c stoa-sidecar | grep heartbeat
   ```

2. Verify Control Plane API key:
   ```bash
   kubectl get secret stoa-sidecar-secrets -n stoa-system -o jsonpath='{.data.control-plane-api-key}' | base64 -d
   ```

3. Ensure the API key is in the `GATEWAY_API_KEYS` list in Control Plane config.

## Related Documentation

- [ADR-028: Gateway Auto-Registration](../architecture/adr/adr-028-gateway-auto-registration.md)
- [ADR-024: Gateway Unified Modes](https://docs.gostoa.dev/architecture/adr/adr-024-gateway-unified-modes)
- [Control Plane Agnostique Plan](../plans/control-plane-agnostique.md)
