# Gateway Auto-Registration Guide

This guide explains how to configure and deploy STOA gateways with automatic registration to the Control Plane.

## Overview

STOA gateways can automatically register with the Control Plane at startup, eliminating the need for manual registration via API calls. This provides an "Apple ecosystem" experience where gateways appear in the Console UI within seconds of deployment.

**Key benefits:**
- Zero-config deployment (2 environment variables)
- Automatic re-registration on restart
- Real-time health visibility via heartbeat
- Self-healing (gateway recovery is automatic)

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Control Plane API                            │
│                                                                 │
│  ┌─────────────────────┐    ┌────────────────────────────────┐  │
│  │  Gateway Internal   │    │   Gateway Health Worker        │  │
│  │  /v1/internal/gateways   │   Marks stale gateways OFFLINE │  │
│  │  - /register        │    │   (90s timeout)                │  │
│  │  - /{id}/heartbeat  │    └────────────────────────────────┘  │
│  │  - /{id}/config     │                                        │
│  └─────────┬───────────┘                                        │
└────────────┼────────────────────────────────────────────────────┘
             │
             │ HTTPS (X-Gateway-Key header)
             │
    ┌────────┴────────┐              ┌────────────────┐
    │  STOA Gateway   │              │ STOA Sidecar   │
    │  (edge-mcp)     │              │ + Kong/Envoy   │
    │                 │              │                │
    │  1. Register    │              │  ext_authz     │
    │  2. Heartbeat   │              │  ↓             │
    │     (30s)       │              │  Policy/Meter  │
    └─────────────────┘              └────────────────┘
```

## Quick Start

### Tier 1: STOA Native Gateway

Deploy a STOA gateway with automatic registration:

```bash
# Minimal configuration (2 env vars)
export STOA_CONTROL_PLANE_URL=https://api.gostoa.dev
export STOA_CONTROL_PLANE_API_KEY=gw_your_key_here

# Start the gateway
./stoa-gateway
```

The gateway will:
1. Derive identity from hostname + mode + environment
2. Call `POST /v1/internal/gateways/register`
3. Start heartbeat loop (every 30 seconds)
4. Appear in Console UI at `/gateways`

### Tier 2: Sidecar Mode

Deploy STOA as a sidecar alongside a third-party gateway:

```yaml
# Kubernetes deployment example
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kong-with-stoa-sidecar
spec:
  template:
    spec:
      containers:
        # Main gateway (Kong)
        - name: kong
          image: kong:3.5
          env:
            - name: KONG_PLUGINS
              value: "ext-authz"
            - name: KONG_EXT_AUTHZ_URL
              value: "http://localhost:8081/authz"
          ports:
            - containerPort: 8000

        # STOA sidecar
        - name: stoa-sidecar
          image: ghcr.io/stoa/stoa-gateway:latest
          env:
            - name: STOA_GATEWAY_MODE
              value: "sidecar"
            - name: STOA_CONTROL_PLANE_URL
              value: "https://api.gostoa.dev"
            - name: STOA_CONTROL_PLANE_API_KEY
              valueFrom:
                secretKeyRef:
                  name: stoa-sidecar-secrets
                  key: control-plane-api-key
          ports:
            - containerPort: 8081  # ext_authz endpoint
```

## Control Plane Configuration

### 1. Create Gateway API Keys

Configure the Control Plane to accept gateway registrations:

```bash
# Create Kubernetes secret with API keys
kubectl create secret generic stoa-gateway-api-keys \
  --namespace stoa-system \
  --from-literal=GATEWAY_API_KEYS="gw_prod_key_abc123,gw_staging_key_xyz789"
```

**Key format**: Any string, but we recommend the format `gw_{environment}_{random}`.

**Key rotation**: Multiple keys are supported (comma-separated). Add a new key before removing the old one.

### 2. Deploy Control Plane with Keys

Patch the Control Plane deployment:

```bash
kubectl patch deployment control-plane-api -n stoa-system \
  --type='json' \
  -p='[{"op": "add", "path": "/spec/template/spec/containers/0/env/-", "value": {"name": "GATEWAY_API_KEYS", "valueFrom": {"secretKeyRef": {"name": "stoa-gateway-api-keys", "key": "GATEWAY_API_KEYS"}}}}]'
```

Or via Helm:

```yaml
# values.yaml
controlPlane:
  env:
    GATEWAY_API_KEYS:
      secretKeyRef:
        name: stoa-gateway-api-keys
        key: GATEWAY_API_KEYS
