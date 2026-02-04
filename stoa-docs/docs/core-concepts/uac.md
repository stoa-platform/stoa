---
sidebar_position: 4
title: Universal API Contract
description: UAC — the normalized API definition model in STOA.
---

# Universal API Contract (UAC)

The Universal API Contract (UAC) is STOA's **gateway-agnostic API definition format**. It normalizes API specifications into a common model that can be reconciled to any supported gateway.

## Why UAC?

Different API gateways use different configuration formats:

- webMethods uses its own REST API with specific resource models
- Kong uses declarative YAML with services, routes, and plugins
- Apigee uses API proxies with proxy endpoints and target endpoints

UAC provides a single definition that STOA translates to each gateway's native format through the [Gateway Adapter](../guides/console#gateway-adapters) pattern.

## UAC Structure

A UAC definition captures everything needed to deploy an API:

```yaml
apiName: petstore
apiVersion: 1.0.0
tenant: acme
displayName: Petstore API
description: Manage pets in the store

# API specification
spec:
  format: openapi3
  url: https://api.example.com/v1/openapi.json

# Backend endpoint
endpoint:
  url: https://backend.acme.internal/pets
  method: REST
  timeout: 30s

# Access control
auth:
  type: oauth2
  scopes:
    - read:pets
    - write:pets

# Policies
policies:
  - type: rate_limit
    config:
      requests_per_minute: 600
  - type: cors
    config:
      allowed_origins: ["https://app.acme.com"]
  - type: logging
    config:
      level: info

# Portal visibility
portal:
  visible: true
  categories: ["pets", "demo"]
```

## UAC in the GitOps Flow

The UAC is the artifact that flows through the GitOps pipeline:

```
Console UI / CLI / API
        │
        ▼
  Control Plane API
        │ (writes UAC)
        ▼
  GitLab Repository
        │
        ▼
  ArgoCD (detects change)
        │
        ▼
  AWX / Ansible
        │ (reads UAC)
        ▼
  Gateway Adapter
        │ (translates UAC → native format)
        ▼
  Target Gateway (webMethods, Kong, ...)
```

## UAC Components

### API Identity

| Field | Required | Description |
|-------|----------|-------------|
| `apiName` | Yes | Unique API identifier within tenant |
| `apiVersion` | Yes | Semantic version string |
| `tenant` | Yes | Owning tenant ID |
| `displayName` | No | Human-readable name |
| `description` | No | API description |

### Endpoint

| Field | Required | Description |
|-------|----------|-------------|
| `url` | Yes | Backend service URL |
| `method` | No | Protocol (REST, GraphQL, gRPC) |
| `timeout` | No | Request timeout |

### Policies

Policies are applied in order and translated to gateway-native plugins/handlers:

| Policy Type | Description |
|-------------|-------------|
| `rate_limit` | Request throttling per consumer |
| `cors` | Cross-origin resource sharing rules |
| `jwt` | JWT validation and claims extraction |
| `ip_filter` | IP allowlist/denylist |
| `logging` | Request/response logging level |
| `transform` | Header/body transformation rules |

### Auth Configuration

| Auth Type | Description |
|-----------|-------------|
| `oauth2` | OAuth 2.0 with scopes |
| `api_key` | API key in header or query |
| `basic` | HTTP Basic authentication |
| `none` | Public API (no auth) |

## Gateway Adapter Translation

Each Gateway Adapter implements the translation from UAC to native format:

```python
class GatewayAdapterInterface:
    def sync_api(self, api_spec: dict, tenant_id: str) -> AdapterResult:
        """Translate UAC and sync to target gateway."""

    def upsert_policy(self, policy_spec: dict) -> AdapterResult:
        """Translate and apply policy."""

    def provision_application(self, app_spec: dict) -> AdapterResult:
        """Provision consumer access."""
```

The adapter guarantees **idempotent** operations — syncing the same UAC twice produces identical results on the gateway.

## Shadow Mode (Future)

In the planned **shadow** gateway mode, STOA will be able to auto-generate UAC definitions by passively capturing API traffic. This enables onboarding existing APIs without manual specification:

1. Deploy STOA Gateway in shadow mode alongside existing traffic
2. Capture request/response patterns
3. Auto-generate UAC with inferred schemas and policies
4. Review and publish via Console UI
