# Gateway Registration — Deployment Runbook (CAB-1781)

## Overview

Connect all gateway instances to the Control Plane so they appear in Console UI.

## Prerequisites

1. **Infisical secret**: `STOA_CONTROL_PLANE_API_KEY` in `prod/gateway/`
   - Must match a key in the CP API's `GATEWAY_API_KEYS` env var
   - If `GATEWAY_API_KEYS` is empty, registration returns 503

2. **CP API config**: Verify `GATEWAY_API_KEYS` contains the key
   ```bash
   kubectl exec -n stoa-system deploy/control-plane-api -- env | grep GATEWAY_API_KEYS
   ```

## STOA Gateways (Self-Register)

These gateways auto-register on startup when `STOA_CONTROL_PLANE_URL` + `STOA_CONTROL_PLANE_API_KEY` are set.

### Deploy Steps

For each VPS, add the key to the `.env` file:

```bash
# SSH to VPS, add to .env alongside existing secrets
echo 'STOA_CONTROL_PLANE_API_KEY=<key-from-infisical>' >> .env

# Redeploy
docker compose down && docker compose up -d

# Verify registration (check gateway logs)
docker logs stoa-gateway 2>&1 | grep -i "register"
```

### Instance Inventory

| Instance Name | VPS | Port | Mode | Env |
|---------------|-----|------|------|-----|
| `stoa-arena-vps` | 51.83.45.13 | 8080 | edge-mcp | prod |
| `hegemon-gateway-internal` | Contabo workers | 8090 | edge-mcp | prod |
| `hegemon-gateway-external` | Contabo workers | 8091 | proxy | prod |
| `stoa-quickstart` | Local dev | 8081 | edge-mcp | dev |

### Network Requirements (outbound from VPS)

- HTTPS to `api.gostoa.dev:443` (registration + heartbeat)
- All VPS already have outbound HTTPS — no firewall changes needed

## Third-Party Gateways (Manual Register)

Kong, Gravitee, and webMethods cannot self-register. Use the registration script:

```bash
# Get a cpi-admin Bearer token from Keycloak
export STOA_API_TOKEN="<bearer-token>"

# Register all third-party gateways
./register-gateways.sh
```

### Network Requirements (inbound to VPS admin ports)

The CP API needs to reach VPS admin ports for health checks via adapters:

| Gateway | VPS IP | Admin Port | Protocol |
|---------|--------|------------|----------|
| Kong | 54.36.209.237 | 8001 | HTTP |
| Gravitee | 54.36.209.237 | 8083 | HTTP |
| webMethods | 51.255.201.17 | 5555 | HTTP |

**Firewall rule**: Allow inbound from OVH K8s worker IPs to these ports.
OVH K8s egress IP: check `kubectl get nodes -o wide` for external IPs.

## Staging (Hetzner K3s)

Add to Helm values or K3s deployment:

```yaml
# In stoa-infra Helm values for staging
stoaGateway:
  env:
    STOA_CONTROL_PLANE_URL: "https://api.staging.gostoa.dev"
    STOA_CONTROL_PLANE_API_KEY: "<key>"
    STOA_INSTANCE_NAME: "stoa-staging-k3s"
    STOA_ENVIRONMENT: "staging"
    STOA_AUTO_REGISTER: "true"
```

## Verification

After deployment, verify all gateways appear in Console:

```bash
# API check
curl -s -H "Authorization: Bearer ${TOKEN}" \
  https://api.gostoa.dev/v1/admin/gateways | jq '.items[] | {name, status, gateway_type, source}'

# Expected: 7+ gateways with status "online" (STOA) or registered (third-party)
```

Console URL: https://console.gostoa.dev/gateways

## Rollback

- **STOA gateways**: Remove `STOA_CONTROL_PLANE_API_KEY` from `.env`, redeploy. Gateway runs standalone.
- **Third-party**: Delete from Console UI or `DELETE /v1/admin/gateways/<id>`
- Zero blast radius — registration failure = standalone mode (graceful degradation)
