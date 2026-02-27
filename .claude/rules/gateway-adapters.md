---
globs:
  - "control-plane-api/src/adapters/**"
  - "control-plane-api/tests/test_*_adapter*"
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
| Aliases | `upsert_alias` | Optional | webMethods only |
| Config | `apply_config` | Optional | webMethods only |
| Backup | `export_archive` | Optional | webMethods only |

## Key Files

| File | Purpose |
|------|---------|
| `control-plane-api/src/adapters/gateway_adapter_interface.py` | Abstract interface + `AdapterResult` |
| `control-plane-api/src/adapters/registry.py` | Factory: `gateway_type` → adapter class |
| `control-plane-api/src/adapters/{gw}/adapter.py` | Adapter implementation |
| `control-plane-api/src/adapters/{gw}/mappers.py` | Spec translation functions |
| `control-plane-api/tests/test_{gw}_adapter.py` | Unit tests (mock httpx) |

---

## STOA Gateway (Rust)

See `stoa-gateway/src/handlers/admin.rs` for the Rust admin API contract. The Python adapter (`StoaGatewayAdapter`) wraps the admin endpoints.

---

## Kong (DB-less)

### Quick Reference
- **Admin API**: `GET /services`, `GET /plugins`, `GET /consumers`, `POST /config`
- **Auth**: `Kong-Admin-Token` header (optional)
- **Storage**: Declarative YAML via `POST /config` (atomic reload)
- **Ports**: 8000 (proxy), 8001 (admin)
- **VPS**: `51.83.45.13` (kong-standalone-gra)

### State Management Pattern
Kong DB-less mode makes Admin API **read-only** for writes. All mutations follow:
1. `GET /services` + `GET /plugins` + `GET /consumers` → read current state
2. Merge desired change into state (upsert by name/tag)
3. `POST /config` with full `_format_version: "3.0"` payload → atomic reload

### Tips
- **Always use `_format_version: "3.0"`** in config payload
- Services include nested `routes` in declarative config (not separate entities)
- Plugins reference services by **name** (not ID) in declarative config
- Use `stoa-policy-{id}` tags to identify STOA-managed plugins
- Use `stoa-consumer-{subscription_id}` tags for STOA-managed consumers
- Consumer key-auth credentials go in `keyauth_credentials` array
- Consumer-scoped rate-limiting goes in `plugins` array on the consumer object

### Gotchas (live-tested on VPS)
- **`tags: null`** — Kong returns `null` for tags, not `[]`. Always use `get("tags") or []`, never `get("tags", [])`
- **`path: null`** — Services with no path return `null`. URL reconstruction: `svc.get('path') or ''`
- **Port in URL**: `port` field is an integer, must be part of the reconstructed URL string
- **Plugin service reference**: Admin API returns `service: {id: "..."}` (dict), not `service: "name"`. Must resolve ID to name.
- **Config reload is all-or-nothing**: if one service is invalid, the entire reload fails
- **Rate-limiting plugin config**: `minute`, `second`, `hour`, `day` keys (not `maxRequests`)

### Mappers
| Function | Direction | Notes |
|----------|-----------|-------|
| `map_api_spec_to_kong_service` | CP → Kong | Returns service + routes |
| `map_kong_service_to_cp` | Kong → CP | From GET /services response |
| `map_policy_to_kong_plugin` | CP → Kong | rate_limit → rate-limiting, cors → cors |
| `map_kong_plugin_to_policy` | Kong → CP | Reverse mapping |
| `map_app_spec_to_kong_consumer` | CP → Kong | Consumer + keyauth + optional rate-limit |
| `map_kong_consumer_to_cp` | Kong → CP | Extract subscription_id from tags |

### Testing
```bash
cd control-plane-api && pytest tests/test_kong_adapter.py -v  # ~38 tests
```

---

## Gravitee (APIM v4)

### Quick Reference
- **Mgmt API**: `http://host:8083/management/v2/environments/DEFAULT/apis`
- **Auth**: Basic `admin:admin` (default)
- **Storage**: MongoDB + Elasticsearch (full CRUD)
- **Ports**: 8082 (gateway), 8083 (mgmt API), 8084 (mgmt UI)
- **VPS**: `54.36.209.237` (gravitee-standalone-gra)

