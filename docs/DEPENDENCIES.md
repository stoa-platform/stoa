<!-- AUTO-GENERATED from stoa-impact.db — DO NOT EDIT MANUALLY -->
<!-- Regenerate: python3 docs/scripts/regenerate-docs.py -->
<!-- Last generated: 2026-03-26 20:35 -->

# STOA Platform — Dependency Map

> **13** active components | **83** contracts (28 typed, **55 untyped**) | **6** open risks (1 CRITICAL)

## Components

### stoactl CLI (`stoactl`)
- **Type**: cli | **Stack**: Go 1.22, Cobra, go-keyring | **Path**: `stoa-go/cmd/stoactl/`
- CLI — Device Authorization flow, 20+ commands, OS keyring token storage
- **Outgoing** (3 contracts):
  - `cli-cp-001` → `control-plane-api` (rest-api): `GET /v1/tenants/{tid}/apis + CRUD` **UNTYPED**
  - `cli-cp-002` → `control-plane-api` (rest-api): `GET /health` **UNTYPED**
  - `cli-kc-001` → `keycloak` (oidc-flow): `Device Authorization Grant (stoactl client)`

### HashiCorp Vault (`vault`)
- **Type**: external | **Stack**: Vault KV v2 | **Path**: N/A
- Secrets: API keys, certs, consumer credentials. AppRole auth
- **Incoming** (2 contracts):
  - `cp-vault-001` ← `control-plane-api` (rest-api): `Vault KV v2 (hvac)` **UNTYPED**
  - `conn-vault-001` ← `stoa-connect` (rest-api): `Vault KV v2 stoa/data/consumers/{tid}` **UNTYPED**

### Kafka / Redpanda (`kafka`)
- **Type**: external | **Stack**: Redpanda | **Path**: N/A
- 25+ topics, no schema registry — CRITICAL gap
- **Incoming** (14 contracts):
  - `cp-kf-001` ← `control-plane-api` (kafka-event): `stoa.api.lifecycle` **UNTYPED**
  - `cp-kf-002` ← `control-plane-api` (kafka-event): `stoa.deployment.events` **UNTYPED**
  - `cp-kf-003` ← `control-plane-api` (kafka-event): `stoa.tenant.lifecycle` **UNTYPED**
  - `cp-kf-004` ← `control-plane-api` (kafka-event): `stoa.audit.trail` **UNTYPED**
  - `cp-kf-005` ← `control-plane-api` (kafka-event): `stoa.policy.changes` **UNTYPED**
  - `cp-kf-006` ← `control-plane-api` (kafka-event): `stoa.catalog.changes` **UNTYPED**
  - `cp-kf-007` ← `control-plane-api` (kafka-event): `stoa.app.lifecycle` **UNTYPED**
  - `cp-kf-008` ← `control-plane-api` (kafka-event): `stoa.security.alerts` **UNTYPED**
  - `cp-kf-009` ← `control-plane-api` (kafka-event): `stoa.errors` **UNTYPED**
  - `cp-kf-010` ← `control-plane-api` (kafka-event): `stoa.deploy.requests` **UNTYPED**
  - `gw-kf-001` ← `stoa-gateway` (kafka-event): `stoa.metering.events` **UNTYPED**
  - `gw-kf-002` ← `stoa-gateway` (kafka-event): `stoa.errors` **UNTYPED**
  - `gw-kf-003` ← `stoa-gateway` (kafka-event): `stoa.security.alerts` **UNTYPED**
  - `gw-kf-004` ← `stoa-gateway` (kafka-event): `stoa.gateway.metrics` **UNTYPED**

### Keycloak IAM (`keycloak`)
- **Type**: external | **Stack**: Keycloak 26.5.3, custom STOA theme | **Path**: `keycloak/`
- OIDC/OAuth2 — token-exchange, DPoP, PAR. Realm: stoa. 8 clients configured
- **Incoming** (8 contracts):
  - `cs-kc-001` ← `console` (oidc-flow): `OIDC Authorization Code + PKCE (control-plane-ui client)`
  - `cp-kc-001` ← `control-plane-api` (admin-api): `Keycloak Admin REST API (python-keycloak)` **UNTYPED**
  - `cp-kc-002` ← `control-plane-api` (oidc-flow): `OIDC JWT validation (RS256, JWKS)`
  - `pt-kc-001` ← `portal` (oidc-flow): `OIDC Authorization Code + PKCE (stoa-portal client)`
  - `gw-kc-001` ← `stoa-gateway` (oidc-flow): `OIDC JWT validation (JWKS fetch)`
  - `gw-kc-002` ← `stoa-gateway` (admin-api): `POST /oauth/register proxy → KC DCR + PKCE patch` **UNTYPED**
  - `gw-kc-003` ← `stoa-gateway` (oidc-flow): `POST /oauth/token proxy → KC token endpoint`
  - `cli-kc-001` ← `stoactl` (oidc-flow): `Device Authorization Grant (stoactl client)`

### OpenSearch (`opensearch`)
- **Type**: external | **Stack**: OpenSearch | **Path**: N/A
- Audit logs, full-text search, traces — OPTIONAL dependency
- **Incoming** (1 contracts):
  - `cp-os-001` ← `control-plane-api` (rest-api): `OpenSearch indexing (stoa-audit-*, stoa-errors-*, stoa-traces-*)` **UNTYPED**

### PostgreSQL (`postgresql`)
- **Type**: external | **Stack**: PostgreSQL 14+ (asyncpg) | **Path**: N/A
- 65 tables, Alembic migrations, asyncpg pool (2-20)
- **Incoming** (2 contracts):
  - `cp-pg-001` ← `control-plane-api` (db-write): `SQLAlchemy ORM (65 tables)`
  - `cp-pg-002` ← `control-plane-api` (db-read): `SQLAlchemy ORM queries`

