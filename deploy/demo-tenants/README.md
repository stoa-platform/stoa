# Demo Tenants (CAB-279)

Demo tenant configuration for STOA MVP presentation demonstrating multi-tenant isolation.

## Overview

This directory contains Kubernetes manifests for two demo tenants and their tool subscriptions:

| Tenant | Description | Tools | Admin User |
|--------|-------------|-------|------------|
| **team-alpha** | Sales & Finance | crm-search, billing-invoice | e2e-tenant-admin |
| **team-beta** | Operations | inventory-lookup, notifications-send | e2e-devops |

## Prerequisites

1. **STOA Platform deployed** with Control-Plane API running
2. **Demo MCP tools deployed** from `deploy/demo-tools/`
3. **E2E test users created** (from CAB-238):
   - `e2e-admin` - Platform admin
   - `e2e-tenant-admin` - Tenant admin for team-alpha
   - `e2e-devops` - DevOps user for team-beta
   - `e2e-viewer` - Read-only user (both tenants)

## Directory Structure

```
deploy/demo-tenants/
├── README.md              # This file
├── kustomization.yaml     # Kustomize configuration
├── team-alpha.yaml        # Team Alpha tenant + namespace
├── team-beta.yaml         # Team Beta tenant + namespace
└── subscriptions.yaml     # Pre-approved tool subscriptions
```

## Deployment

### Option 1: Using Kustomize (Kubernetes CRDs)

```bash
# Preview what will be created
kubectl kustomize deploy/demo-tenants/

# Apply to cluster
kubectl apply -k deploy/demo-tenants/

# Verify tenants
kubectl get tenants -n stoa-system
kubectl get subscriptions -n stoa-system -l stoa.cab-i.com/demo=true
```

### Option 2: Using Seed Script (Control-Plane API)

The seed script creates tenants via the Control-Plane API (useful when CRD controllers aren't running):

```bash
# Install dependencies
pip install httpx

# Run with default settings (localhost)
python scripts/seed-demo-data.py

# Run with custom URLs (production)
CONTROL_PLANE_URL=https://api.stoa.cab-i.com \
KEYCLOAK_URL=https://auth.stoa.cab-i.com \
ADMIN_USERNAME=e2e-admin \
ADMIN_PASSWORD=Admin123! \
python scripts/seed-demo-data.py
```

## Access Matrix

| User | Tenant | Role | Accessible Tools |
|------|--------|------|------------------|
| e2e-tenant-admin | team-alpha | admin | crm-search, billing-invoice |
| e2e-devops | team-beta | admin | inventory-lookup, notifications-send |
| e2e-viewer | team-alpha | viewer | Read-only access |
| e2e-viewer | team-beta | viewer | Read-only access |
| e2e-admin | all | platform-admin | Full access (Grafana, AWX) |

## Tenant Details

### Team Alpha (Sales & Finance)

- **Contact**: alice@demo.stoa.io
- **Quota**: 10 subscriptions, 10,000 requests/day
- **Rate Limit**: 100 req/min, burst 20
- **Tools**:
  - `team_alpha_crm_search` - CRM customer search
  - `team_alpha_billing_invoice` - Invoice generation

### Team Beta (Operations)

- **Contact**: bob@demo.stoa.io
- **Quota**: 10 subscriptions, 10,000 requests/day
- **Rate Limit**: 100 req/min, burst 20
- **Tools**:
  - `team_beta_inventory_lookup` - Inventory queries
  - `team_beta_notifications_send` - Send notifications

## Testing Multi-Tenant Isolation

### 1. Verify Tenant Tools via MCP Gateway

```bash
# Port-forward to MCP Gateway
kubectl port-forward -n stoa-system svc/stoa-mcp-gateway 8080:8080

# Get auth token for team-alpha user
TOKEN=$(curl -s -X POST "https://auth.stoa.cab-i.com/realms/stoa/protocol/openid-connect/token" \
  -d "grant_type=password" \
  -d "client_id=stoa-portal" \
  -d "username=e2e-tenant-admin" \
  -d "password=Admin123!" | jq -r '.access_token')

# List tools (should only see team-alpha tools)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/mcp/v1/tools | jq '.tools[].name'
```

### 2. Test Tool Invocation

```bash
# Invoke crm-search (should succeed for team-alpha user)
curl -X POST "http://localhost:8080/mcp/v1/tools/team_alpha_crm_search/invoke" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"arguments": {"query": "Acme Corp", "limit": 5}}'

# Try to invoke team-beta tool (should be denied)
curl -X POST "http://localhost:8080/mcp/v1/tools/team_beta_inventory_lookup/invoke" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"arguments": {"sku": "SKU-001"}}'
# Expected: 403 Forbidden
```

### 3. Verify via Control-Plane API

```bash
# Get tenants
curl -H "Authorization: Bearer $TOKEN" https://api.stoa.cab-i.com/v1/tenants

# Get subscriptions for team-alpha
curl -H "Authorization: Bearer $TOKEN" https://api.stoa.cab-i.com/v1/subscriptions?tenant_id=team-alpha
```

## Cleanup

```bash
# Remove demo tenants
kubectl delete -k deploy/demo-tenants/

# Or selectively
kubectl delete tenant team-alpha team-beta -n stoa-system
kubectl delete subscription -n stoa-system -l stoa.cab-i.com/demo=true
kubectl delete namespace team-alpha team-beta
```

## Related

- [Demo MCP Tools](../demo-tools/README.md) - The tools these tenants subscribe to
- [E2E Test Users](../../scripts/setup_test_users.sh) - CAB-238 user setup
- [MCP Gateway](../../mcp-gateway/README.md) - Gateway documentation