### API Lifecycle
Gravitee APIs have a lifecycle: `CREATED → PUBLISHED → STARTED → DEPLOYED`
```
1. POST /apis (create)
2. POST /apis/{id}/_start (start — may fail on V4 APIs, non-blocking)
3. POST /apis/{id}/deployments (deploy)
```

### Tips
- **V4 APIs**: Use `definitionVersion: "V4"` with `type: "PROXY"` and `listeners/endpointGroups`
- **Plans**: Rate-limiting is done via Plans with flows (not standalone policies)
- **Applications**: CRUD at `/applications`, subscriptions link apps to plans
- **KEY_LESS plans**: Cannot have subscriptions (non-blocking warning)
- Use STOA naming convention: `stoa-rate-limit-{policy_id}` for plan names
- When searching APIs by name: `GET /apis?q={name}`

### Gotchas (live-tested on VPS)
- **Plan tags MUST match API tags** — Plans can't have tags that don't exist on the API. Use name-based identification instead of tags.
- **V4 Plan required fields**: `definitionVersion: "V4"`, `mode: "STANDARD"`, `characteristics: []` — missing any causes 400
- **`_start` returns 400 on V4 APIs** that aren't fully configured — non-blocking, API still works
- **Subscription on KEY_LESS plan**: returns 400 "not subscribable" — log warning, don't fail
- **Basic auth header**: `Authorization: Basic YWRtaW46YWRtaW4=` (admin:admin base64)
- **Management API v2 path**: `/management/v2/environments/DEFAULT/apis` (not `/management/organizations/DEFAULT/environments/DEFAULT/apis`)
- **Health check endpoint**: `GET /management/organizations/DEFAULT/environments/DEFAULT` (v1 path, not v2)

### Mappers
| Function | Direction | Notes |
|----------|-----------|-------|
| `map_api_spec_to_gravitee_v4` | CP → Gravitee | V4 API with listeners + endpoints |
| `map_gravitee_api_to_cp` | Gravitee → CP | Normalize to CP format |
| `map_policy_to_gravitee_plan` | CP → Gravitee | rate_limit → Plan with rate-limit flow |
| `map_gravitee_plan_to_policy` | Gravitee → CP | Extract STOA ID from plan name |
| `map_app_spec_to_gravitee_app` | CP → Gravitee | Application object |
| `map_gravitee_app_to_cp` | Gravitee → CP | Normalize to CP format |

### Testing
```bash
cd control-plane-api && pytest tests/test_gravitee_adapter.py -v  # ~35 tests
```

---

## webMethods (IBM/Software AG)

### Quick Reference
- **Admin API**: `http://host:5555/rest/apigateway/*`
- **Auth**: Basic `Administrator:manage`
- **Storage**: Elasticsearch (internal)
- **Ports**: 5555 (HTTP runtime + admin), 5543 (HTTPS runtime), 9072 (admin UI)
- **Docker**: `softwareag/apigateway-trial:10.15` (2.6 GB, needs ES + 25-min cron for trial)

### Full Feature Set
webMethods is the most feature-complete adapter — supports all 16 interface methods including OIDC, aliases, config, and backup.

### Tips
- **API import**: via file upload (`multipart/form-data`) or URL. Only OpenAPI 3.0.x (NOT 3.1.0)
- **Routing**: Uses endpoint aliases (`${AliasName}/${sys:resource_path}`) in policy actions
- **OIDC**: Full 8-step Keycloak integration (auth server → strategy → app → scope → IAM policy)
- **Policies**: webMethods uses `policyActions` with `templateKey` identifiers
- **Transport**: APIs default to HTTP only (port 5555). Must enable HTTPS via transport policy
- **Applications**: Create app → associate strategy → associate APIs → create scope mappings
- **Backup**: `GET /archive?include=api,application,alias,policy` returns ZIP

