# Installation

## Prerequisites

Before installing STOA Platform, ensure:

- Kubernetes cluster 1.28+ is running and `kubectl` is configured
- Helm 3.x is installed
- PostgreSQL 15 instance is accessible
- Keycloak 24 instance is running with a `stoa` realm
- Vault is running and unsealed (optional — can use K8s secrets directly)
- Namespace `stoa-system` exists or will be created

## Step 1 — Install CRDs

Custom Resource Definitions must be applied before the Helm chart:

```bash
kubectl apply -f charts/stoa-platform/crds/
```

Verify CRDs are registered:

```bash
kubectl get crds | grep gostoa.dev
```

Expected output:

```
tools.gostoa.dev        2026-01-15T10:00:00Z
toolsets.gostoa.dev     2026-01-15T10:00:00Z
```

## Step 2 — Configure Values

Copy and edit the Helm values file:

```bash
cp charts/stoa-platform/values.yaml my-values.yaml
```

Key values to set:

```yaml
global:
  baseDomain: "gostoa.dev"        # Your base domain
  registry: "your-registry.com"    # Container registry

controlPlaneApi:
  image:
    tag: "latest"
  database:
    host: "postgresql.stoa-system.svc"
    name: "stoa"

keycloak:
  url: "https://auth.gostoa.dev"
  realm: "stoa"
  clientId: "control-plane-ui"

externalSecret:
  enabled: false                   # Set true if using Vault + ESO
  secretStoreRef: vault-backend
  vaultPath: stoa/data/gateway
```

## Step 3 — Helm Install

```bash
helm upgrade --install stoa-platform ./charts/stoa-platform \
  -n stoa-system \
  --create-namespace \
  -f my-values.yaml
```

## Step 4 — Post-Install Checks

### Verify pods are running

```bash
kubectl get pods -n stoa-system
```

All pods should be `Running` with `READY` showing full replicas (e.g., `1/1`).

### Verify health endpoints

```bash
# Control Plane API
curl -s https://api.<BASE_DOMAIN>/health/ready
# Expected: {"status": "ok"}

# Control Plane API — detailed
curl -s https://api.<BASE_DOMAIN>/health/live
curl -s https://api.<BASE_DOMAIN>/health/startup

# MCP Gateway
curl -s https://mcp.<BASE_DOMAIN>/health
# Expected: {"status": "ok"}

# Keycloak OIDC
curl -s https://auth.<BASE_DOMAIN>/realms/stoa/.well-known/openid-configuration | head -5
```

### Verify services

```bash
kubectl get svc -n stoa-system
```

Expected services:

| Service | Type | Port |
|---------|------|------|
| control-plane-api | ClusterIP | 8000 |
| control-plane-ui | ClusterIP | 80 |
| portal | ClusterIP | 80 |
| mcp-gateway | ClusterIP | 8080 |
| stoa-gateway | ClusterIP | 8443 |

### Verify ingress

```bash
kubectl get ingress -n stoa-system
```

## Step 5 — Run Database Migrations

If this is a fresh install:

```bash
kubectl exec -it deploy/control-plane-api -n stoa-system -- \
  alembic upgrade head
```

## Step 6 — Create Initial Tenant

```bash
# Get admin token
TOKEN=$(curl -s -X POST "https://auth.<BASE_DOMAIN>/realms/stoa/protocol/openid-connect/token" \
  -d "grant_type=client_credentials&client_id=admin-cli&client_secret=<secret>" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Create tenant
curl -X POST "https://api.<BASE_DOMAIN>/v1/tenants" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-tenant", "display_name": "My Tenant"}'
```

## Uninstall

```bash
helm uninstall stoa-platform -n stoa-system
kubectl delete -f charts/stoa-platform/crds/   # Only if removing CRDs
kubectl delete namespace stoa-system             # Only if removing everything
```

> **Warning**: Deleting CRDs will remove all Tool and ToolSet custom resources across all namespaces.
