---
sidebar_position: 1
title: APIs
description: Define, publish, version, and manage APIs in STOA.
---

# APIs

APIs are the primary resource in STOA. Each API belongs to a tenant and goes through a managed lifecycle from draft to production.

## API Lifecycle

```
Draft → Published → Deprecated → Retired
```

| State | Description |
|-------|-------------|
| **Draft** | API is being configured. Not visible in the Portal. |
| **Published** | API is live, discoverable, and available for subscriptions. |
| **Deprecated** | API still works but consumers are warned to migrate. |
| **Retired** | API is deactivated. No traffic is accepted. |

## Creating an API

APIs are created within a tenant context. You can use the Console UI, CLI, or API directly.

### Via Console UI

1. Navigate to **APIs → Create API**
2. Enter name, version, and description
3. Upload or link an OpenAPI specification
4. Configure policies (rate limiting, CORS, authentication)
5. Click **Publish** when ready

### Via CLI

```bash
stoa api create \
  --tenant my-org \
  --name petstore \
  --version 1.0.0 \
  --spec ./openapi.json
```

### Via API

```bash
curl -X POST https://api.gostoa.dev/v1/tenants/my-org/apis \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "petstore",
    "version": "1.0.0",
    "displayName": "Petstore API",
    "specUrl": "https://petstore3.swagger.io/api/v3/openapi.json"
  }'
```

## Versioning

STOA supports multiple API versions running simultaneously. Each version is a separate resource with its own spec, policies, and subscriptions.

```
petstore v1.0.0  → Published
petstore v2.0.0  → Published
petstore v1.0.0  → Deprecated (after migration period)
```

Consumers subscribe to a specific version. When you publish a new version, existing subscriptions continue to work on their version until migrated.

## Policies

Policies are attached to APIs to control access and behavior:

| Policy | Purpose |
|--------|---------|
| **Rate Limiting** | Throttle requests per consumer |
| **CORS** | Control cross-origin access |
| **JWT Validation** | Require and validate JWT tokens |
| **IP Filtering** | Allow/deny by source IP |
| **Logging** | Configure request/response logging |

Policies are defined declaratively in Git and reconciled to the gateway via the Gateway Adapter.

## Gateway Sync

When an API is published, STOA syncs the definition to the target API gateway:

1. API spec written to GitLab repository
2. ArgoCD detects the change and syncs to Kubernetes
3. AWX triggers an Ansible playbook
4. Gateway Adapter reconciles the API on the target gateway (webMethods, Kong, etc.)

The adapter ensures idempotent sync — running it multiple times produces the same result.

## API in the MCP Gateway

Published APIs can also be registered as **tools** in the MCP Gateway, making them available to AI agents:

```yaml
apiVersion: gostoa.dev/v1alpha1
kind: Tool
metadata:
  name: petstore-list-pets
  namespace: tenant-my-org
spec:
  displayName: List Pets
  description: Retrieve a list of pets from the store
  endpoint: https://api.example.com/v1/pets
  method: GET
  inputSchema:
    type: object
    properties:
      limit:
        type: integer
        description: Maximum number of pets to return
```

See [MCP Gateway](./mcp-gateway) for details.
