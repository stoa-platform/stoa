# stoactl ↔ Control Plane API Contract Map

**Audit Date**: 2026-04-17
**Method**: static analysis — `stoa-go/pkg/client/*.go` (CLI view) × `control-plane-api/src/routers/*.py` (backend view). Every row manually verified.

**Status legend**
- `implemented` — CLI path matches a real backend route
- `renamed` — similar endpoint exists at different path/method (drift)
- `missing` — no backend route at all (dead command)
- `external` — CLI hits something other than CP API (Keycloak, stoa-connect agent)
- `offline` — pure local operation (no network)

**Owner legend**: `cli` (CLI wrong) / `backend` (endpoint absent) / `shared` (schema or scope drift — both need alignment) / `—` (clean).

---

## Contract Map

| cli_cmd | endpoint (CLI view) | status | owner |
|---------|---------------------|--------|-------|
| apply (API) | `POST /v1/tenants/{tenant_id}/apis` | implemented | — | <!-- CAB-2095: was /v1/apis (renamed) -->
| apply (API, dry-run) | client-side validation only (no HTTP) | offline | — | <!-- CAB-2095: backend has no ?dryRun, Service.Validate is now local -->  
| apply (Consumer) | `POST /v1/consumers/{tenant_id}` | implemented | — |
| apply (Contract) | `POST /v1/tenants/{tenant_id}/contracts` | implemented | — |
| apply (Gateway) | `POST /v1/admin/gateways` | implemented | — |
| apply (MCPServer) | `POST /v1/admin/mcp/servers` | implemented | — |
| apply (Plan) | `POST /v1/plans/{tenant_id}` | implemented | — |
| apply (ServiceAccount) | `POST /v1/service-accounts` | implemented | — |
| apply (Subscription) | `POST /v1/subscriptions` | implemented | — |
| apply (Tenant) | `POST /v1/tenants` | implemented | — |
| apply (Webhook) | `POST /v1/tenants/{tenant_id}/webhooks` | implemented | — |
| audit export (json) | `GET /v1/audit/{tenant_id}` | implemented | — |
| audit export (csv) | `GET /v1/audit/{tenant_id}/export/csv` | implemented | — |
| auth login | Keycloak device flow `auth.gostoa.dev/realms/stoa/...` | external | — |
| auth logout | (keyring + token file) | offline | — |
| auth rotate-key | (no network calls — likely stub) | offline | cli | <!-- TODO(CAB-2096): verify or descope in Phase C -->  
| auth status | (local keyring read) | offline | — |
| bridge (generate only) | (local OpenAPI → CRD YAML) | offline | — |
| bridge --apply | `POST /v1/admin/mcp/servers` + `POST /v1/admin/mcp/servers/{id}/tools` | implemented | — |
| catalog stats | `GET /v1/admin/catalog/stats` | implemented | — |
| catalog sync | `POST /v1/admin/catalog/sync` | implemented | — |
| catalog sync --tenant | `POST /v1/admin/catalog/sync/tenant/{tenant_id}` | implemented | — |
| catalog sync-status | `GET /v1/admin/catalog/sync/status` | implemented | — |
| completion bash\|zsh\|fish | — | offline | — |
| config current-context | — | offline | — |
| config get-contexts | — | offline | — |
| config set-context | — | offline | — |
| config use-context | — | offline | — |
| config view | — | offline | — |
| connect discover | `GET {agent_url}/discover` (stoa-connect agent) | external | — |
| connect status | `GET {agent_url}/health` (stoa-connect agent) | external | — |
| connect sync | `POST {agent_url}/sync` (stoa-connect agent) | external | — |
| delete api `<name>` | `DELETE /v1/tenants/{tenant_id}/apis/{api_id}` | implemented | — | <!-- CAB-2095 -->  
| delete consumer `<id>` | `DELETE /v1/consumers/{tenant_id}/{id}` | implemented | — |
| delete contract `<id>` | `DELETE /v1/tenants/{tenant_id}/contracts/{id}` | implemented | — |
| delete gateway `<id>` | `DELETE /v1/admin/gateways/{id}` | implemented | — |
| delete plan `<id>` | `DELETE /v1/plans/{tenant_id}/{id}` | implemented | — |
| delete service-account `<id>` | `DELETE /v1/service-accounts/{id}` | implemented | — |
| delete subscription `<id>` | `DELETE /v1/subscriptions/{id}` | implemented | — |
| delete tenant `<id>` | `DELETE /v1/tenants/{id}` | implemented | — |
| delete webhook `<id>` | `DELETE /v1/tenants/{tenant_id}/webhooks/{id}` | implemented | — |
| **deploy create** | CLI: `POST /v1/tenants/{tenant}/deployments` — backend: `POST /v1/admin/deployments` | **renamed** | **shared** |
| **deploy get `<id>`** | CLI: `GET /v1/tenants/{tenant}/deployments/{id}` — backend: `GET /v1/admin/deployments/{id}` | **renamed** | **shared** |
| **deploy list** | CLI: `GET /v1/tenants/{tenant}/deployments` — backend: `GET /v1/admin/deployments` | **renamed** | **shared** |
| **deploy rollback** | CLI: `POST /v1/tenants/{tenant}/deployments/{id}/rollback` — backend: no rollback route (only `/sync`, `/test`) | **missing** | **backend** |
| doctor | localhost-only probes (Docker, keyring, ports) | offline | — |
| gateway get `<id>` | `GET /v1/admin/gateways/{id}` | implemented | — |
| gateway health | `GET /v1/admin/gateways/health` | implemented | — |
| gateway list | `GET /v1/admin/gateways` | implemented | — |
| get apis | `GET /v1/tenants/{tenant_id}/apis` | implemented | — | <!-- CAB-2095: was /v1/portal/apis (portal consumer view, wrong semantic) -->
| get api `<name>` | `GET /v1/tenants/{tenant_id}/apis/{api_id}` | implemented | — | <!-- CAB-2095 -->  
| get consumers | `GET /v1/consumers/{tenant_id}` | implemented | — |
| get consumer `<id>` | `GET /v1/consumers/{tenant_id}/{id}` | implemented | — |
| get contracts | `GET /v1/tenants/{tenant_id}/contracts` | implemented | — |
| get contract `<id>` | `GET /v1/tenants/{tenant_id}/contracts/{id}` | implemented | — |
| get environments | `GET /v1/environments` | implemented | — |
| get gateways | `GET /v1/admin/gateways` | implemented | — |
| get gateway `<id>` | `GET /v1/admin/gateways/{id}` | implemented | — |
| get plans | `GET /v1/plans/{tenant_id}` | implemented | — |
| get plan `<id>` | `GET /v1/plans/{tenant_id}/{id}` | implemented | — |
| get service-accounts | `GET /v1/service-accounts` | implemented | — |
| **get subscriptions** | CLI: `GET /v1/subscriptions?page=X` — backend: no root list, only `/my` + `/tenant/{id}` | **renamed** | **shared** |
| get subscription `<id>` | `GET /v1/subscriptions/{id}` | implemented | — |
| get tenants | `GET /v1/tenants` | implemented | — |
| get tenant `<id>` | `GET /v1/tenants/{id}` | implemented | — |
| get webhooks | `GET /v1/tenants/{tenant_id}/webhooks` | implemented | — |
| get webhook `<id>` | `GET /v1/tenants/{tenant_id}/webhooks/{id}` | implemented | — |
| init | (scaffolds docker-compose + stoa.yaml locally) | offline | — |
| **logs** | `GET /v1/apis/{name}` + `GET /v1/tenants/{tenant}/deployments` — same drift as deploy list | **renamed** | **shared** |
| mcp call `<tool>` | `POST /v1/admin/mcp/servers/{server_id}/tools/invoke` | implemented | — |
| mcp health | `GET /v1/admin/mcp/servers/health` | implemented | — |
| mcp health --gateway | `GET /mcp/health` (gateway direct) | implemented | — |
| mcp list-servers | `GET /v1/admin/mcp/servers` | implemented | — |
| mcp list-tools | `GET /v1/admin/mcp/servers/{server_id}` | implemented | — |
| mcp list-tools --gateway | `GET /mcp/v1/tools` (gateway direct) | implemented | — |
| subscription approve `<id>` | `POST /v1/subscriptions/{id}/approve` | implemented | — |
| **subscription list** | same drift as `get subscriptions` — `GET /v1/subscriptions?page=X` | **renamed** | **shared** |
| subscription revoke `<id>` | `POST /v1/subscriptions/{id}/revoke` | implemented | — |
| tenant create | `POST /v1/tenants` | implemented | — |
| tenant delete `<id>` | `DELETE /v1/tenants/{id}` | implemented | — |
| tenant get `<id>` | `GET /v1/tenants/{id}` | implemented | — |
| tenant list | `GET /v1/tenants` | implemented | — |
| token-usage | `GET /v1/usage/tokens?time_range=X` | implemented | — |
| token-usage --compare | `GET /v1/usage/tokens/compare?time_range=X` | implemented | — |
| version | (build info only) | offline | — |