### STOA Admin Console (`console`)
- **Type**: frontend | **Stack**: React 18, TypeScript, Vite, TanStack Query | **Path**: `control-plane-ui/`
- Admin SPA — 200+ API calls, ~150 endpoints consumed
- **Outgoing** (17 contracts):
  - `cs-cp-001` → `control-plane-api` (rest-api): `CRUD /v1/tenants` **UNTYPED**
  - `cs-cp-002` → `control-plane-api` (rest-api): `CRUD /v1/tenants/{t}/apis` **UNTYPED**
  - `cs-cp-003` → `control-plane-api` (rest-api): `CRUD /v1/consumers/{t}` **UNTYPED**
  - `cs-cp-004` → `control-plane-api` (rest-api): `CRUD /v1/subscriptions` **UNTYPED**
  - `cs-cp-005` → `control-plane-api` (rest-api): `CRUD /v1/tenants/{t}/deployments` **UNTYPED**
  - `cs-cp-006` → `control-plane-api` (rest-api): `CRUD /v1/tenants/{t}/promotions` **UNTYPED**
  - `cs-cp-007` → `control-plane-api` (rest-api): `CRUD /v1/admin/gateways` **UNTYPED**
  - `cs-cp-008` → `control-plane-api` (rest-api): `CRUD /v1/admin/policies` **UNTYPED**
  - `cs-cp-009` → `control-plane-api` (rest-api): `CRUD /v1/admin/external-mcp-servers` **UNTYPED**
  - `cs-cp-010` → `control-plane-api` (rest-api): `CRUD /v1/tenants/{t}/contracts` **UNTYPED**
  - `cs-cp-011` → `control-plane-api` (rest-api): `CRUD /v1/tenants/{t}/federation/accounts` **UNTYPED**
  - `cs-cp-012` → `control-plane-api` (rest-api): `GET /v1/platform/status` **UNTYPED**
  - `cs-cp-013` → `control-plane-api` (rest-api): `GET /v1/traces` **UNTYPED**
  - `cs-cp-014` → `control-plane-api` (rest-api): `GET /v1/business/metrics` **UNTYPED**
  - `cs-cp-015` → `control-plane-api` (sse): `EventSource /v1/events/stream/{tid}` **UNTYPED**
  - `cs-kc-001` → `keycloak` (oidc-flow): `OIDC Authorization Code + PKCE (control-plane-ui client)`
  - `cs-prom-001` → `prometheus` (metrics): `/prometheus/api/v1/query (same-origin proxy)` **UNTYPED**
- **Scenarios**: SCEN-003 (P0, unit), SCEN-001 (P0, none), SCEN-004 (P1, none), SCEN-006 (P1, none)

### STOA Developer Portal (`portal`)
- **Type**: frontend | **Stack**: React 19, TypeScript, Vite 7, TanStack Query v5 | **Path**: `portal/`
- Developer self-service — 100+ API calls, dual client (apiClient + mcpClient)
- **Outgoing** (15 contracts):
  - `pt-cp-001` → `control-plane-api` (rest-api): `GET /v1/portal/apis (catalog)` **UNTYPED**
  - `pt-cp-002` → `control-plane-api` (rest-api): `CRUD /v1/subscriptions` **UNTYPED**
  - `pt-cp-003` → `control-plane-api` (rest-api): `CRUD /v1/mcp/servers + /v1/mcp/subscriptions` **UNTYPED**
  - `pt-cp-004` → `control-plane-api` (rest-api): `CRUD /v1/applications` **UNTYPED**
  - `pt-cp-005` → `control-plane-api` (rest-api): `CRUD /v1/consumers/{tenant_id}` **UNTYPED**
  - `pt-cp-006` → `control-plane-api` (rest-api): `GET /v1/usage/me + /v1/dashboard/stats` **UNTYPED**
  - `pt-cp-007` → `control-plane-api` (rest-api): `POST /v1/self-service/tenants` **UNTYPED**
  - `pt-cp-008` → `control-plane-api` (rest-api): `CRUD /v1/contracts` **UNTYPED**
  - `pt-cp-009` → `control-plane-api` (rest-api): `CRUD /v1/tenants/{tid}/mcp-servers` **UNTYPED**
  - `pt-cp-010` → `control-plane-api` (rest-api): `CRUD /tenants/{tid}/webhooks` **UNTYPED**
  - `pt-cp-011` → `control-plane-api` (rest-api): `GET /v1/me + POST /v1/me/tenant` **UNTYPED**
  - `pt-kc-001` → `keycloak` (oidc-flow): `OIDC Authorization Code + PKCE (stoa-portal client)`
  - `pt-gw-001` → `stoa-gateway` (rest-api): `GET /mcp/v1/tools`
  - `pt-gw-002` → `stoa-gateway` (rest-api): `POST /mcp/v1/tools/{name}/invoke`
  - `pt-gw-003` → `stoa-gateway` (rest-api): `CRUD /mcp/v1/subscriptions`
- **Scenarios**: SCEN-001 (P0, none)

### MCP Gateway (Python) (`mcp-gateway-legacy`) **[ARCHIVED]**
- **Type**: gateway | **Stack**: Python 3.11, FastAPI | **Path**: `archive/mcp-gateway/`
- ARCHIVED Feb 2026 — replaced by stoa-gateway Rust