### Gotchas
- **Trial license expires**: needs cron job every 25 minutes to restart/refresh
- **OpenAPI 3.1.0 not supported**: must convert to 3.0.3 before import (`sed 's/3.1.0/3.0.3/'`)
- **PUT on API requires full object**: GET current → modify → PUT entire object back
- **`consumingAPIs` not modifiable via PUT**: use `POST /applications/{id}/apis` instead
- **Scope naming**: must be `{AuthServerAlias}:{ScopeName}` format (e.g. `KeycloakOIDC:openid`)
- **Scope audience must be empty string `""`** — setting a custom value breaks validation
- **Strategy body**: must NOT be wrapped in `strategy` object (send properties directly)
- **ES dependency**: needs Elasticsearch running alongside (8.13.4 recommended)
- **Adapter delegates to `GatewayAdminService`**: for HTTP calls — different pattern from Kong/Gravitee which use httpx directly

### Testing
```bash
cd control-plane-api && pytest tests/test_webmethods_adapter.py -v
```

### Docker Compose (local dev)
```bash
cd deploy/docker-compose && docker compose -f docker-compose.webmethods.yml up -d
# Health: curl -u Administrator:manage http://localhost:5555/rest/apigateway/health
```

---

## Apigee X (Google Cloud)

### Quick Reference
- **API**: Apigee Management API v1 at `https://apigee.googleapis.com/v1/organizations/{org}`
- **Auth**: Google Cloud Bearer token (OAuth2 or service account)
- **Storage**: Apigee X managed (versioned API proxies, API products, developer apps)
- **Ports**: HTTPS only (cloud-managed)

### Concept Mapping

| STOA Concept | Apigee Concept | Notes |
|-------------|---------------|-------|
| API | API Proxy | POST create, versioned revisions |
| Policy (rate-limit) | API Product | Product-level quota fields (`quota`, `quotaInterval`, `quotaTimeUnit`) |
| Application | Developer App | Under STOA-managed developer (`stoa-platform@gostoa.dev`) |

### Tips
- **STOA-managed developer**: All apps are created under a single developer (`stoa-platform@gostoa.dev`), auto-created by `_ensure_developer()` if missing
- **Idempotent developer creation**: 409 (Conflict) on developer POST is treated as success (race condition guard)
- **Product-level quota**: Rate limiting uses Apigee product `quota`, `quotaInterval`, `quotaTimeUnit` fields (not policies)
- **STOA naming convention**: Resources prefixed with `stoa-{tenant}-*` or have `stoa-managed: true` attribute
- **Labels for filtering**: API proxies use `labels` dict, products/apps use `attributes` array
- **`_get_client()` pattern**: Returns `(client, should_close_after)` for ephemeral client support
- **No OIDC/alias/config/archive support** — returns `AdapterResult(success=False, error="Not supported")`

### Config Keys

```python
{
    "organization": "...",          # Apigee organization name
    "auth_config": {
        "bearer_token": "..."       # Google Cloud bearer token
    },
    "base_url": "https://apigee.googleapis.com"  # Override for private Apigee
}
```

### Mappers
| Function | Direction | Notes |
|----------|-----------|-------|
| `map_api_spec_to_apigee_proxy` | CP → Apigee | Returns proxy with labels |
| `map_apigee_proxy_to_cp` | Apigee → CP | Normalize to CP format |
| `map_policy_to_apigee_product` | CP → Apigee | Product with quota fields |
| `map_apigee_product_to_policy` | Apigee → CP | Extract policy ID from attributes |
| `map_app_spec_to_apigee_developer_app` | CP → Apigee | Developer App with API product bindings |
| `map_apigee_developer_app_to_cp` | Apigee → CP | Extract app ID, API key from credentials |

### Gotchas
- **Developer must exist before creating apps**: `_ensure_developer()` handles this automatically
- **Proxies are versioned**: each POST to `/apis` creates a new revision (not update in-place)
- **`apiProduct` (singular key)**: `GET /apiproducts` returns `{"apiProduct": [...]}` (not `apiProducts`)
- **`app` (singular key)**: `GET /developers/{email}/apps?expand=true` returns `{"app": [...]}` (not `apps`)
- **Attributes are arrays**: `[{"name": "k", "value": "v"}]` not dicts — must transform for lookups

### Testing
```bash
cd control-plane-api && pytest tests/test_apigee_adapter.py -v  # ~63 tests
```

---

## Azure APIM