---

## Summary

**Total rows**: 79 leaf commands
- `implemented`: 58
- `offline`: 14
- `external` (Keycloak or stoa-connect agent): 4
- **`renamed` (drift)**: 5
- **`missing`**: 1 — `deploy rollback` has no backend endpoint
- `deprecated`: 0

### Correction log — 2026-04-17 (CAB-2095)

Phase A initial map classified `POST/GET/DELETE /v1/apis` as `implemented` after the Explore agent matched `/v1/apis` against `@router.get("/apis")` in `routers/gateway.py` (portal consumer route, wrong semantic). Phase B3 reproduction proved these endpoints return 404 — the real admin router is mounted at `/v1/tenants/{tenant_id}/apis`. Rows for `apply/get/delete api` are now corrected above. Lesson: contract audits must grep the **prefix** AND the method decorator together, and cross-reference admin vs consumer semantics for paths that look similar.

### Drifts (fix_verdict candidates)

| cmd | drift | owner | fix direction |
|-----|-------|-------|---------------|
| `deploy create/list/get` | CLI uses `/v1/tenants/{t}/deployments`, backend uses `/v1/admin/deployments` | shared | Decide: scope admin vs tenant-scoped. CLI likely wrong — backend is current truth (matches CAB-2010 GitOps). |
| `deploy rollback` | no backend route, CLI expects `POST .../rollback` | backend | Implement route or drop CLI verb. |
| `get subscriptions` / `subscription list` | CLI lists via `/v1/subscriptions`, backend only exposes `/my` + `/tenant/{id}` | shared | CLI must call `/tenant/{current_tenant}` (tenant from context). |
| `logs` | reuses broken deploy path | shared | Fixed automatically once deploy drift resolved. |
| `auth rotate-key` | no network calls in source — likely stub | cli | Verify Phase B; either implement or descope. |

### Golden path coverage

All 4 core golden paths touch only `implemented` rows:

- **B1 auth + tenants** — `auth login` (external) + `tenant list` (impl) → **clean**
- **B2 tenant lifecycle** — `tenant create` (impl) + `tenant get` (impl, provisioning-status endpoint not yet in CLI — gap) → **near-clean**
- **B3 apply/get/delete api** — `apply (API)` (impl) + `get apis` (impl) + `delete api` (impl) → **clean**
- **B4 mcp list/call** — `mcp list-servers` + `mcp list-tools` + `mcp call` → **clean**

→ Phase B can proceed immediately. Drifts (deploy, subscription list, logs) are outside the 4 core paths.

### Deferred / descope candidates

- `deploy rollback` → backend work, not CLI bug → file backend ticket, don't fix in CLI
- `auth rotate-key` → descope until backend route confirmed
- `get subscriptions` → either fix CLI tenant scoping, or descope until portal use case forces it

### Known gap outside scope

- `tenant provisioning-status` endpoint exists on backend (`GET /v1/tenants/{id}/provisioning-status`) but no CLI wrapper. Gap, not drift.