### STOA MCP Gateway (`stoa-gateway`)
- **Type**: gateway | **Stack**: Rust 2021, Tokio, axum 0.7, 170 source files | **Path**: `stoa-gateway/`
- Production gateway — 4 modes: edge-mcp, sidecar, proxy, shadow. 100+ endpoints
- **Outgoing** (16 contracts):
  - `gw-cp-001` → `control-plane-api` (rest-api): `POST /v1/gateway/internal/register`
  - `gw-cp-002` → `control-plane-api` (rest-api): `POST /v1/gateway/internal/heartbeat`
  - `gw-cp-003` → `control-plane-api` (rest-api): `GET /v1/mcp/validate`
  - `gw-kf-001` → `kafka` (kafka-event): `stoa.metering.events` **UNTYPED**
  - `gw-kf-002` → `kafka` (kafka-event): `stoa.errors` **UNTYPED**
  - `gw-kf-003` → `kafka` (kafka-event): `stoa.security.alerts` **UNTYPED**
  - `gw-kf-004` → `kafka` (kafka-event): `stoa.gateway.metrics` **UNTYPED**
  - `gw-kc-001` → `keycloak` (oidc-flow): `OIDC JWT validation (JWKS fetch)`
  - `gw-kc-002` → `keycloak` (admin-api): `POST /oauth/register proxy → KC DCR + PKCE patch` **UNTYPED**
  - `gw-kc-003` → `keycloak` (oidc-flow): `POST /oauth/token proxy → KC token endpoint`
  - `gw-prom-001` → `prometheus` (metrics): `GET /metrics (60+ metrics)`
  - `gw-mcp-001` → `stoa-gateway` (rest-api): `GET /mcp/capabilities (RFC 9728)`
  - `gw-mcp-002` → `stoa-gateway` (rest-api): `POST /mcp/tools/list + /mcp/tools/call (JSON-RPC 2.0)`
  - `gw-oauth-001` → `stoa-gateway` (rest-api): `/.well-known/oauth-protected-resource (RFC 9728)`
  - `gw-oauth-002` → `stoa-gateway` (rest-api): `/.well-known/oauth-authorization-server (RFC 8414)`
  - `gw-admin-001` → `stoa-gateway` (admin-api): `/admin/* (70+ endpoints)`
- **Incoming** (9 contracts):
  - `cp-gw-001` ← `control-plane-api` (admin-api): `StoaGatewayAdapter → /admin/*`
  - `pt-gw-001` ← `portal` (rest-api): `GET /mcp/v1/tools`
  - `pt-gw-002` ← `portal` (rest-api): `POST /mcp/v1/tools/{name}/invoke`
  - `pt-gw-003` ← `portal` (rest-api): `CRUD /mcp/v1/subscriptions`
  - `gw-mcp-001` ← `stoa-gateway` (rest-api): `GET /mcp/capabilities (RFC 9728)`
  - `gw-mcp-002` ← `stoa-gateway` (rest-api): `POST /mcp/tools/list + /mcp/tools/call (JSON-RPC 2.0)`
  - `gw-oauth-001` ← `stoa-gateway` (rest-api): `/.well-known/oauth-protected-resource (RFC 9728)`
  - `gw-oauth-002` ← `stoa-gateway` (rest-api): `/.well-known/oauth-authorization-server (RFC 8414)`
  - `gw-admin-001` ← `stoa-gateway` (admin-api): `/admin/* (70+ endpoints)`
- **Scenarios**: SCEN-002 (P0, integration), SCEN-006 (P1, none), SCEN-005 (P1, unit)

### ArgoCD (`argocd`)
- **Type**: infra | **Stack**: ArgoCD | **Path**: N/A
- GitOps CD — selfHeal + prune, status API consumed by CP API
- **Incoming** (1 contracts):
  - `cp-argo-001` ← `control-plane-api` (rest-api): `ArgoCD REST API (sync, diff, status)` **UNTYPED**

### Prometheus + Grafana (`prometheus`)
- **Type**: infra | **Stack**: LGTM stack | **Path**: N/A
- Metrics scrape from CP API + Gateway, Grafana dashboards
- **Incoming** (4 contracts):
  - `cs-prom-001` ← `console` (metrics): `/prometheus/api/v1/query (same-origin proxy)` **UNTYPED**
  - `cp-prom-001` ← `control-plane-api` (metrics): `GET /metrics (stoa_control_plane_http_*)`
  - `conn-prom-001` ← `stoa-connect` (metrics): `GET /metrics (stoa_connect_*)`
  - `gw-prom-001` ← `stoa-gateway` (metrics): `GET /metrics (60+ metrics)`