```

## Gateway Configuration Reference

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `STOA_CONTROL_PLANE_URL` | Yes | - | Control Plane API URL |
| `STOA_CONTROL_PLANE_API_KEY` | Yes | - | Shared secret for authentication |
| `STOA_GATEWAY_MODE` | No | `edge-mcp` | Gateway mode: `edge-mcp`, `sidecar`, `proxy`, `shadow` |
| `STOA_ENVIRONMENT` | No | `dev` | Environment identifier for grouping |
| `STOA_TENANT_ID` | No | - | Optional tenant restriction |

### Registration Payload

The gateway sends this payload at startup:

```json
{
  "hostname": "stoa-gateway-7f8b9c",
  "mode": "edge-mcp",
  "version": "0.1.0",
  "environment": "prod",
  "capabilities": ["rest", "mcp", "sse", "oidc", "rate_limiting"],
  "admin_url": "http://10.0.1.50:8080",
  "tenant_id": null
}
```

### Heartbeat Payload

Every 30 seconds:

```json
{
  "uptime_seconds": 3600,
  "routes_count": 15,
  "policies_count": 5,
  "requests_total": 10000,
  "error_rate": 0.01
}
```

## Identity Derivation

Gateway identity is deterministic: `{hostname}-{mode_normalized}-{environment}`

| Hostname | Mode | Environment | Derived Name |
|----------|------|-------------|--------------|
| `stoa-gw-abc123` | `edge-mcp` | `prod` | `stoa-gw-abc123-edgemcp-prod` |
| `kong-sidecar-xyz` | `sidecar` | `staging` | `kong-sidecar-xyz-sidecar-staging` |

This enables:
- **Idempotent registration**: Same gateway restarts update rather than duplicate
- **Clear naming**: Easy to identify in Console UI
- **Environment filtering**: Group gateways by environment

## Helm Chart Configuration

### STOA Sidecar (Tier 2)

Full configuration in `charts/stoa-platform/values.yaml`:

```yaml
stoaSidecar:
  enabled: true
  targetGateway: webmethods  # or kong, envoy, apigee, generic

  image:
    repository: ghcr.io/stoa/stoa-gateway
    tag: latest

  replicas: 2
  environment: prod

  # Control Plane connection
  controlPlaneUrl: "http://control-plane-api.stoa-system.svc.cluster.local:8000"
  secretName: stoa-sidecar-secrets  # Must contain control-plane-api-key

  # Keycloak OIDC (for token validation)
  keycloakUrl: "https://auth.gostoa.dev"
  keycloakRealm: stoa
  keycloakClientId: stoa-sidecar

  # Policy enforcement
  policyEnabled: true

  # Main gateway container (runs alongside)
  mainGateway:
    enabled: true
    image:
      repository: softwareag/webmethods-api-gateway
      tag: "10.15"
    port: 9072
    env:
      - name: EXT_AUTHZ_ENABLED
        value: "true"
```

## Console UI

After registration, gateways appear at **Console → Gateways**:

| Column | Description |
|--------|-------------|
| Name | Derived instance name |
| Type | `stoa`, `stoa_sidecar`, `webmethods`, etc. |
| Status | `ONLINE`, `OFFLINE`, `DEGRADED` |
| Environment | `dev`, `staging`, `prod` |
| Last Seen | Time since last heartbeat |
| Capabilities | Feature badges |

### Status Indicators

| Status | Meaning |
|--------|---------|
| 🟢 ONLINE | Heartbeat received within 90s |
| 🔴 OFFLINE | No heartbeat for > 90s |
| 🟡 DEGRADED | Online but with high error rate |

## Troubleshooting

### Gateway Not Appearing in Console

1. **Check gateway logs for registration errors:**
   ```bash
   kubectl logs -n stoa-system deployment/stoa-gateway | grep -i register
   ```

2. **Verify Control Plane has API keys configured:**
   ```bash
   kubectl get secret stoa-gateway-api-keys -n stoa-system -o jsonpath='{.data.GATEWAY_API_KEYS}' | base64 -d
   ```

3. **Check Control Plane logs:**
   ```bash
   kubectl logs -n stoa-system deployment/control-plane-api | grep -i gateway
   ```

4. **Test registration endpoint manually:**
   ```bash
   curl -X POST https://api.gostoa.dev/v1/internal/gateways/register \
     -H "X-Gateway-Key: gw_your_key" \
     -H "Content-Type: application/json" \
     -d '{
       "hostname": "test-gateway",
       "mode": "edge-mcp",
       "version": "0.1.0",
       "environment": "dev",
       "capabilities": ["rest"],
       "admin_url": "http://localhost:8080"
     }'
   ```

### Gateway Shows OFFLINE

1. **Check heartbeat is being sent:**
   ```bash
   kubectl logs -n stoa-system deployment/stoa-gateway | grep heartbeat
   ```

2. **Verify network connectivity to Control Plane:**
   ```bash
   kubectl exec -n stoa-system deployment/stoa-gateway -- \
     curl -s http://control-plane-api.stoa-system.svc.cluster.local:8000/health
   ```

3. **Check for heartbeat 404 errors:**
   ```bash
   # The URL must be /{gateway_id}/heartbeat, not /heartbeat/{gateway_id}
   kubectl logs -n stoa-system deployment/stoa-gateway | grep 404
   ```

### Registration Returns 503

**Cause**: `GATEWAY_API_KEYS` not configured in Control Plane.

**Fix**:
```bash
# Create secret
kubectl create secret generic stoa-gateway-api-keys \
  --namespace stoa-system \
  --from-literal=GATEWAY_API_KEYS="gw_your_key_here"