### Quick Reference
- **API**: Azure ARM REST API at `https://management.azure.com`
- **Auth**: Bearer token (Azure AD / Entra ID OAuth2 client credentials)
- **API Version**: `2023-09-01-preview` (appended as `?api-version=` on all requests)
- **Resource Path**: `/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.ApiManagement/service/{name}`

### Concept Mapping

| STOA Concept | Azure APIM Concept | Notes |
|-------------|-------------------|-------|
| API | API | PUT idempotent create-or-update |
| Policy (rate-limit) | Product + XML Policy | Product scoped, policy applied via `/policies/policy` |
| Application | Subscription | Subscription scoped to a Product |

### Tips
- **PUT is idempotent** — both create and update use PUT (unlike AWS POST+PATCH)
- **DELETE requires `If-Match: *`** — all three delete methods must include this header
- **STOA naming convention**: resources prefixed with `stoa-{tenant}-*` for filtering
- **Rate-limit via XML policy**: Applied at Product scope, uses `<rate-limit>` XML element
- **Subscription scope binding**: `properties.scope` points to Product ARM path
- **api-version param**: Appended to every request automatically by `_request` helper
- No OIDC/alias/config/archive support — returns `AdapterResult(success=False, error="Not supported")`

### Config Keys

```python
{
    "subscription_id": "...",       # Azure subscription ID
    "resource_group": "...",        # Resource group name
    "service_name": "...",          # APIM service instance name
    "auth_config": {
        "bearer_token": "..."       # Azure AD bearer token
    },
    "base_url": "https://management.azure.com"  # Override for sovereign clouds
}
```

### Mappers
| Function | Direction | Notes |
|----------|-----------|-------|
| `map_api_spec_to_azure` | CP → Azure | Returns API PUT payload with `_stoa_api_id` |
| `map_azure_api_to_cp` | Azure → CP | Normalize to CP format |
| `map_policy_to_azure_product` | CP → Azure | Product + `_stoa_rate_limit` metadata |
| `map_azure_product_to_policy` | Azure → CP | Extract policy ID from `stoa-{id}` naming |
| `map_app_spec_to_azure_subscription` | CP → Azure | Subscription with display name |
| `map_azure_subscription_to_cp` | Azure → CP | Extract subscription ID from naming |
| `build_rate_limit_policy_xml` | — | XML string for `<rate-limit>` element |

### Testing
```bash
cd control-plane-api && pytest tests/test_azure_apim_adapter.py -v  # ~53 tests
```

---

## Adding a New Gateway Adapter

1. Copy `control-plane-api/src/adapters/template/` to `adapters/{new_gw}/`
2. Implement all 16 abstract methods in `adapter.py`
3. Create mappers in `mappers.py` (CP spec ↔ gateway-native format)
4. Add enum value in `alembic/versions/` migration
5. Register in `adapters/registry.py`
6. Add tests in `tests/test_{new_gw}_adapter.py` (~30+ tests)
7. Update this rule file with gateway-specific tips and gotchas

### Adapter Contract Rules
- All methods MUST be **idempotent** (calling twice = same result)
- Return `AdapterResult(success=False, error="Not supported by X")` for unsupported methods
- Use `httpx.AsyncClient` for HTTP calls (async, connection pooling)
- Log warnings for non-critical failures (e.g., plan not subscribable)
- Never raise exceptions — catch and return `AdapterResult(success=False, error=str(e))`

## Live Validation

Test adapter against live gateway:
```python
# /tmp/validate-adapters-live.py pattern:
# 1. health_check
# 2. sync_api (create test API)
# 3. list_apis (verify)
# 4. upsert_policy (rate-limit)
# 5. list_policies (verify)
# 6. provision_application
# 7. list_applications (verify)
# 8. deprovision_application
# 9. delete_policy
# 10. delete_api (cleanup)
```

## DB Registration

Gateway instances are stored in `gateway_instances` table:
```sql
-- gateway_type_enum: webmethods, kong, apigee, aws_apigateway, azure_apim,
--   gravitee, stoa, stoa_edge_mcp, stoa_sidecar, stoa_proxy, stoa_shadow
INSERT INTO gateway_instances (name, display_name, gateway_type, base_url, status, ...)
VALUES ('kong-standalone-gra', 'Kong DB-less (GRA)', 'kong', 'https://kong.gostoa.dev', 'online', ...);
```