### Control Plane API (`control-plane-api`)
- **Type**: service | **Stack**: Python 3.11, FastAPI 0.109, SQLAlchemy 2.0 | **Path**: `control-plane-api/`
- Central hub — 300+ endpoints, 65 tables, 40+ Kafka topics
- **Outgoing** (25 contracts):
  - `cp-argo-001` → `argocd` (rest-api): `ArgoCD REST API (sync, diff, status)` **UNTYPED**
  - `cp-rest-001` → `control-plane-api` (rest-api): `/v1/tenants CRUD`
  - `cp-rest-002` → `control-plane-api` (rest-api): `/v1/tenants/{tid}/apis CRUD`
  - `cp-rest-003` → `control-plane-api` (rest-api): `/v1/subscriptions CRUD`
  - `cp-rest-004` → `control-plane-api` (rest-api): `/v1/mcp/servers + /v1/mcp/subscriptions`
  - `cp-rest-005` → `control-plane-api` (rest-api): `/v1/portal/apis (public catalog)`
  - `cp-rest-006` → `control-plane-api` (rest-api): `/health` **UNTYPED**
  - `cp-kf-001` → `kafka` (kafka-event): `stoa.api.lifecycle` **UNTYPED**
  - `cp-kf-002` → `kafka` (kafka-event): `stoa.deployment.events` **UNTYPED**
  - `cp-kf-003` → `kafka` (kafka-event): `stoa.tenant.lifecycle` **UNTYPED**
  - `cp-kf-004` → `kafka` (kafka-event): `stoa.audit.trail` **UNTYPED**
  - `cp-kf-005` → `kafka` (kafka-event): `stoa.policy.changes` **UNTYPED**
  - `cp-kf-006` → `kafka` (kafka-event): `stoa.catalog.changes` **UNTYPED**
  - `cp-kf-007` → `kafka` (kafka-event): `stoa.app.lifecycle` **UNTYPED**
  - `cp-kf-008` → `kafka` (kafka-event): `stoa.security.alerts` **UNTYPED**
  - `cp-kf-009` → `kafka` (kafka-event): `stoa.errors` **UNTYPED**
  - `cp-kf-010` → `kafka` (kafka-event): `stoa.deploy.requests` **UNTYPED**
  - `cp-kc-001` → `keycloak` (admin-api): `Keycloak Admin REST API (python-keycloak)` **UNTYPED**
  - `cp-kc-002` → `keycloak` (oidc-flow): `OIDC JWT validation (RS256, JWKS)`
  - `cp-os-001` → `opensearch` (rest-api): `OpenSearch indexing (stoa-audit-*, stoa-errors-*, stoa-traces-*)` **UNTYPED**
  - `cp-pg-001` → `postgresql` (db-write): `SQLAlchemy ORM (65 tables)`
  - `cp-pg-002` → `postgresql` (db-read): `SQLAlchemy ORM queries`
  - `cp-prom-001` → `prometheus` (metrics): `GET /metrics (stoa_control_plane_http_*)`
  - `cp-gw-001` → `stoa-gateway` (admin-api): `StoaGatewayAdapter → /admin/*`
  - `cp-vault-001` → `vault` (rest-api): `Vault KV v2 (hvac)` **UNTYPED**
- **Incoming** (42 contracts):
  - `cs-cp-001` ← `console` (rest-api): `CRUD /v1/tenants` **UNTYPED**
  - `cs-cp-002` ← `console` (rest-api): `CRUD /v1/tenants/{t}/apis` **UNTYPED**
  - `cs-cp-003` ← `console` (rest-api): `CRUD /v1/consumers/{t}` **UNTYPED**
  - `cs-cp-004` ← `console` (rest-api): `CRUD /v1/subscriptions` **UNTYPED**
  - `cs-cp-005` ← `console` (rest-api): `CRUD /v1/tenants/{t}/deployments` **UNTYPED**
  - `cs-cp-006` ← `console` (rest-api): `CRUD /v1/tenants/{t}/promotions` **UNTYPED**
  - `cs-cp-007` ← `console` (rest-api): `CRUD /v1/admin/gateways` **UNTYPED**
  - `cs-cp-008` ← `console` (rest-api): `CRUD /v1/admin/policies` **UNTYPED**
  - `cs-cp-009` ← `console` (rest-api): `CRUD /v1/admin/external-mcp-servers` **UNTYPED**
  - `cs-cp-010` ← `console` (rest-api): `CRUD /v1/tenants/{t}/contracts` **UNTYPED**
  - `cs-cp-011` ← `console` (rest-api): `CRUD /v1/tenants/{t}/federation/accounts` **UNTYPED**
  - `cs-cp-012` ← `console` (rest-api): `GET /v1/platform/status` **UNTYPED**
  - `cs-cp-013` ← `console` (rest-api): `GET /v1/traces` **UNTYPED**
  - `cs-cp-014` ← `console` (rest-api): `GET /v1/business/metrics` **UNTYPED**
  - `cs-cp-015` ← `console` (sse): `EventSource /v1/events/stream/{tid}` **UNTYPED**
  - `cp-rest-001` ← `control-plane-api` (rest-api): `/v1/tenants CRUD`
  - `cp-rest-002` ← `control-plane-api` (rest-api): `/v1/tenants/{tid}/apis CRUD`
  - `cp-rest-003` ← `control-plane-api` (rest-api): `/v1/subscriptions CRUD`
  - `cp-rest-004` ← `control-plane-api` (rest-api): `/v1/mcp/servers + /v1/mcp/subscriptions`
  - `cp-rest-005` ← `control-plane-api` (rest-api): `/v1/portal/apis (public catalog)`
  - `cp-rest-006` ← `control-plane-api` (rest-api): `/health` **UNTYPED**
  - `pt-cp-001` ← `portal` (rest-api): `GET /v1/portal/apis (catalog)` **UNTYPED**
  - `pt-cp-002` ← `portal` (rest-api): `CRUD /v1/subscriptions` **UNTYPED**
  - `pt-cp-003` ← `portal` (rest-api): `CRUD /v1/mcp/servers + /v1/mcp/subscriptions` **UNTYPED**
  - `pt-cp-004` ← `portal` (rest-api): `CRUD /v1/applications` **UNTYPED**
  - `pt-cp-005` ← `portal` (rest-api): `CRUD /v1/consumers/{tenant_id}` **UNTYPED**
  - `pt-cp-006` ← `portal` (rest-api): `GET /v1/usage/me + /v1/dashboard/stats` **UNTYPED**
  - `pt-cp-007` ← `portal` (rest-api): `POST /v1/self-service/tenants` **UNTYPED**
  - `pt-cp-008` ← `portal` (rest-api): `CRUD /v1/contracts` **UNTYPED**
  - `pt-cp-009` ← `portal` (rest-api): `CRUD /v1/tenants/{tid}/mcp-servers` **UNTYPED**
  - `pt-cp-010` ← `portal` (rest-api): `CRUD /tenants/{tid}/webhooks` **UNTYPED**
  - `pt-cp-011` ← `portal` (rest-api): `GET /v1/me + POST /v1/me/tenant` **UNTYPED**
  - `conn-cp-001` ← `stoa-connect` (rest-api): `POST /v1/internal/gateways/register` **UNTYPED**
  - `conn-cp-002` ← `stoa-connect` (rest-api): `POST /v1/internal/gateways/{id}/heartbeat` **UNTYPED**
  - `conn-cp-003` ← `stoa-connect` (rest-api): `GET /v1/internal/gateways/{id}/config` **UNTYPED**
  - `conn-cp-004` ← `stoa-connect` (rest-api): `POST /v1/internal/gateways/{id}/sync-ack` **UNTYPED**
  - `conn-cp-005` ← `stoa-connect` (rest-api): `POST /v1/internal/gateways/{id}/discovery` **UNTYPED**
  - `gw-cp-001` ← `stoa-gateway` (rest-api): `POST /v1/gateway/internal/register`
  - `gw-cp-002` ← `stoa-gateway` (rest-api): `POST /v1/gateway/internal/heartbeat`
  - `gw-cp-003` ← `stoa-gateway` (rest-api): `GET /v1/mcp/validate`
  - `cli-cp-001` ← `stoactl` (rest-api): `GET /v1/tenants/{tid}/apis + CRUD` **UNTYPED**
  - `cli-cp-002` ← `stoactl` (rest-api): `GET /health` **UNTYPED**
