# STOA Hybrid Gateway Adapter — Bring Your Own Gateway

## Overview

STOA's Gateway Adapter Pattern allows you to orchestrate **any API gateway** through a unified, gateway-agnostic interface. Your APIs, policies, OIDC configuration, and applications are declared in Git; the adapter translates them into gateway-specific REST calls during the GitOps reconciliation cycle.

```
Git (desired state) → ArgoCD → AWX → Ansible → Gateway Adapter → Your Gateway
```

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  STOA Control Plane                  │
│              GitOps Reconciliation Engine             │
├──────────┬──────────┬──────────┬────────────────────┤
│ webMethods│  Kong    │  Apigee  │  AWS API Gateway   │
│ Adapter  │ Adapter  │ Adapter  │     Adapter        │
│    ✅    │   🔜    │   🔜    │       🔜           │
├──────────┴──────────┴──────────┴────────────────────┤
│          GatewayAdapterInterface (ABC)               │
│  health_check · sync_api · upsert_policy · ...       │
└─────────────────────────────────────────────────────┘
```

### Interface Contract

Every adapter implements `GatewayAdapterInterface` (see [spec](../reference/gateway-adapter-spec.md)). Key properties:

- **Idempotent**: Calling the same operation twice produces the same result
- **Declarative**: You specify desired state, the adapter computes the diff
- **Auth-agnostic**: Supports both OIDC proxy (JWT forwarding) and Basic Auth

### Reconciliation Lifecycle

```
PHASE 0:   health_check()         → Verify gateway is reachable
PHASE 1:   (load from Git)        → Read tenant/API definitions
PHASE 1.5: upsert_policy()        → Sync policies (CORS, rate-limit, etc.)
PHASE 1.7: upsert_auth_server()   → Sync OIDC (Keycloak, Okta, etc.)
PHASE 2:   list_apis()            → Fetch current gateway state
PHASE 3:   (compute diff)         → Compare Git vs gateway
PHASE 4:   sync_api()             → Create/update/delete APIs
PHASE 4.5: provision_application() → Sync OAuth applications
PHASE 5:   (portal visibility)    → Publish/unpublish from portal
PHASE 6:   apply_config()         → Global gateway configuration
PHASE 7:   export_archive()       → Backup gateway state
```

## Implementing a New Adapter

### 1. Create the adapter module

```
control-plane-api/src/adapters/
├── gateway_adapter_interface.py   # Don't modify
├── __init__.py
├── webmethods/                    # Reference implementation
│   ├── adapter.py
│   └── mappers.py
└── kong/                          # Your new adapter
    ├── __init__.py
    ├── adapter.py
    └── mappers.py
```

### 2. Implement the interface

```python
from ..gateway_adapter_interface import GatewayAdapterInterface, AdapterResult

class KongGatewayAdapter(GatewayAdapterInterface):
    async def health_check(self) -> AdapterResult:
        # GET /status on Kong Admin API
        ...

    async def sync_api(self, api_spec: dict, tenant_id: str,
                       auth_token=None) -> AdapterResult:
        # POST /services + POST /routes on Kong Admin API
        ...

    # ... implement all abstract methods
```

### 3. Register the adapter

In `provisioning_service.py`, swap the adapter:

```python
from ..adapters.kong import KongGatewayAdapter
gateway_adapter = KongGatewayAdapter()
```

### 4. Update Ansible tasks (optional)

For full GitOps reconciliation, create gateway-specific Ansible tasks or reuse the generic ones with the adapter's REST mappings.

## Supported Gateways

| Gateway | Status | Adapter |
|---------|--------|---------|
| webMethods 10.x/11.x | ✅ Production | `adapters/webmethods/` |
| Kong | 🔜 Planned Q3 2026 | — |
| Apigee | 🔜 Planned Q4 2026 | — |
| AWS API Gateway | 🔜 Planned Q4 2026 | — |

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WM_GATEWAY_URL` | `http://apim-gateway:5555` | webMethods admin URL |
| `WM_ADMIN_USER` | `Administrator` | Admin username (Basic Auth) |
| `WM_ADMIN_PASSWORD` | — | Admin password (Basic Auth) |
| `GATEWAY_USE_OIDC_PROXY` | `false` | Use OIDC proxy mode |
| `GATEWAY_ADMIN_PROXY_URL` | — | OIDC proxy URL |

### Git Structure

```
platform/webmethods/
├── aliases/
│   ├── dev.yaml
│   ├── staging.yaml
│   └── prod.yaml
├── policies/
│   ├── cors-platform.yaml
│   ├── rate-limit-default.yaml
│   └── logging-standard.yaml
├── oidc/
│   └── keycloak-auth-server.yaml
├── config/
│   └── gateway-config.yaml
└── applications/
    └── .gitkeep
```

## Local Development

```bash
# Start local webMethods sandbox
docker compose -f deploy/docker-compose/docker-compose.webmethods.yml up -d

# Run smoke test
./scripts/test-gateway-api.sh http://localhost:5555

# Run reconciliation in dry-run
ansible-playbook stoa-infra:ansible/reconcile-webmethods/reconcile-webmethods.yml \
  -e "env=dev" --check
```
