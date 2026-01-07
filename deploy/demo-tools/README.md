# Demo MCP Tools (CAB-290)

This directory contains demo MCP tools to illustrate **multi-tenant isolation** in the STOA Platform.

## Overview

| Tool | Tenant | Category | Description |
|------|--------|----------|-------------|
| `crm-search` | team-alpha | Sales | Search customers in CRM database |
| `billing-invoice` | team-alpha | Finance | Generate invoices for customers |
| `inventory-lookup` | team-beta | Operations | Check stock levels across warehouses |
| `notifications-send` | team-beta | Communications | Send notifications via multiple channels |

## Multi-Tenant Isolation

These tools demonstrate tenant isolation:

- **team-alpha** can only access: `crm-search`, `billing-invoice`
- **team-beta** can only access: `inventory-lookup`, `notifications-send`

The MCP Gateway enforces this isolation via:
1. Kubernetes namespace separation
2. OPA policies based on JWT claims
3. Tool CRD ownership labels

## Prerequisites

Before deploying demo tools, ensure the MCP Gateway has RBAC permissions to watch Tool CRDs:

```bash
# Create ServiceAccount and RBAC (if not already done via Helm)
kubectl apply -f - <<EOF
apiVersion: v1
kind: ServiceAccount
metadata:
  name: stoa-mcp-gateway
  namespace: stoa-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: stoa-mcp-gateway-tools
rules:
  - apiGroups: ["stoa.cab-i.com"]
    resources: ["tools", "toolsets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["stoa.cab-i.com"]
    resources: ["tools/status", "toolsets/status"]
    verbs: ["get", "patch", "update"]
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: stoa-mcp-gateway-tools
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: stoa-mcp-gateway-tools
subjects:
  - kind: ServiceAccount
    name: stoa-mcp-gateway
    namespace: stoa-system
EOF

# Ensure MCP Gateway deployment uses the service account
kubectl patch deployment mcp-gateway -n stoa-system \
  --type='json' \
  -p='[{"op": "add", "path": "/spec/template/spec/serviceAccountName", "value": "stoa-mcp-gateway"}]'
```

## Deployment

### Deploy All Tools

```bash
# Using kustomize
kubectl apply -k deploy/demo-tools/

# Or individually
kubectl apply -f deploy/demo-tools/crm-search.yaml
kubectl apply -f deploy/demo-tools/billing-invoice.yaml
kubectl apply -f deploy/demo-tools/inventory-lookup.yaml
kubectl apply -f deploy/demo-tools/notifications-send.yaml
```

### Verify Deployment

```bash
# List all tools in Kubernetes
kubectl get tools -A

# List team-alpha tools
kubectl get tools -n team-alpha

# List team-beta tools
kubectl get tools -n team-beta

# Describe a specific tool
kubectl describe tool crm-search -n team-alpha
```

### Verify Tools in MCP Gateway API

```bash
# Port-forward to MCP Gateway
kubectl port-forward deployment/mcp-gateway -n stoa-system 8080:8080 &

# List all registered tools (should include K8s-based tools)
curl -s http://localhost:8080/mcp/v1/tools | jq '.tools[] | {name, tenant_id, description}'

# Expected output includes:
# - team_alpha_crm_search
# - team_alpha_billing_invoice
# - team_beta_inventory_lookup
# - team_beta_notifications_send

# Kill port-forward
pkill -f "port-forward.*mcp-gateway"
```

**Note:** Tool names in the MCP API follow the pattern `{namespace}_{tool_name}` (e.g., `team_alpha_crm_search`).

## Testing Multi-Tenant Isolation

### As team-alpha user

```bash
# Get token for team-alpha user
TOKEN=$(curl -s -X POST "https://auth.stoa.cab-i.com/realms/stoa/protocol/openid-connect/token" \
  -d "grant_type=password" \
  -d "client_id=stoa-portal" \
  -d "username=alpha-user" \
  -d "password=demo" | jq -r .access_token)

# List available tools (should see only team-alpha tools)
curl -H "Authorization: Bearer $TOKEN" \
  https://mcp.stoa.cab-i.com/mcp/v1/tools

# Invoke crm-search (should work)
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "team_alpha_crm_search", "arguments": {"query": "ACME"}}' \
  https://mcp.stoa.cab-i.com/mcp/v1/tools/call

# Try inventory-lookup (should be denied - team-beta only)
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "team_beta_inventory_lookup", "arguments": {"sku": "WIDGET-PRO-500"}}' \
  https://mcp.stoa.cab-i.com/mcp/v1/tools/call
# Expected: 403 Forbidden
```

### As team-beta user

```bash
# Get token for team-beta user
TOKEN=$(curl -s -X POST "https://auth.stoa.cab-i.com/realms/stoa/protocol/openid-connect/token" \
  -d "grant_type=password" \
  -d "client_id=stoa-portal" \
  -d "username=beta-user" \
  -d "password=demo" | jq -r .access_token)

# Invoke inventory-lookup (should work)
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "team_beta_inventory_lookup", "arguments": {"sku": "WIDGET-PRO-500"}}' \
  https://mcp.stoa.cab-i.com/mcp/v1/tools/call

# Try crm-search (should be denied - team-alpha only)
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "team_alpha_crm_search", "arguments": {"query": "ACME"}}' \
  https://mcp.stoa.cab-i.com/mcp/v1/tools/call
# Expected: 403 Forbidden
```

## Tool Specifications

### crm-search (team-alpha)

**Input Schema:**
```json
{
  "query": "string (required)",
  "limit": "integer (default: 10)",
  "include_inactive": "boolean (default: false)"
}
```

### billing-invoice (team-alpha)

**Input Schema:**
```json
{
  "customer_id": "string (required)",
  "order_ids": "array of strings",
  "due_days": "integer (default: 30)",
  "include_tax": "boolean (default: true)",
  "currency": "EUR|USD|GBP (default: EUR)"
}
```

### inventory-lookup (team-beta)

**Input Schema:**
```json
{
  "sku": "string (required)",
  "warehouse_id": "string (optional)",
  "include_reserved": "boolean (default: true)",
  "check_reorder": "boolean (default: true)"
}
```

### notifications-send (team-beta)

**Input Schema:**
```json
{
  "recipient": "string (required)",
  "channel": "email|sms|push|slack (required)",
  "message": "string (required)",
  "subject": "string",
  "template_id": "string",
  "template_vars": "object",
  "priority": "low|normal|high|urgent (default: normal)",
  "schedule_at": "ISO 8601 datetime"
}
```

## Cleanup

```bash
# Remove all demo tools
kubectl delete -k deploy/demo-tools/

# Or remove namespaces (deletes everything)
kubectl delete namespace team-alpha team-beta
```

## Related Documentation

- [MCP Gateway Architecture](../../docs/ARCHITECTURE-PRESENTATION.md)
- [Tool CRD Specification](../../charts/stoa-platform/crds/tool-crd.yaml)
- [OPA Policies](../../mcp-gateway/src/policies/)
