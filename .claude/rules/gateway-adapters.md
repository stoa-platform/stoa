---
globs: "control-plane-api/src/adapters/**,control-plane-api/tests/test_*_adapter*"
---

# Gateway Adapters — Per-Gateway Rules & Tips

## Architecture Overview

STOA uses the **Adapter pattern** to orchestrate multiple API gateways. All adapters implement `GatewayAdapterInterface` (16 abstract methods). The Control Plane API is the source of truth; gateways are the execution layer.

```
Console → CP API → AdapterRegistry.create(gateway_type) →
  ├─ StoaGatewayAdapter     → Rust stoa-gateway /admin/* (in-memory)
  ├─ KongGatewayAdapter     → Kong Admin API /config (DB-less, declarative reload)
  ├─ GraviteeGatewayAdapter → Gravitee Mgmt API v2 (REST CRUD + lifecycle)
  ├─ WebMethodsGatewayAdapter → webMethods /rest/apigateway/* (via GatewayAdminService)
  ├─ ApigeeGatewayAdapter   → Apigee Mgmt API v1 (Bearer token auth)
  ├─ AwsApiGatewayAdapter   → AWS API Gateway REST API (SigV4 auth)
  └─ AzureApimAdapter       → Azure APIM ARM REST API (Bearer token auth)
```

## Interface Methods (16)

| Category | Methods | Required | Notes |
|----------|---------|----------|-------|
| Lifecycle | `health_check`, `connect`, `disconnect` | All | Always implement |
| APIs | `sync_api`, `delete_api`, `list_apis` | All | Core operations |
| Policies | `upsert_policy`, `delete_policy`, `list_policies` | All | Rate-limit, CORS |
| Applications | `provision_application`, `deprovision_application`, `list_applications` | All | Consumer management |
| Auth/OIDC | `upsert_auth_server`, `upsert_strategy`, `upsert_scope` | Optional | webMethods only |
| Aliases/Config/Backup | `upsert_alias`, `apply_config`, `export_archive` | Optional | webMethods only |

## Key Files

| File | Purpose |
|------|---------|
| `control-plane-api/src/adapters/gateway_adapter_interface.py` | Abstract interface + `AdapterResult` |
| `control-plane-api/src/adapters/registry.py` | Factory: `gateway_type` → adapter class |
| `control-plane-api/src/adapters/{gw}/adapter.py` | Adapter implementation |
| `control-plane-api/src/adapters/{gw}/mappers.py` | Spec translation functions (6 per gateway) |
| `control-plane-api/tests/test_{gw}_adapter.py` | Unit tests (mock httpx) |

---

## Kong (DB-less)

- **Ports**: 8000 (proxy), 8001 (admin). Auth: `Kong-Admin-Token` header. VPS: `<KONG_VPS_IP>`
- **DB-less**: Admin API read-only for writes. Mutations: GET state → merge → `POST /config` (`_format_version: "3.0"`, atomic reload)
- Services nest `routes`. Plugins ref by **name**. Tags: `stoa-policy-{id}`, `stoa-consumer-{subscription_id}`
- **Gotchas**: `tags: null` (not `[]`) — use `get("tags") or []`. `path: null` — use `get('path') or ''`. Plugin service ref: `{id: "..."}` dict. Rate-limit keys: `minute/second/hour/day`. Config reload all-or-nothing. ~38 tests

## Gravitee (APIM v4)

- **Ports**: 8082 (gw), 8083 (mgmt API), 8084 (UI). Auth: Basic `admin:admin`. VPS: `<GRAVITEE_VPS_IP>`
- **Lifecycle**: `POST /apis` → `_start` (may fail V4, non-blocking) → `/deployments`. V4: `definitionVersion: "V4"`, `type: "PROXY"`
- Rate-limiting via Plans with flows. Apps via `/applications`, subscriptions link to plans
- **Gotchas**: Plan tags MUST match API tags (use name-based ID). V4 Plan needs `mode: "STANDARD"`, `characteristics: []`. KEY_LESS can't subscribe (warn). Mgmt v2: `/management/v2/environments/DEFAULT/apis`. Health: v1 path. ~35 tests

## webMethods (IBM/Software AG)

- **Ports**: 5555 (HTTP+admin), 5543 (HTTPS), 9072 (UI). Auth: Basic `Administrator:manage`. Docker: `softwareag/apigateway-trial:10.15`
- Most feature-complete: all 16 methods including OIDC (8-step KC integration), aliases, config, backup
- API import via multipart. Only OpenAPI 3.0.x (NOT 3.1.0). Uses `policyActions` with `templateKey`. Delegates to `GatewayAdminService`
- **Gotchas**: Trial expires (25-min cron). PUT needs full object. `consumingAPIs` via `POST /applications/{id}/apis`. Scope: `{Alias}:{Name}` format, audience must be `""`. Strategy body unwrapped. ES 8.13.4 required

## Apigee X (Google Cloud)

- **API**: `https://apigee.googleapis.com/v1/organizations/{org}`. Auth: Google Bearer token. HTTPS only
- Concept map: API→Proxy (versioned), Policy→Product (quota fields), App→Developer App (under `stoa-platform@gostoa.dev`)
- `_ensure_developer()` auto-creates. 409 on POST = success. Labels dict vs attributes array. No OIDC support
- **Gotchas**: Proxies versioned (POST = new revision). Singular keys: `apiProduct`, `app`. Attributes are `[{name,value}]` arrays. ~63 tests

## Azure APIM

- **API**: ARM REST at `management.azure.com`. Auth: Azure AD Bearer. Version: `2023-09-01-preview`
- Concept map: API→API (PUT idempotent), Policy→Product+XML, App→Subscription (scoped to Product)
- DELETE needs `If-Match: *`. Rate-limit via `<rate-limit>` XML. `api-version` auto-appended. No OIDC support
- Config: `subscription_id`, `resource_group`, `service_name`, `auth_config.bearer_token`. ~53 tests

---

## Adding a New Gateway Adapter

1. Copy `adapters/template/` → `adapters/{new_gw}/`. Implement 16 methods + mappers
2. Add enum in alembic migration. Register in `registry.py`. Add ~30+ tests
3. Contract: idempotent, `AdapterResult(success=False)` for unsupported, `httpx.AsyncClient`, never raise

## DB Registration

`gateway_type_enum`: webmethods, kong, apigee, aws_apigateway, azure_apim, gravitee, stoa, stoa_edge_mcp, stoa_sidecar, stoa_proxy, stoa_shadow