# Patch deployment
kubectl patch deployment control-plane-api -n stoa-system \
  --type='json' \
  -p='[{"op": "add", "path": "/spec/template/spec/containers/0/env/-", "value": {"name": "GATEWAY_API_KEYS", "valueFrom": {"secretKeyRef": {"name": "stoa-gateway-api-keys", "key": "GATEWAY_API_KEYS"}}}}]'

# Wait for rollout
kubectl rollout status deployment/control-plane-api -n stoa-system
```

### Registration Returns 401

**Cause**: Gateway API key doesn't match any key in `GATEWAY_API_KEYS`.

**Fix**: Verify the key matches:
```bash
# Check what keys are configured
kubectl get secret stoa-gateway-api-keys -n stoa-system \
  -o jsonpath='{.data.GATEWAY_API_KEYS}' | base64 -d

# Check what key the gateway is using
kubectl exec -n stoa-system deployment/stoa-gateway -- env | grep STOA_CONTROL_PLANE_API_KEY
```

## Security Considerations

### API Key Management

- **Never commit keys to Git**: Use Kubernetes Secrets or external secrets manager
- **Use environment-specific keys**: Different keys for dev, staging, prod
- **Rotate keys periodically**: Add new key → update gateways → remove old key
- **Audit registrations**: Check Control Plane logs for unexpected registrations

### Network Security

- Internal endpoints (`/v1/internal/*`) should NOT be exposed via public ingress
- Use Kubernetes NetworkPolicies to restrict which pods can call the internal API
- Consider mTLS for high-security deployments (future enhancement)

### Key Rotation Procedure

1. **Add new key to Control Plane:**
   ```bash
   kubectl patch secret stoa-gateway-api-keys -n stoa-system \
     --type='json' \
     -p='[{"op": "replace", "path": "/data/GATEWAY_API_KEYS", "value": "'$(echo -n "gw_old_key,gw_new_key" | base64)'"}]'
   ```

2. **Restart Control Plane to pick up new key:**
   ```bash
   kubectl rollout restart deployment/control-plane-api -n stoa-system
   ```

3. **Update gateways to use new key:**
   ```bash
   kubectl set env deployment/stoa-gateway \
     STOA_CONTROL_PLANE_API_KEY=gw_new_key -n stoa-system
   ```

4. **Remove old key after all gateways updated:**
   ```bash
   kubectl patch secret stoa-gateway-api-keys -n stoa-system \
     --type='json' \
     -p='[{"op": "replace", "path": "/data/GATEWAY_API_KEYS", "value": "'$(echo -n "gw_new_key" | base64)'"}]'
   ```

## Related Documentation

- [ADR-028: Gateway Auto-Registration](../architecture/adr/adr-028-gateway-auto-registration.md) — Architecture decision record
- [ADR-024: Gateway Unified Modes](https://docs.gostoa.dev/architecture/adr/adr-024-gateway-unified-modes) — Gateway modes (edge-mcp, sidecar, proxy, shadow)
- [WebMethods Sidecar Integration](../integrations/webmethods-sidecar-integration.md) — Specific guide for WebMethods
- [Gateway Adapter Pattern](../architecture/adr/adr-027-gateway-adapter-pattern.md) — How CP orchestrates gateways