- **Scenarios**: SCEN-003 (P0, unit), SCEN-001 (P0, none), SCEN-006 (P1, none), SCEN-005 (P1, unit)

### STOA Connect Agent (`stoa-connect`)
- **Type**: service | **Stack**: Go 1.22, Vault SDK, Prometheus | **Path**: `stoa-go/cmd/stoa-connect/`
- On-premise agent — bidirectional bridge, policy sync, 3 gateway adapters
- **Outgoing** (7 contracts):
  - `conn-cp-001` → `control-plane-api` (rest-api): `POST /v1/internal/gateways/register` **UNTYPED**
  - `conn-cp-002` → `control-plane-api` (rest-api): `POST /v1/internal/gateways/{id}/heartbeat` **UNTYPED**
  - `conn-cp-003` → `control-plane-api` (rest-api): `GET /v1/internal/gateways/{id}/config` **UNTYPED**
  - `conn-cp-004` → `control-plane-api` (rest-api): `POST /v1/internal/gateways/{id}/sync-ack` **UNTYPED**
  - `conn-cp-005` → `control-plane-api` (rest-api): `POST /v1/internal/gateways/{id}/discovery` **UNTYPED**
  - `conn-prom-001` → `prometheus` (metrics): `GET /metrics (stoa_connect_*)`
  - `conn-vault-001` → `vault` (rest-api): `Vault KV v2 stoa/data/consumers/{tid}` **UNTYPED**

## Dependency Matrix

| Source \ Target | stoact | vault | kafka | keyclo | opense | postgr | consol | portal | stoa-g | argocd | promet | contro | stoa-c |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **stoactl** | - |   |   | x |   |   |   |   |   |   |   | x |   |
| **vault** |   | - |   |   |   |   |   |   |   |   |   |   |   |
| **kafka** |   |   | - |   |   |   |   |   |   |   |   |   |   |
| **keycloak** |   |   |   | - |   |   |   |   |   |   |   |   |   |
| **opensearch** |   |   |   |   | - |   |   |   |   |   |   |   |   |
| **postgresql** |   |   |   |   |   | - |   |   |   |   |   |   |   |
| **console** |   |   |   | x |   |   | - |   |   |   | x | x |   |
| **portal** |   |   |   | x |   |   |   | - | x |   |   | x |   |
| **stoa-gateway** |   |   | x | x |   |   |   |   | - |   | x | x |   |
| **argocd** |   |   |   |   |   |   |   |   |   | - |   |   |   |
| **prometheus** |   |   |   |   |   |   |   |   |   |   | - |   |   |
| **control-plane-** |   | x | x | x | x | x |   |   | x | x | x | - |   |
| **stoa-connect** |   | x |   |   |   |   |   |   |   |   | x | x | - |

## Untyped Contracts (Risk Alert)

**55 contracts** have no formal schema enforcement:

| ID | Source → Target | Type | Reference |
|---|---|---|---|
| `cp-kc-001` | control-plane-api → keycloak | admin-api | `Keycloak Admin REST API (python-keycloak)` |
| `gw-kc-002` | stoa-gateway → keycloak | admin-api | `POST /oauth/register proxy → KC DCR + PKCE patch` |
| `cp-kf-001` | control-plane-api → kafka | kafka-event | `stoa.api.lifecycle` |
| `cp-kf-002` | control-plane-api → kafka | kafka-event | `stoa.deployment.events` |
| `cp-kf-003` | control-plane-api → kafka | kafka-event | `stoa.tenant.lifecycle` |
| `cp-kf-004` | control-plane-api → kafka | kafka-event | `stoa.audit.trail` |
| `cp-kf-005` | control-plane-api → kafka | kafka-event | `stoa.policy.changes` |
| `cp-kf-006` | control-plane-api → kafka | kafka-event | `stoa.catalog.changes` |
| `cp-kf-007` | control-plane-api → kafka | kafka-event | `stoa.app.lifecycle` |
| `cp-kf-008` | control-plane-api → kafka | kafka-event | `stoa.security.alerts` |
| `cp-kf-009` | control-plane-api → kafka | kafka-event | `stoa.errors` |
| `cp-kf-010` | control-plane-api → kafka | kafka-event | `stoa.deploy.requests` |
| `gw-kf-001` | stoa-gateway → kafka | kafka-event | `stoa.metering.events` |
| `gw-kf-002` | stoa-gateway → kafka | kafka-event | `stoa.errors` |
| `gw-kf-003` | stoa-gateway → kafka | kafka-event | `stoa.security.alerts` |
| `gw-kf-004` | stoa-gateway → kafka | kafka-event | `stoa.gateway.metrics` |
| `cs-prom-001` | console → prometheus | metrics | `/prometheus/api/v1/query (same-origin proxy)` |
| `cp-os-001` | control-plane-api → opensearch | rest-api | `OpenSearch indexing (stoa-audit-*, stoa-errors-*, stoa-traces-*)` |
| `cp-vault-001` | control-plane-api → vault | rest-api | `Vault KV v2 (hvac)` |
| `cp-argo-001` | control-plane-api → argocd | rest-api | `ArgoCD REST API (sync, diff, status)` |
| `cp-rest-006` | control-plane-api → control-plane-api | rest-api | `/health` |
| `cs-cp-001` | console → control-plane-api | rest-api | `CRUD /v1/tenants` |
| `cs-cp-002` | console → control-plane-api | rest-api | `CRUD /v1/tenants/{t}/apis` |
| `cs-cp-003` | console → control-plane-api | rest-api | `CRUD /v1/consumers/{t}` |
| `cs-cp-004` | console → control-plane-api | rest-api | `CRUD /v1/subscriptions` |
| `cs-cp-005` | console → control-plane-api | rest-api | `CRUD /v1/tenants/{t}/deployments` |
| `cs-cp-006` | console → control-plane-api | rest-api | `CRUD /v1/tenants/{t}/promotions` |
| `cs-cp-007` | console → control-plane-api | rest-api | `CRUD /v1/admin/gateways` |
| `cs-cp-008` | console → control-plane-api | rest-api | `CRUD /v1/admin/policies` |
| `cs-cp-009` | console → control-plane-api | rest-api | `CRUD /v1/admin/external-mcp-servers` |
| `cs-cp-010` | console → control-plane-api | rest-api | `CRUD /v1/tenants/{t}/contracts` |
| `cs-cp-011` | console → control-plane-api | rest-api | `CRUD /v1/tenants/{t}/federation/accounts` |
| `cs-cp-012` | console → control-plane-api | rest-api | `GET /v1/platform/status` |
| `cs-cp-013` | console → control-plane-api | rest-api | `GET /v1/traces` |
| `cs-cp-014` | console → control-plane-api | rest-api | `GET /v1/business/metrics` |
| `pt-cp-001` | portal → control-plane-api | rest-api | `GET /v1/portal/apis (catalog)` |
| `pt-cp-002` | portal → control-plane-api | rest-api | `CRUD /v1/subscriptions` |
| `pt-cp-003` | portal → control-plane-api | rest-api | `CRUD /v1/mcp/servers + /v1/mcp/subscriptions` |
| `pt-cp-004` | portal → control-plane-api | rest-api | `CRUD /v1/applications` |
| `pt-cp-005` | portal → control-plane-api | rest-api | `CRUD /v1/consumers/{tenant_id}` |
| `pt-cp-006` | portal → control-plane-api | rest-api | `GET /v1/usage/me + /v1/dashboard/stats` |
| `pt-cp-007` | portal → control-plane-api | rest-api | `POST /v1/self-service/tenants` |
| `pt-cp-008` | portal → control-plane-api | rest-api | `CRUD /v1/contracts` |
| `pt-cp-009` | portal → control-plane-api | rest-api | `CRUD /v1/tenants/{tid}/mcp-servers` |
| `pt-cp-010` | portal → control-plane-api | rest-api | `CRUD /tenants/{tid}/webhooks` |
| `pt-cp-011` | portal → control-plane-api | rest-api | `GET /v1/me + POST /v1/me/tenant` |
| `cli-cp-001` | stoactl → control-plane-api | rest-api | `GET /v1/tenants/{tid}/apis + CRUD` |
| `cli-cp-002` | stoactl → control-plane-api | rest-api | `GET /health` |
| `conn-cp-001` | stoa-connect → control-plane-api | rest-api | `POST /v1/internal/gateways/register` |
| `conn-cp-002` | stoa-connect → control-plane-api | rest-api | `POST /v1/internal/gateways/{id}/heartbeat` |
| `conn-cp-003` | stoa-connect → control-plane-api | rest-api | `GET /v1/internal/gateways/{id}/config` |
| `conn-cp-004` | stoa-connect → control-plane-api | rest-api | `POST /v1/internal/gateways/{id}/sync-ack` |
| `conn-cp-005` | stoa-connect → control-plane-api | rest-api | `POST /v1/internal/gateways/{id}/discovery` |
| `conn-vault-001` | stoa-connect → vault | rest-api | `Vault KV v2 stoa/data/consumers/{tid}` |
| `cs-cp-015` | console → control-plane-api | sse | `EventSource /v1/events/stream/{tid}` |

## Risk Summary

| ID | Severity | Title | Status | Ticket |
|---|---|---|---|---|
| RISK-001 | **CRITICAL** | No Formal Schema for Kafka Events | open | — |
| RISK-002 | **HIGH** | Frontend-Backend Contract Drift | open | — |
| RISK-003 | **HIGH** | Duplicate MCP Subscription Paths | open | — |
| RISK-004 | **HIGH** | No E2E Integration Tests in CI | open | — |
| RISK-005 | MEDIUM | Gateway-CP API Internal Auth (X-Operator-Key) | open | — |
| RISK-006 | MEDIUM | Health Check Inconsistency | mitigated | CAB-1916 |
| RISK-007 | MEDIUM | OpenSearch Optional Dependency | open | — |
| RISK-008 | LOW | Shared Directory Build Context | accepted | — |

## Contract Inventory

| ID | Source | Target | Type | Reference | Typed |
|---|---|---|---|---|---|
| `cli-cp-001` | stoactl | control-plane-api | rest-api | `GET /v1/tenants/{tid}/apis + CRUD` | **No** |
| `cli-cp-002` | stoactl | control-plane-api | rest-api | `GET /health` | **No** |
| `cli-kc-001` | stoactl | keycloak | oidc-flow | `Device Authorization Grant (stoactl client)` | Yes |
| `conn-cp-001` | stoa-connect | control-plane-api | rest-api | `POST /v1/internal/gateways/register` | **No** |
| `conn-cp-002` | stoa-connect | control-plane-api | rest-api | `POST /v1/internal/gateways/{id}/heartbeat` | **No** |
| `conn-cp-003` | stoa-connect | control-plane-api | rest-api | `GET /v1/internal/gateways/{id}/config` | **No** |
| `conn-cp-004` | stoa-connect | control-plane-api | rest-api | `POST /v1/internal/gateways/{id}/sync-ack` | **No** |
| `conn-cp-005` | stoa-connect | control-plane-api | rest-api | `POST /v1/internal/gateways/{id}/discovery` | **No** |
| `conn-prom-001` | stoa-connect | prometheus | metrics | `GET /metrics (stoa_connect_*)` | Yes |
| `conn-vault-001` | stoa-connect | vault | rest-api | `Vault KV v2 stoa/data/consumers/{tid}` | **No** |
| `cp-argo-001` | control-plane-api | argocd | rest-api | `ArgoCD REST API (sync, diff, status)` | **No** |
| `cp-gw-001` | control-plane-api | stoa-gateway | admin-api | `StoaGatewayAdapter → /admin/*` | Yes |
| `cp-kc-001` | control-plane-api | keycloak | admin-api | `Keycloak Admin REST API (python-keycloak)` | **No** |
| `cp-kc-002` | control-plane-api | keycloak | oidc-flow | `OIDC JWT validation (RS256, JWKS)` | Yes |
| `cp-kf-001` | control-plane-api | kafka | kafka-event | `stoa.api.lifecycle` | **No** |
| `cp-kf-002` | control-plane-api | kafka | kafka-event | `stoa.deployment.events` | **No** |
| `cp-kf-003` | control-plane-api | kafka | kafka-event | `stoa.tenant.lifecycle` | **No** |
| `cp-kf-004` | control-plane-api | kafka | kafka-event | `stoa.audit.trail` | **No** |
| `cp-kf-005` | control-plane-api | kafka | kafka-event | `stoa.policy.changes` | **No** |
| `cp-kf-006` | control-plane-api | kafka | kafka-event | `stoa.catalog.changes` | **No** |
| `cp-kf-007` | control-plane-api | kafka | kafka-event | `stoa.app.lifecycle` | **No** |
| `cp-kf-008` | control-plane-api | kafka | kafka-event | `stoa.security.alerts` | **No** |
| `cp-kf-009` | control-plane-api | kafka | kafka-event | `stoa.errors` | **No** |
| `cp-kf-010` | control-plane-api | kafka | kafka-event | `stoa.deploy.requests` | **No** |
| `cp-os-001` | control-plane-api | opensearch | rest-api | `OpenSearch indexing (stoa-audit-*, stoa-errors-*, stoa-traces-*)` | **No** |
| `cp-pg-001` | control-plane-api | postgresql | db-write | `SQLAlchemy ORM (65 tables)` | Yes |
| `cp-pg-002` | control-plane-api | postgresql | db-read | `SQLAlchemy ORM queries` | Yes |
| `cp-prom-001` | control-plane-api | prometheus | metrics | `GET /metrics (stoa_control_plane_http_*)` | Yes |
| `cp-rest-001` | control-plane-api | control-plane-api | rest-api | `/v1/tenants CRUD` | Yes |
| `cp-rest-002` | control-plane-api | control-plane-api | rest-api | `/v1/tenants/{tid}/apis CRUD` | Yes |
| `cp-rest-003` | control-plane-api | control-plane-api | rest-api | `/v1/subscriptions CRUD` | Yes |
| `cp-rest-004` | control-plane-api | control-plane-api | rest-api | `/v1/mcp/servers + /v1/mcp/subscriptions` | Yes |
| `cp-rest-005` | control-plane-api | control-plane-api | rest-api | `/v1/portal/apis (public catalog)` | Yes |
| `cp-rest-006` | control-plane-api | control-plane-api | rest-api | `/health` | **No** |
| `cp-vault-001` | control-plane-api | vault | rest-api | `Vault KV v2 (hvac)` | **No** |
| `cs-cp-001` | console | control-plane-api | rest-api | `CRUD /v1/tenants` | **No** |
| `cs-cp-002` | console | control-plane-api | rest-api | `CRUD /v1/tenants/{t}/apis` | **No** |
| `cs-cp-003` | console | control-plane-api | rest-api | `CRUD /v1/consumers/{t}` | **No** |
| `cs-cp-004` | console | control-plane-api | rest-api | `CRUD /v1/subscriptions` | **No** |
| `cs-cp-005` | console | control-plane-api | rest-api | `CRUD /v1/tenants/{t}/deployments` | **No** |
| `cs-cp-006` | console | control-plane-api | rest-api | `CRUD /v1/tenants/{t}/promotions` | **No** |
| `cs-cp-007` | console | control-plane-api | rest-api | `CRUD /v1/admin/gateways` | **No** |
| `cs-cp-008` | console | control-plane-api | rest-api | `CRUD /v1/admin/policies` | **No** |
| `cs-cp-009` | console | control-plane-api | rest-api | `CRUD /v1/admin/external-mcp-servers` | **No** |
| `cs-cp-010` | console | control-plane-api | rest-api | `CRUD /v1/tenants/{t}/contracts` | **No** |
| `cs-cp-011` | console | control-plane-api | rest-api | `CRUD /v1/tenants/{t}/federation/accounts` | **No** |
| `cs-cp-012` | console | control-plane-api | rest-api | `GET /v1/platform/status` | **No** |
| `cs-cp-013` | console | control-plane-api | rest-api | `GET /v1/traces` | **No** |
| `cs-cp-014` | console | control-plane-api | rest-api | `GET /v1/business/metrics` | **No** |
| `cs-cp-015` | console | control-plane-api | sse | `EventSource /v1/events/stream/{tid}` | **No** |
| `cs-kc-001` | console | keycloak | oidc-flow | `OIDC Authorization Code + PKCE (control-plane-ui client)` | Yes |
| `cs-prom-001` | console | prometheus | metrics | `/prometheus/api/v1/query (same-origin proxy)` | **No** |
| `gw-admin-001` | stoa-gateway | stoa-gateway | admin-api | `/admin/* (70+ endpoints)` | Yes |
| `gw-cp-001` | stoa-gateway | control-plane-api | rest-api | `POST /v1/gateway/internal/register` | Yes |
| `gw-cp-002` | stoa-gateway | control-plane-api | rest-api | `POST /v1/gateway/internal/heartbeat` | Yes |
| `gw-cp-003` | stoa-gateway | control-plane-api | rest-api | `GET /v1/mcp/validate` | Yes |
| `gw-kc-001` | stoa-gateway | keycloak | oidc-flow | `OIDC JWT validation (JWKS fetch)` | Yes |
| `gw-kc-002` | stoa-gateway | keycloak | admin-api | `POST /oauth/register proxy → KC DCR + PKCE patch` | **No** |
| `gw-kc-003` | stoa-gateway | keycloak | oidc-flow | `POST /oauth/token proxy → KC token endpoint` | Yes |
| `gw-kf-001` | stoa-gateway | kafka | kafka-event | `stoa.metering.events` | **No** |
| `gw-kf-002` | stoa-gateway | kafka | kafka-event | `stoa.errors` | **No** |
| `gw-kf-003` | stoa-gateway | kafka | kafka-event | `stoa.security.alerts` | **No** |
| `gw-kf-004` | stoa-gateway | kafka | kafka-event | `stoa.gateway.metrics` | **No** |
| `gw-mcp-001` | stoa-gateway | stoa-gateway | rest-api | `GET /mcp/capabilities (RFC 9728)` | Yes |
| `gw-mcp-002` | stoa-gateway | stoa-gateway | rest-api | `POST /mcp/tools/list + /mcp/tools/call (JSON-RPC 2.0)` | Yes |
| `gw-oauth-001` | stoa-gateway | stoa-gateway | rest-api | `/.well-known/oauth-protected-resource (RFC 9728)` | Yes |
| `gw-oauth-002` | stoa-gateway | stoa-gateway | rest-api | `/.well-known/oauth-authorization-server (RFC 8414)` | Yes |
| `gw-prom-001` | stoa-gateway | prometheus | metrics | `GET /metrics (60+ metrics)` | Yes |
| `pt-cp-001` | portal | control-plane-api | rest-api | `GET /v1/portal/apis (catalog)` | **No** |
| `pt-cp-002` | portal | control-plane-api | rest-api | `CRUD /v1/subscriptions` | **No** |
| `pt-cp-003` | portal | control-plane-api | rest-api | `CRUD /v1/mcp/servers + /v1/mcp/subscriptions` | **No** |
| `pt-cp-004` | portal | control-plane-api | rest-api | `CRUD /v1/applications` | **No** |
| `pt-cp-005` | portal | control-plane-api | rest-api | `CRUD /v1/consumers/{tenant_id}` | **No** |
| `pt-cp-006` | portal | control-plane-api | rest-api | `GET /v1/usage/me + /v1/dashboard/stats` | **No** |
| `pt-cp-007` | portal | control-plane-api | rest-api | `POST /v1/self-service/tenants` | **No** |
| `pt-cp-008` | portal | control-plane-api | rest-api | `CRUD /v1/contracts` | **No** |
| `pt-cp-009` | portal | control-plane-api | rest-api | `CRUD /v1/tenants/{tid}/mcp-servers` | **No** |
| `pt-cp-010` | portal | control-plane-api | rest-api | `CRUD /tenants/{tid}/webhooks` | **No** |
| `pt-cp-011` | portal | control-plane-api | rest-api | `GET /v1/me + POST /v1/me/tenant` | **No** |
| `pt-gw-001` | portal | stoa-gateway | rest-api | `GET /mcp/v1/tools` | Yes |
| `pt-gw-002` | portal | stoa-gateway | rest-api | `POST /mcp/v1/tools/{name}/invoke` | Yes |
| `pt-gw-003` | portal | stoa-gateway | rest-api | `CRUD /mcp/v1/subscriptions` | Yes |
| `pt-kc-001` | portal | keycloak | oidc-flow | `OIDC Authorization Code + PKCE (stoa-portal client)` | Yes |
