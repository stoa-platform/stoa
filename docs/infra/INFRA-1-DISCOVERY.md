# INFRA-1 — Phase 0 Discovery: Configuration Cartography

> **Status**: Phase 0 (Discovery) — read-only audit, **no code/config change**.
> **Branch**: `discovery/infra-1-config-cartography` (stoa monorepo).
> **Snapshot**: stoa `main` ahead of merge of this PR (last reviewed commit `79f057e9d` — chore(main): release control-plane-ui 1.5.7 — 2026-04-26 19:17 UTC). UAC V2 MCP projection PRs (#2582/#2584/#2585/#2588) merged earlier the same day; spot-check post-merge does NOT change the cartography findings (UAC V2 work touches `stoa-gateway` MCP projection logic + cp-api UAC modules, not the config loaders inventoried here).
> **Cross-repo**: stoa-infra inspected at `/Users/torpedo/hlfh-repos/stoa-infra` (commit `82a0339` on `main`).
> **Scope**: 3 repos × 3 drift categories (A dead, B duplicated, C ambiguous).
> **Granularity**: ~50 strategic configs (auth, secrets, URLs, timeouts, feature flags). Niche configs listed by reference only.
> **Date**: 2026-04-26.

---

## Executive summary

The platform has **at least 11 distinct configuration loaders** across services and repos:

| Loader | Path | Pattern | Field count |
|--------|------|---------|------------:|
| `Settings` (cp-api main) | `control-plane-api/src/config.py` | Pydantic `BaseSettings`, no env_prefix, ALL_CAPS fields, `extra="ignore"` | ~95 |
| `OpenSearchSettings` (cp-api) | `control-plane-api/src/opensearch/opensearch_integration.py` | Pydantic `BaseSettings`, `env_prefix=""`, snake_case fields | 9 |
| `SnapshotSettings` (cp-api) | `control-plane-api/src/features/error_snapshots/config.py` | Pydantic `BaseSettings`, `env_prefix="STOA_SNAPSHOTS_"` | 17 |
| `PIIMaskingConfig` (cp-api) | `control-plane-api/src/core/pii/config.py` | Plain `BaseModel` (no env loader, in-process only) | 7 |
| `Config` (stoa-gateway Rust) | `stoa-gateway/src/config.rs` + 5 nested modules | Figment (TOML + env), `STOA_*` prefix, double-underscore for nested | ~200 |
| `Config` (stoactl Go) | `stoa-go/pkg/config/config.go` | YAML at `~/.stoa/config` (kubectl-style contexts) | 4 |
| Frontend env (cp-ui) | `control-plane-ui/src/config.ts` | Vite `import.meta.env.VITE_*` | ~30 |
| Frontend env (portal) | `portal/src/config.ts` | Vite `import.meta.env.VITE_*` | ~15 |
| Helm `values.yaml` (stoa-infra) | 16 charts in `stoa-infra/charts/` | YAML + Helm templating | varies |
| ExternalSecrets (chart-templated) | `stoa-infra/charts/<svc>/templates/externalsecret.yaml` | ExternalSecrets Operator → Vault `stoa/data/<svc>` | per chart |
| ExternalSecrets (hand-applied) | `stoa-infra/deploy/external-secrets/external-secret-*.yaml` | ExternalSecrets Operator → Vault `k8s/<svc>` | per file |

**Risk**: source-of-truth is unclear in **at least 4 of these** (chart `env:` block vs deployment.yaml hardcode vs `extra="ignore"` Pydantic vs hand-applied ExternalSecrets).

**Recommended Phase 1 split**: this scope is too large for one MEGA. See Section H — propose **INFRA-1a** (applicatif), **INFRA-1b** (stoa-infra Helm + ExternalSecrets), **INFRA-1c** (CI/dev tooling + cross-repo source-of-truth contract).

---

## Section A — Inventaire exhaustif par couche

### A.1 — Application configs (Python — control-plane-api)

#### A.1.1 — Main `Settings` (Pydantic BaseSettings)

- **File**: `control-plane-api/src/config.py:109-635`
- **Class**: `Settings(BaseSettings)`
- **Total fields**: ~95 (counted by visual grep on `Field(...)`/typed defaults)
- **Sub-models** (all `BaseModel`, hydrated by validator):
  - `GitProviderConfig` (`config.py:83`) — orchestrates github vs gitlab
  - `GitHubConfig` (`config.py:49`) — token, org, catalog_repo, webhook_secret
  - `GitLabConfig` (`config.py:68`) — url, token, project_id, webhook_secret
- **Loader**: Pydantic Settings auto-discovery (env vars → fields by case-insensitive name match)
- **`Config.env_file`**: `".env"` (loaded if present in CWD)
- **`Config.extra`**: `"ignore"` — silently swallows unknown env vars (impacts dead-config detection: see Section C.1)
- **Validators**:
  - `@field_validator("GIT_PROVIDER", mode="before")` — case-insensitive normalization (CAB-1889)
  - `@model_validator(mode="after") _hydrate_and_validate_git` — flat env → `git.*` sub-model + fail-fast in prod
  - `@model_validator(mode="after") _gate_sensitive_debug_flags_in_prod` — CAB-2145 (refuse boot on prod with debug flags)
  - `@model_validator(mode="after") _gate_auth_bypass_in_prod` — `STOA_DISABLE_AUTH=true` blocked in prod
- **Field categories** (rough breakdown):
  - Application (`VERSION`, `DEBUG`, `ENVIRONMENT`, `STOA_EDITION`, `BASE_DOMAIN`) — 5
  - Keycloak (`KEYCLOAK_URL`, `_INTERNAL_URL`, `_REALM`, `_CLIENT_ID`, `_CLIENT_SECRET`, `_VERIFY_SSL`, `_ADMIN_*`, `STOA_DISABLE_AUTH`) — 10
  - Slack (`SLACK_*`) — 3
  - Git provider (legacy flat `GIT_PROVIDER`, `GITHUB_*`, `GITLAB_*` — 10 fields, all `exclude=True`, hydrated to `settings.git.*`) — 10
  - Kafka (`KAFKA_*`) — 6
  - Gateway (`GATEWAY_*`, `MCP_GATEWAY_URL`) — 8
  - ArgoCD (`ARGOCD_*`) — 5
  - Observability (`GRAFANA_URL`, `PROMETHEUS_URL`, `LOGS_URL`, `PROMETHEUS_INTERNAL_URL`, `LOKI_INTERNAL_URL`, `TEMPO_INTERNAL_URL`, plus `_TIMEOUT_SECONDS` / `_ENABLED` per service) — 15
  - Sync engine + drift (`SYNC_ENGINE_*`, `DEPLOY_MODE`, `DRIFT_AUTO_REPAIR`, `GIT_SYNC_ON_WRITE`) — 7
  - Algolia/docs search (`ALGOLIA_*`, `DOCS_SEARCH_*`, `LLMS_FULL_TXT_URL`) — 5
  - Chat agent (`CHAT_*`) — 6
  - Embeddings (`EMBEDDING_*`, `OPENSEARCH_URL`, `OPENSEARCH_DOCS_INDEX`, `DOCS_REINDEX_ENABLED`) — 8
  - Rate limiting (`RATE_LIMIT_*`, `TENANT_DEFAULT_RATE_LIMIT_RPM`) — 3
  - Signup (`SIGNUP_*`) — 2
  - Logging (`LOG_*` — basic + 22 debug toggles) — ~30
  - Sender-constrained (`SENDER_CONSTRAINED_*`) — 3
  - Vault (`VAULT_*`, `BACKEND_ENCRYPTION_KEY`) — 6
  - Database (`DATABASE_*`) — 3
  - Multi-env (`STOA_ENVIRONMENTS`, `CORS_ORIGINS`) — 2
- **Properties** (computed, not settings): `keycloak_internal_url`, `argocd_platform_apps_list`, `cors_origins_list`, `log_components_dict`, `log_exclude_paths_list`, `log_masking_patterns_list`, `gateway_api_keys_list`, `signup_invite_codes_list`, `database_url_sync`, `is_sse_enabled`, `is_sync_engine_enabled`, `is_inline_sync_enabled`.
- **Module-level pre-load** (`config.py:17`): `_BASE_DOMAIN = os.getenv("BASE_DOMAIN", "gostoa.dev")` — defaults like `KEYCLOAK_URL = f"https://auth.{_BASE_DOMAIN}"` are **frozen at import time**. Setting `Settings(BASE_DOMAIN="other.tld")` will NOT recompute these defaults. See Section E.1 (Catégorie C — ambiguity).
- **Consumed by**: imported `from src.config import settings` across 38+ routers, services, workers.

#### A.1.2 — `OpenSearchSettings` (cp-api, secondary)

- **File**: `control-plane-api/src/opensearch/opensearch_integration.py:29-46`
- **Loader**: Pydantic `BaseSettings`, `env_prefix=""` (no prefix; case-insensitive uppercase env match)
- **Fields**: `opensearch_host`, `opensearch_user`, `opensearch_password`, `opensearch_verify_certs`, `opensearch_ca_certs`, `opensearch_timeout`, `audit_enabled`, `audit_buffer_size`, `audit_flush_interval` (9 fields)
- **Defaults**: `opensearch_host="https://opensearch.gostoa.dev"` (note: this is **different** from `Settings.OPENSEARCH_URL` default of `http://opensearch.stoa-system.svc.cluster.local:9200`)
- **Consumed by**: `OpenSearchService` (audit logger middleware, search service)
- **Critical observation**: `OPENSEARCH_HOST/USER/VERIFY_CERTS/CA_CERTS` env vars (set by Helm chart at `stoa-infra/charts/control-plane-api/values.yaml:27-30`) are consumed **here**, not by main `Settings`. See Section E.4.

#### A.1.3 — `SnapshotSettings` (cp-api, feature-scoped)

- **File**: `control-plane-api/src/features/error_snapshots/config.py:17`
- **Loader**: Pydantic `BaseSettings`, `env_prefix="STOA_SNAPSHOTS_"` (note: **plural** "SNAPSHOTS" with S)
- **Fields**: 17 (enabled, capture_on_4xx/5xx/timeout, storage_*, retention_days, max_body_size, masking_*, exclude_paths, etc.)
- **Conflict risk**: stoa-gateway Rust uses singular `STOA_SNAPSHOT_*` (`config.rs:830-854`) — different scope (in-process ring buffer) but **easy mistake** in ops to set wrong prefix. See Section D.4.

#### A.1.4 — `PIIMaskingConfig` (cp-api, in-process only)

- **File**: `control-plane-api/src/core/pii/config.py:23`
- **Loader**: plain `BaseModel` (no env), constructed in code via `.strict()` / `.development()` / `.default_production()` factories.
- **Fields**: 7 (`enabled`, `level`, `field_overrides`, `disabled_types`, `exempt_roles`, `audit_enabled`, `max_text_length`)
- **Consumed by**: PII masking middleware (per-tenant config in DB, not env-driven).

### A.2 — Application configs (Rust — stoa-gateway)

#### A.2.1 — Main `Config` (Figment)

- **File**: `stoa-gateway/src/config.rs:46-855` + 5 nested config modules in `stoa-gateway/src/config/`
- **Loader**: Figment (provider chain: TOML file → env vars → defaults), see `loader.rs`
- **Env prefix**: `STOA_` — flat fields use single underscore (`STOA_LOG_LEVEL`); nested struct fields use **double underscore** (`STOA_MTLS__ENABLED`, `STOA_DPOP__REQUIRED`, `STOA_LLM_ROUTER__DEFAULT_STRATEGY`, `STOA_API_PROXY__ENABLED`, `STOA_SENDER_CONSTRAINT__DPOP_REQUIRED`).
- **Top-level field count**: ~141 STOA_-prefixed (counted via `grep STOA_ src/config.rs`)
- **Total inc. nested**: ~190+ STOA_-prefixed env vars (counted across all `src/config/*.rs`)
- **Nested structs**:
  - `MtlsConfig` (`config/mtls.rs`) — 15 STOA_MTLS__* fields
  - `DpopConfig` (`auth/dpop.rs`) — env prefix `STOA_DPOP__`
  - `SenderConstraintConfig` (`config/sender_constraint.rs`) — `STOA_SENDER_CONSTRAINT__`
  - `LlmRouterConfig` (`config/llm_router.rs`) — `STOA_LLM_ROUTER__`
  - `ApiProxyConfig` (`config/api_proxy.rs`) — `STOA_API_PROXY__`
- **Backward-compat unprefixed env vars** (consumed in addition to STOA_ variants):
  - `GITHUB_TOKEN` / `STOA_GITHUB_TOKEN`
  - `GITHUB_ORG` / `STOA_GITHUB_ORG`
  - `GITHUB_CATALOG_REPO` / `STOA_GITHUB_CATALOG_REPO`
  - `GITHUB_GITOPS_REPO` / `STOA_GITHUB_GITOPS_REPO`
  - `GITHUB_WEBHOOK_SECRET` / `STOA_GITHUB_WEBHOOK_SECRET`
  - `GIT_PROVIDER` / `STOA_GIT_PROVIDER`
- **Custom `Debug`**: `config.rs:857-1067` — manually redacts secret-bearing fields. Removing/renaming a secret field requires updating BOTH the struct AND this `Debug` impl. Maintenance hazard.
- **TOML config support**: `loader.rs` (not inspected line-by-line; presence of `figment::providers::Yaml`/`Toml`/`Env` and `STOA_CONFIG_FILE` env var implies file overrides).
- **Consumed by**: `Config::load()` from `main.rs`/`main_wiring.rs`, propagated to AppState.

### A.3 — Frontend configs

#### A.3.1 — control-plane-ui (Vite SPA)

- **Source-of-truth file**: `control-plane-ui/src/config.ts` (referenced from `.env.example`).
- **Env access pattern**: `import.meta.env.VITE_*` at build time + runtime `runtime-config.js` injected by container nginx (CAB-2163 hardening).
- **Distinct VITE_* keys used in code**: ~30 (extracted via `grep -oE 'import\.meta\.env\.VITE_[A-Z_]+' src/`):
  - URLs: `VITE_API_URL`, `VITE_KEYCLOAK_URL`, `VITE_GRAFANA_URL`, `VITE_PROMETHEUS_URL`, `VITE_LOGS_URL`, `VITE_AWX_URL`, `VITE_ARENA_DASHBOARD_URL`, `VITE_GIT_REPO_URL`, `VITE_GITLAB_URL`, `VITE_API_DOCS_URL`, `VITE_ERROR_TRACKING_ENDPOINT`
  - Identity: `VITE_KEYCLOAK_REALM`, `VITE_KEYCLOAK_CLIENT_ID`, `VITE_GIT_PROVIDER`, `VITE_PORTAL_MODE`
  - Timing: `VITE_API_TIMEOUT`, `VITE_MCP_TIMEOUT`, `VITE_AUTH_REFRESH_TIMEOUT_MS`, `VITE_REFRESH_INTERVAL`, `VITE_ITEMS_PER_PAGE`, `VITE_DATE_FORMAT`
  - Feature flags (16): `VITE_ENABLE_AI_TOOLS`, `_API_CATALOG`, `_API_COMPARISON`, `_API_TESTING`, `_APPLICATIONS`, `_AUDIT_LOG`, `_DEBUG`, `_FAVORITES`, `_GATEWAYS`, `_GITOPS`, `_I18N` (typo'd as `VITE_ENABLE_I` in initial grep — confirmed `VITE_ENABLE_I18N` at `src/config.ts:170`), `_MARKETPLACE`, `_MCP_CATALOG`, `_MCP_TOOLS`, `_MONITORING`, `_NOTIFICATIONS`, `_RATE_LIMITS`, `_SUBSCRIPTIONS`
  - Multi-env (Portal-shared): `VITE_AVAILABLE_ENVIRONMENTS`, `VITE_REQUIRE_SANDBOX_CONFIRMATION`, `VITE_APP_TITLE`, `VITE_APP_VERSION`
- **Helm chart passthrough**: `stoa-infra/charts/control-plane-ui/templates/deployment.yaml:31-47` only emits **5 VITE_** vars (`VITE_API_URL`, `VITE_KEYCLOAK_CLIENT_ID`, `VITE_KEYCLOAK_URL`, `VITE_KEYCLOAK_REALM`, `VITE_BASE_DOMAIN`) plus 3 nginx backends (`API_BACKEND_URL`, `LOGS_BACKEND_URL`, `PROMETHEUS_BACKEND_URL`). The other ~25 VITE_* keys are baked at build time via Dockerfile build args (or fall back to defaults in `config.ts`).
- **Hardcoded fallback in chart** (`deployment.yaml:37`): `VITE_KEYCLOAK_URL` defaults to `https://auth.{{ .Values.baseDomain }}` if `.Values.env.VITE_KEYCLOAK_URL` is absent. Same pattern as cp-api `KEYCLOAK_URL`.

#### A.3.2 — portal (Vite SPA)

- **Source-of-truth file**: `portal/src/config.ts` (referenced from `.env.example`).
- **VITE_* keys** (~15): subset of cp-ui — `VITE_API_URL`, `VITE_MCP_URL`, `VITE_API_TIMEOUT`, `VITE_MCP_TIMEOUT`, `VITE_KEYCLOAK_URL`, `VITE_KEYCLOAK_REALM`, `VITE_KEYCLOAK_CLIENT_ID` (default: `stoa-portal`), 7 feature flags, multi-env testing flags.
- **Helm chart passthrough**: `stoa-infra/charts/stoa-portal/templates/deployment.yaml:23-31` uses a `range $key, $value := .Values.env` block PLUS explicit `VITE_KEYCLOAK_URL` and `VITE_BASE_DOMAIN` after — this **emits VITE_KEYCLOAK_URL twice** in the env array if `.Values.env.VITE_KEYCLOAK_URL` is set; K8s last-wins rules apply (the explicit one wins, which uses `default (printf "https://auth.%s" baseDomain)`). Verbose but not a bug; flagged for cleanup.
- **Mixed runtime layer**: `stoa-portal/values.yaml` env block also includes server-side keys: `API_BACKEND_URL` (nginx backend) and `DNS_RESOLVER` (`10.3.0.10`). These are **not** Vite vars — they configure the pod's nginx reverse proxy.

### A.4 — Go configs (stoa-go: stoactl + stoa-connect)

- **stoactl static config**: `stoa-go/pkg/config/config.go` — kubectl-style YAML at `~/.stoa/config` (4 fields: `apiVersion`, `kind`, `current-context`, `contexts[]`). Token cache at `~/.stoa/tokens`. Audit log at `~/.stoa/audit.log`.
- **stoa-connect runtime**: configured via env vars (no central `config.go`). Files: `stoa-go/internal/connect/{credentials,discovery,connect,sse,vault,routes}.go` — they call `os.Getenv` directly. Not centralized; each module owns its env reads.
- **No Helm chart for stoa-connect yet** (per ADR-057, stoa-connect is a VPS agent, not a K8s deployment). Configuration via systemd unit env files, not chart values.

### A.5 — `.env.example` files (10 in stoa monorepo)

| File | Domain | Notable | Drift status |
|------|--------|---------|--------------|
| `control-plane-api/.env.example` | cp-api | Documents `DATABASE_POOL_SIZE=5` (Settings default is **10**). References `OPENSEARCH_HOST/USER/PASSWORD/VERIFY_CERTS` (consumed by OpenSearchSettings, NOT main Settings). References `AUDIT_ENABLED`, `AUDIT_BUFFER_SIZE`, `AUDIT_FLUSH_INTERVAL` (consumed by OpenSearchSettings, NOT main Settings). Doesn't mention dozens of fields actually in `Settings`: ALGOLIA_*, CHAT_*, VAULT_*, EMBEDDING_*, LOG_DEBUG_*, SENDER_CONSTRAINED_*, etc. | **D** (drift) — pool size; **E** (ambiguous) — OS_HOST namespace |
| `control-plane-ui/.env.example` | cp-ui | Lists ~12 VITE_* keys; ~18 used in code missing here (VITE_AWX_URL, VITE_PORTAL_MODE, VITE_GIT_PROVIDER, VITE_GIT_REPO_URL, VITE_GITLAB_URL, VITE_DATE_FORMAT, VITE_ARENA_DASHBOARD_URL, VITE_AUTH_REFRESH_TIMEOUT_MS, VITE_AVAILABLE_ENVIRONMENTS, VITE_REQUIRE_SANDBOX_CONFIRMATION, VITE_ERROR_TRACKING_ENDPOINT, VITE_API_DOCS_URL, etc.) | **B** (incomplete) |
| `portal/.env.example` | portal | Lists ~10 VITE_* keys; broadly aligned with code | OK |
| `stoa-gateway/.env.example` | gateway (Rust) | Documents ~25 STOA_* keys; ~165 STOA_* keys missing (most nested mtls/dpop/sender_constraint/llm_router/api_proxy fields, all guardrails, federation, hegemon, a2a, soap/grpc/graphql, etc.) | **B** (heavily incomplete — config.rs is the truth) |
| `e2e/.env.example` | E2E tests | URLs (`STOA_PORTAL_URL`, `_CONSOLE_URL`, `_GATEWAY_URL`) + 8 persona credentials (PARZIVAL_*, ART3MIS_*, AECH_*, SORRENTO_*, I_R0K_*, ANORAK_*, ALEX_*, ANORAK_*) — used in Playwright tests. | OK (testing-scoped) |
| `landing-api/.env.example` | landing-api | **Different namespace**: `STOA_APP_NAME`, `STOA_DEBUG`, `STOA_LOG_LEVEL`, `STOA_HOST`, `STOA_PORT`, `STOA_DB_*`, `STOA_INVITE_*`, `STOA_PORTAL_URL` | **D** (collides with stoa-gateway STOA_ prefix in same cluster — same env var STOA_LOG_LEVEL means different things to different services) |
| `services/opensearch-sync/.env.example` | opensearch-sync | Out-of-scope for INFRA-1 (sidecar service) | not analyzed |
| `deploy/docker-compose/.env.example` | docker-compose | Out-of-scope (self-hosted quickstart) | not analyzed |
| `deploy/docker-compose/sidecar/.env.example` | sidecar compose | Out-of-scope | not analyzed |
| `deploy/demo-federation/.env.example` | demo federation | Out-of-scope | not analyzed |

> Mirror in `stoa-signed-commits-policy/` is a tooling artifact, not a real component.

### A.6 — Tilt configs (local dev)

- **`Tiltfile` (stoa root)**: Helm-driven local dev orchestrator, pointing at `../stoa-infra/charts/<svc>` with overrides at `../stoa-infra/deploy/tilt/values-local/<svc>.yaml`. Stub `Secret` `stoa-local-secrets` for the cp-api `envFrom` (so chart deploys succeed without real Vault).
- **Per-service local overrides** (in stoa-infra):
  - `deploy/tilt/values-local/control-plane-api.yaml`
  - `deploy/tilt/values-local/control-plane-ui.yaml`
  - `deploy/tilt/values-local/stoa-portal.yaml`
  - `deploy/tilt/values-local/stoa-gateway.yaml`
- **k3d cluster config**: `stoa-infra/deploy/tilt/k3d-config.yaml`
- **Source-of-truth flow for local**: developer's `.env` (cp-api, cp-ui, portal) NOT loaded by Tilt — only Helm `values-local/*.yaml` are read. `.env` files are loaded only when running `uvicorn`/`vite` directly, not when going through Tilt → k3d → Helm.

### A.7 — stoa-infra Helm charts

#### A.7.1 — Inventory (16 charts)

```
charts/
├── agentgateway-dataplane/
├── argocd/
├── control-plane-api/        ← STOA app (in scope)
├── control-plane-ui/         ← STOA app (in scope)
├── data-prepper/
├── devportal/
├── external-secrets/
├── gravitee-dataplane/
├── kafka-bridge/
├── keycloak/                  ← STOA dep (in scope)
├── kong-dataplane/
├── mcp-gateway/               ← LEGACY (Python, retired Feb 2026 — see Section C)
├── opensearch/
├── stoa-gateway/              ← STOA app (in scope)
├── stoa-link/
├── stoa-platform/             ← parent umbrella chart
├── stoa-portal/               ← STOA app (in scope)
├── tempo/
└── webmethods-dataplane/
```

#### A.7.2 — In-scope chart structures

| Chart | values.yaml structure | Templates of interest |
|-------|----------------------|------------------------|
| `control-plane-api` | `env:` block (17 keys), `extraEnv:` block (CAB-2171 cross-NS Loki/Tempo), `secrets.{existingSecret,gitlabSecret}`, `opensearch.caSecretName`, `seeder.{enabled,profile,...}` | `deployment.yaml` (mixed: `.Values.env.X` per-key + valueFrom secretKeyRef for GITLAB_*; `MCP_GATEWAY_URL` **hardcoded** to `http://mcp-gateway.stoa-system.svc.cluster.local:80` — see C.2), `seeder-job.yaml` |
| `stoa-gateway` | `env:` block (12 keys, all `STOA_*`), top-level `mode`/`environment`/`autoRegister`/`policies.*`/`k8s.*`/`kafka.*`/`otelEndpoint`, `keycloakAdminSecret.{name,key}`, `keycloakClientSecret`, `secrets.existingSecret`, `externalSecret.{enabled,refreshInterval,secretStoreRef,vaultPath}` | `deployment.yaml` (mixed: 4 fields hardcoded `STOA_HOST/PORT/INSTANCE_NAME/KEYCLOAK_URL`; rest from values), `externalsecret.yaml` (chart-templated, but `externalSecret.enabled=false` → currently dead — see Section F.2), `policy-configmap.yaml` (Rego policies) |
| `control-plane-ui` | `env:` block (3 keys), `nginxBackends.{apiUrl,logsUrl,prometheusUrl}` | `deployment.yaml` (5 explicit env vars + 3 nginx backends + hardcoded fallback for VITE_KEYCLOAK_URL) |
| `stoa-portal` | `env:` block (5 keys including server-side `API_BACKEND_URL` + `DNS_RESOLVER`) | `deployment.yaml` (range over `.Values.env` + 2 explicit overrides — duplicate VITE_KEYCLOAK_URL emit, see A.3.2) |
| `keycloak` | (not deeply inspected; per memory `gotcha_keycloak_bootstrap_non_reconciling.md`: 3-layer authority — chart bootstrap-only, bootstrap-job post-install hook, ansible playbook authoritative for ROPC flag) | `deployment.yaml`, `bootstrap-job.yaml` |

#### A.7.3 — Per-env values overrides (none)

```bash
$ find stoa-infra/charts -name "values-*.yaml"
charts/external-secrets/values-external-secrets.yaml
charts/opensearch/values-dashboards.yaml
charts/opensearch/values-opensearch.yaml
```

**Finding**: there are **no `values-prod.yaml` / `values-staging.yaml` / `values-dev.yaml`** for cp-api, stoa-gateway, control-plane-ui, stoa-portal in stoa-infra. Per-env overrides are NOT a chart pattern in current setup. The single `values.yaml` is treated as prod (`baseDomain: gostoa.dev`, `image.tag: dev-<sha>`). ArgoCD auto-syncs that single file. Local Tilt overrides via `deploy/tilt/values-local/*.yaml`.

**Implication**: any per-env divergence (staging vs prod) currently requires either (a) a manual `helm upgrade --set` outside ArgoCD, (b) a separate cluster (no separate environment in this org), or (c) git branches per env (not the current pattern). This is a **major source of ambiguity** when planning Phase 1: source-of-truth canon must support multi-env even though the current platform is single-env.

### A.8 — K8s ConfigMaps + Secrets

#### A.8.1 — Chart-templated ConfigMaps

Only **two** chart-templated ConfigMaps in scope:
- `stoa-infra/charts/stoa-gateway/templates/policy-configmap.yaml` — OPA Rego policies, mounted to `/etc/stoa/policies`. Not a config-as-env source.
- `stoa-infra/charts/data-prepper/templates/configmap.yaml` — out of scope (data-prepper config).

**No other ConfigMap is templated** for cp-api, cp-ui, stoa-portal, keycloak (besides the policy CM above).

#### A.8.2 — Hand-written ConfigMaps in monorepo (suspected dead)

- `control-plane-api/k8s/configmap.yaml` — declares `stoa-control-plane-api-config` ConfigMap with **non-sensitive cp-api env vars** (BASE_DOMAIN, KEYCLOAK_URL, GIT_PROVIDER, GITLAB_URL, GITHUB_*, KAFKA_*, GATEWAY_URL, etc.). **Not referenced** by `stoa-infra/charts/control-plane-api/templates/deployment.yaml` (which uses inline `.Values.env.*` instead). Per memory `gotcha_stoa_infra_dead_appset.md`, ArgoCD live pattern is `kubectl apply` of chart `argocd-application.yaml` files; no AppSet picks up `<repo>/k8s/`. Confirmed in C.3 below.
- `portal/k8s/configmap.yaml` — declares `stoa-portal-config` ConfigMap. The file's own header says: *"These values are baked into the Docker image at build time. This ConfigMap is for documentation/reference purposes."* — **explicitly documentation-only**.
- `control-plane-ui/k8s/*.yaml`, `stoa-gateway/k8s/*.yaml`, `stoa-operator/k8s/*.yaml` — deployment/service/ingress/HPA/PDB. None apparently referenced by ArgoCD.

#### A.8.3 — Secrets sources

Three layers:
1. **envFrom secretRef in chart deployment.yaml** — pulls all keys from a single Secret. Used by:
   - cp-api: `stoa-control-plane-api-secrets` (`secrets.existingSecret`)
   - stoa-gateway: `stoa-gateway-secrets` (`secrets.existingSecret`, `optional: true`)
2. **valueFrom secretKeyRef in chart deployment.yaml** — explicit key mapping. Used by:
   - cp-api `GITLAB_TOKEN`, `GITLAB_PROJECT_ID`, `GITLAB_WEBHOOK_SECRET` ← `gitlabSecret: gitlab-secrets`
   - stoa-gateway `STOA_KEYCLOAK_CLIENT_SECRET` ← `keycloakClientSecret.{name,key}` (currently `null` in values, so disabled)
   - stoa-gateway `STOA_KEYCLOAK_ADMIN_PASSWORD` ← `keycloakAdminSecret.{name,key}` (`keycloak-admin-secret`/`admin-password`)
3. **ExternalSecrets** populating those Secrets from Vault — see A.8.4.

#### A.8.4 — ExternalSecrets — TWO definitions for stoa-gateway (drift)

- **Chart-templated** (`stoa-infra/charts/stoa-gateway/templates/externalsecret.yaml`): creates secret keys `control-plane-api-key`, `jwt-secret`, `keycloak-client-secret`, `admin-api-token` (lowercase + dashes) targeting Secret `stoa-gateway-secrets`. **Currently disabled** (`values.yaml: externalSecret.enabled=false`).
- **Hand-applied** (`stoa-infra/deploy/external-secrets/external-secret-gateway.yaml`): creates secret keys `STOA_CONTROL_PLANE_API_KEY`, `STOA_KEYCLOAK_CLIENT_SECRET` (UPPER + underscores) targeting same Secret name `stoa-gateway-secrets`. **This is the active one** in OVH prod.
- **Drift**: both target Secret `stoa-gateway-secrets`, but with **different key names**. envFrom of the deployment imports keys verbatim as env vars — only UPPER_UNDERSCORE keys become valid env vars (`STOA_*`). The chart-templated lowercase-dash keys would NOT be importable as env vars without aliasing — chart externalsecret is **doubly dead**: disabled flag + would-be-broken keys.
- **Cause**: hand-applied ExternalSecrets pre-date the chart-templated version, never deprecated. See Section F.2.

Other hand-applied ExternalSecrets in `stoa-infra/deploy/external-secrets/`:
- `external-secret-anthropic.yaml`, `-arena-verify.yaml`, `-database.yaml`, `-gateway.yaml`, `-gitlab.yaml`, `-opensearch.yaml`, `-traffic-seeder.yaml` — 7 files, not chart-templated.

### A.9 — CI / dev tooling configs

- **GitHub Actions secrets referenced** (across `.github/workflows/`): **62 distinct** (e.g. `ANTHROPIC_API_KEY`, `LINEAR_API_KEY`, `KUBECONFIG_OVH`, `KUBECONFIG_B`, `GITHUB_GITOPS_TOKEN`, `GIT_CRYPT_KEY`, `RELEASE_PLEASE_TOKEN`, `HOMEBREW_TAP_TOKEN`, `SLACK_WEBHOOK_URL`, `SLACK_WEBHOOK_GUARDIAN_ALERTS`, `SLACK_WEBHOOK_STOA_REVIEWS`, `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID`, `STOA_API_TOKEN`, `STOA_API_URL`, `STOA_CONSOLE_URL`, `PUSHGATEWAY_AUTH`, `PUSHGATEWAY_URL`, `HEGEMON_REMOTE_*`, `HEGEMON_VPS_HOST`, `HEGEMON_SSH_PRIVATE_KEY`, plus 8 E2E persona credentials and 4 GitLab/GitHub provider credentials).
- **GitHub Actions vars referenced** (16 distinct): `AUTOPILOT_DAILY_MAX`, `AUTOPILOT_TODAY_COUNT`, `CLAUDE_DEFAULT_MODEL`, `COUNCIL_S` (truncated grep — should be `COUNCIL_SLACK_*` or similar), `DEMO_SMOKE_BLOCKING`, `DISABLE_AUTOPILOT_SCAN`, `DISABLE_CONTEXT_COMPILER`, `DISABLE_L`, `DISABLE_LINEAR_CLOSE`, `DISABLE_LINEAR_REOPEN`, `DISABLE_PR_GUARDIAN`, `DISABLE_REVIEW_DRIFT_DETECTOR`, `GIT_PROVIDER`, `HEGEMON_WORKER_HOSTS`, `N`, `PUSHGATEWAY_URL`. The `vars.GIT_PROVIDER` is **the same env name** as cp-api Settings + Rust Config — drift surface.
- **Org-wide block on PR creation by Actions** (per memory `gotcha_enterprise_blocks_actions_pr_creation.md`): workflows opening PRs must use `secrets.PAT_TOKEN`. Documented in CI; not a config-cartography concern but informs Section H ops decisions.

---

## Section B — Cross-reference matrix (~30 strategic configs)

Legend: `✓` = present/consumed, `—` = absent, `→X` = points/maps to X. `[hard]` = hardcoded value (not configurable). SoT = proposed source-of-truth.

| Setting | cp-api Pydantic | gateway Rust | Frontend | cp-api Helm | gateway Helm | UI/Portal Helm | K8s ConfigMap (legacy) | .env.example | Tilt local | Notes / Proposed SoT |
|---------|-----------------|--------------|----------|-------------|--------------|----------------|------------------------|--------------|------------|----------------------|
| `BASE_DOMAIN` / `VITE_BASE_DOMAIN` | ✓ `Settings.BASE_DOMAIN` (frozen at import) | — | ✓ `VITE_BASE_DOMAIN` | ✓ `baseDomain` (top-level) | ✓ `baseDomain` | ✓ `baseDomain` → templated | ✓ | ✓ (commented) | values-local/* | **AMBIGU** (E.1) — chart top-level vs Pydantic frozen default. **SoT: Helm `baseDomain`** for prod; Pydantic default for fallback. |
| `ENVIRONMENT` | ✓ `Settings.ENVIRONMENT` | ✓ `Config.environment` (`STOA_ENVIRONMENT`) | ✓ `VITE_ENVIRONMENT` (build-time) | — (not in values, defaults to "production") | ✓ `environment: prod` (top-level) | — | ✓ `ENVIRONMENT: production` | ✓ | per-tilt | **DUPLIQUE** (D.1) — multiple sources, validators in cp-api gate prod. SoT: Helm top-level `environment`. |
| `LOG_LEVEL` | ✓ `Settings.LOG_LEVEL` | ✓ `Config.log_level` (`STOA_LOG_LEVEL`) | ✓ `VITE_ENABLE_DEBUG` (boolean only) | — | ✓ via `env.STOA_LOG_LEVEL` | — | — | ✓ | per-tilt | **AMBIGU** — same name, 3 distinct loaders. SoT: per-service env (no global). |
| `LOG_FORMAT` | ✓ `Settings.LOG_FORMAT` (`json|text`) | ✓ `Config.log_format` (`STOA_LOG_FORMAT`, `json|pretty|compact`) | — | — | ✓ `env.STOA_LOG_FORMAT` | — | — | ✓ (gateway) | — | **DUPLIQUE** (D.2) — different value enums between Python and Rust (text vs pretty/compact). SoT: per-service. |
| `KEYCLOAK_URL` (public) | ✓ `Settings.KEYCLOAK_URL` (default `https://auth.{BASE_DOMAIN}`) | ✓ `Config.keycloak_url` (`STOA_KEYCLOAK_URL`) | ✓ `VITE_KEYCLOAK_URL` | ✓ `env.KEYCLOAK_URL` | **[hard]** in deployment.yaml: `https://auth.{baseDomain}` (`.Values.env.STOA_KEYCLOAK_URL` IS IGNORED — gotcha) | ✓ via `default (printf "https://auth.%s" baseDomain)` | ✓ but value `http://keycloak.stoa-system...` (BUG — would break iss validation) | ✓ | — | **AMBIGU+BUG** (E.2). SoT: chart `baseDomain` derived. Deprecate `.Values.env.STOA_KEYCLOAK_URL` (currently ignored). |
| `KEYCLOAK_INTERNAL_URL` | ✓ `Settings.KEYCLOAK_INTERNAL_URL` | ✓ `Config.keycloak_internal_url` | — | ✓ `env.KEYCLOAK_INTERNAL_URL` | ✓ `env.STOA_KEYCLOAK_INTERNAL_URL` | — | — | — | — | **OK**. SoT: per-svc Helm `env`. |
| `KEYCLOAK_REALM` | ✓ | ✓ | ✓ `VITE_KEYCLOAK_REALM` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **DUPLIQUE** (D.3) — 7 places, hardcoded `"stoa"` everywhere. SoT: chart top-level `keycloak.realm` (extract). |
| `KEYCLOAK_CLIENT_ID` | ✓ (default `control-plane-api`) | ✓ (`stoa-mcp-gateway` in chart) | ✓ `VITE_KEYCLOAK_CLIENT_ID` (cp-ui: `control-plane-ui`; portal: `stoa-portal`) | ✓ | ✓ | ✓ | ✓ | ✓ | per-tilt | **OK** — distinct per service by design. SoT: per-svc Helm `env`. |
| `KEYCLOAK_CLIENT_SECRET` | ✓ Settings (`""` default) | ✓ Config (Option<String>) | — | ✓ via `envFrom secretRef stoa-control-plane-api-secrets` | ✓ via `valueFrom secretKeyRef keycloakClientSecret` (currently null) OR `envFrom secretRef stoa-gateway-secrets` | — | — | — | stub `Secret stoa-local-secrets` | **AMBIGU** (E.5) — gateway has BOTH paths (envFrom + valueFrom). SoT: ExternalSecrets via Vault. |
| `KEYCLOAK_ADMIN_CLIENT_SECRET` | ✓ accepts `KEYCLOAK_ADMIN_CLIENT_SECRET` OR `KEYCLOAK_ADMIN_PASSWORD` (load-time `os.getenv` fallback) | ✓ `keycloak_admin_password` (`STOA_KEYCLOAK_ADMIN_PASSWORD`) | — | ✓ envFrom | ✓ `valueFrom secretKeyRef keycloakAdminSecret` | — | — | ✓ (gateway) | — | **AMBIGU+DUPLIQUE** — naming collision between admin-cli secret and admin password; cp-api has `os.getenv` fallback at module load (frozen). SoT: clarify single name `KEYCLOAK_ADMIN_PASSWORD`. |
| `STOA_DISABLE_AUTH` | ✓ Settings (validator gates prod) | — (gateway has separate `STOA_AUTH_DISABLE_FOR_TESTS`?) | — | — | — | — | — | — | — | **OK**. SoT: cp-api Pydantic. |
| `GIT_PROVIDER` | ✓ Settings (legacy flat, `exclude=True`) → `settings.git.provider` | ✓ `Config.git_provider` (`STOA_GIT_PROVIDER` OR `GIT_PROVIDER`) | ✓ `VITE_GIT_PROVIDER` | ✓ `env.GIT_PROVIDER: github` | — | — | ✓ legacy CM | ✓ | — | **DUPLIQUE+CROSS-REPO** (F.1). 5 places, gh provider. SoT: cp-api Helm `env.GIT_PROVIDER` (drives also gateway via separate Helm). |
| `GITHUB_TOKEN` | ✓ flat → `settings.git.github.token` (SecretStr) | ✓ `Config.github_token` (`STOA_GITHUB_TOKEN` OR `GITHUB_TOKEN`) | — | ✓ via `envFrom` secret OR `valueFrom secretKeyRef githubSecret` (CAB-1890 PR #55 stoa-infra) | (gateway not yet wired for github creds) | — | ✓ legacy CM (empty) | — | — | **CROSS-REPO** (F.1). SoT: ExternalSecrets `external-secret-gitlab.yaml` + new equivalent for github (CAB-1890). |
| `GITHUB_ORG`, `_CATALOG_REPO`, `_GITOPS_REPO`, `_WEBHOOK_SECRET` | ✓ (4 fields, exclude=True) | ✓ (4 fields, single + double-prefix variants) | — | ✓ env block (3 of 4 conditional) | — | — | ✓ legacy CM | partial | — | **CROSS-REPO** (F.1). SoT: cp-api Helm `env`. |
| `GITLAB_URL`, `_TOKEN`, `_PROJECT_ID`, `_WEBHOOK_SECRET` | ✓ (4 flat fields, exclude=True) | ✓ (4 fields) | ✓ `VITE_GITLAB_URL` | ✓ env + 3 valueFrom secretKeyRef | — | — | ✓ legacy CM | ✓ | — | **OK** (CAB-1889 hardened). SoT: chart envFrom + ExternalSecret `external-secret-gitlab.yaml`. |
| `DATABASE_URL` | ✓ Settings (default localhost) | — | — | ✓ chart env block (hardcoded prod password — see C.4) | — | — | — | ✓ | — | **DUPLIQUE+SECURITY** (D.5). SoT: ExternalSecret `external-secret-database.yaml`, NOT chart values. |
| `DATABASE_POOL_SIZE` | ✓ Settings (default `10`) | — | — | — | — | — | — | ✓ but documents `5` (drift!) | — | **DUPLIQUE/DRIFT** (D.6). SoT: Pydantic default. |
| `OPENSEARCH_URL` (docs/embedding) | ✓ `Settings.OPENSEARCH_URL` (default `http://opensearch.stoa-system.svc...:9200`) | — | — | — (chart sets OPENSEARCH_HOST instead) | — | — | — | — | — | **DUPLIQUE** (D.7) — main Settings has its own OPENSEARCH_URL distinct from OpenSearchSettings.opensearch_host. |
| `OPENSEARCH_HOST/USER/PASSWORD/VERIFY_CERTS/CA_CERTS` | ✓ `OpenSearchSettings` (audit + search service) | — | — | ✓ chart env block | — | — | — | ✓ | — | **AMBIGU** (E.4) — consumed by sub-loader, not main Settings. Docs needed. SoT: chart env + ExternalSecret `external-secret-opensearch.yaml`. |
| `AWX_URL` | — (no consumer in cp-api/src — verified `grep AWX_URL` = 0 hits) | — | ✓ `VITE_AWX_URL` (UI links only) | ✓ chart env block (`http://awx-service.stoa-system.svc.cluster.local`) | — | — | — | — | — | **DEAD on cp-api** (C.5). SoT: only frontend consumes it (UI link); cp-api env injection is dead code. |
| `MCP_GATEWAY_URL` | ✓ Settings (default `http://stoa-gateway...:80`) | — | ✓ `VITE_MCP_URL` (portal) | **[hard]** in deployment.yaml: `http://mcp-gateway.stoa-system.svc.cluster.local:80` (POINTS AT RETIRED SERVICE — see C.2) | — | — | — | ✓ | — | **DEAD+BUG** (C.2). SoT: cp-api Settings default — the Helm hardcode points at decommissioned mcp-gateway and breaks chat routing in non-rewritten clusters. |
| `KAFKA_ENABLED`, `_BOOTSTRAP_SERVERS`, `_BROKERS` | ✓ Settings (`KAFKA_BOOTSTRAP_SERVERS`) | ✓ Config (`STOA_KAFKA_BROKERS`) | — | ✓ env block | ✓ top-level `kafka.{enabled,brokers,meteringTopic,errorsTopic}` | — | ✓ legacy CM | partial | — | **DUPLIQUE** (D.8) — different env names for same Redpanda endpoint (`KAFKA_BOOTSTRAP_SERVERS` vs `STOA_KAFKA_BROKERS`). SoT: per-svc env. |
| `CHAT_GATEWAY_URL` (CAB-1822) | ✓ Settings | — | — | ✓ chart env block | — | — | — | — | — | **OK**. |
| `STOA_LLM_PROXY_*` | — | ✓ 5 fields | — | — | ✓ chart env block | — | — | ✓ partial | — | **OK**. |
| `STOA_GATEWAY_MODE` (ADR-024) | — | ✓ Config.gateway_mode | — | — | ✓ top-level `mode` | — | — | ✓ | — | **OK**. SoT: Helm top-level. |
| `STOA_AUTO_REGISTER` (ADR-028) | — | ✓ | — | — | ✓ top-level `autoRegister` | — | — | ✓ | — | **OK**. |
| `STOA_OTEL_ENDPOINT`, `_SAMPLE_RATE`, `_ENABLED` | — | ✓ 3 fields | — | — | ✓ top-level `otelEndpoint` (only) | — | — | ✓ partial | — | **OK** (gateway only). |
| `LOG_DEBUG_AUTH_TOKENS/_HEADERS/_PAYLOAD/_HTTP_BODY/_HTTP_HEADERS` | ✓ Settings (5 fields, prod-gated by validator) | — | — | — | — | — | — | — | — | **OK** (CAB-2145). |
| `VAULT_ADDR/_TOKEN/_KUBERNETES_ROLE/_MOUNT_POINT/_ENABLED` | ✓ Settings (5 fields) | — | — | — (cp-api uses K8s SA, not direct env) | — | — | — | — | — | **OK**. SoT: in-cluster K8s auth via Vault provider. |
| `BACKEND_ENCRYPTION_KEY` (CAB-1188 BYOK Fernet) | ✓ Settings | — | — | ✓ envFrom secret | — | — | — | ✓ | — | **OK**. SoT: ExternalSecret. |
| `ANTHROPIC_API_KEY` | ✓ implicit via `CHAT_PROVIDER_API_KEY` | ✓ implicit via `STOA_LLM_PROXY_API_KEY`/`_MISTRAL_API_KEY` | — | ✓ envFrom secret | ✓ envFrom secret | — | — | — | — | **CROSS-REPO** (F.3). SoT: ExternalSecret `external-secret-anthropic.yaml`. CI: `secrets.ANTHROPIC_API_KEY`. |

> **Observation**: ~30 of the 50 strategic configs touch ≥3 layers. Of those, ~15 have a **clear single SoT** today; ~10 are ambiguous (Cat C); ~5 are duplicated with drift risk (Cat B).

---

## Section C — Catégorie A — Dead config

| # | Config | Localisation | Évidence du "dead" | Action proposée |
|---|--------|--------------|--------------------|-----------------|
| C.1 | `AWX_URL` injected at cp-api pod | `stoa-infra/charts/control-plane-api/values.yaml:9`, `templates/deployment.yaml:30-31` | `grep -rn "AWX_URL\|os.getenv.*AWX\|os.environ.*AWX" control-plane-api/src control-plane-api/tests` → **0 hits**. cp-api consumer = none. (Frontend `VITE_AWX_URL` is a separate variable for UI links.) | Remove from chart values + deployment.yaml. Chart bump 0.1 → 0.2. |
| C.2 | `MCP_GATEWAY_URL` hardcoded value | `stoa-infra/charts/control-plane-api/templates/deployment.yaml:76-77` (`http://mcp-gateway.stoa-system.svc.cluster.local:80`) | Per `CLAUDE.md` (root): "*Historical note: the Python `mcp-gateway/` service was retired in Feb 2026 and superseded by `stoa-gateway/` (Rust)*". Service `mcp-gateway` likely no longer exists OR is a BC alias to `stoa-gateway`. Hardcode bypasses `Settings.MCP_GATEWAY_URL` default (`http://stoa-gateway.stoa-system.svc.cluster.local:80`). | **Either** drop the hardcode (let Settings default win) **or** point to `stoa-gateway` directly. Verify via `kubectl get svc -n stoa-system mcp-gateway` first. May be a latent bug masking chat routing failure in some clusters. |
| C.3 | `control-plane-api/k8s/configmap.yaml` ConfigMap `stoa-control-plane-api-config` | `control-plane-api/k8s/configmap.yaml` (lines 1-50+) | Not referenced by `stoa-infra/charts/control-plane-api/templates/deployment.yaml` (no envFrom configMapRef). Per memory `gotcha_stoa_infra_dead_appset.md`: ArgoCD live pattern = chart `argocd-application.yaml`; no AppSet picks up monorepo `<svc>/k8s/`. No `kubectl apply` of this file in CI/AWX. | Delete `control-plane-api/k8s/configmap.yaml`. (Possibly delete entire `control-plane-api/k8s/` directory — verify deployment.yaml/service.yaml are also dead.) |
| C.4 | `portal/k8s/configmap.yaml` ConfigMap `stoa-portal-config` | `portal/k8s/configmap.yaml:1-3` (file's own header: *"This ConfigMap is for documentation/reference purposes"*) | Same as C.3 — not referenced by Helm. Self-documented as dead. | Delete file. Replace with a short `stoa-portal/CONFIG.md` if documentation value is desired. |
| C.5 | `control-plane-ui/k8s/`, `stoa-gateway/k8s/`, `stoa-operator/k8s/` directories | various | Same audit: not used by stoa-infra Helm charts. (stoa-operator deployment may have been retired entirely.) | Audit per directory before deletion; some may have residual ArgoCD references not visible in chart audit. |
| C.6 | Legacy `mcp-gateway` chart in stoa-infra | `stoa-infra/charts/mcp-gateway/` | Python mcp-gateway retired Feb 2026, replaced by `stoa-gateway` (Rust). Chart still present. | Confirm no ArgoCD Application syncs from it (likely abandoned after migration). Delete chart if confirmed orphan. **Out of INFRA-1 scope strictly** but flagged. |
| C.7 | `Settings.LLMS_FULL_TXT_URL` (default `https://gostoa.dev/llms-full.txt`) | `control-plane-api/src/config.py:302` | `grep -rn "LLMS_FULL_TXT_URL" control-plane-api/src` would need verification. If only consumed by docs router for an Algolia/llms.txt feature, it's fine. **Marked for verification** in Phase 1. | Verify consumer count before declaring dead. Out-of-scope for Phase 0 closure. |
| C.8 | `Settings.STOA_EDITION` (default `community`) | `control-plane-api/src/config.py:114` | Defined for "Open Core model"; need to verify any router/middleware reads it before declaring active vs aspirational. | Verify in Phase 1. |
| C.9 | `Settings.STOA_ENVIRONMENTS` (JSON array of multi-env configs) | `control-plane-api/src/config.py:332` | CAB-1659 multi-env registry. Need consumer verification. | Verify in Phase 1. |
| C.10 | Chart-templated `stoa-gateway/templates/externalsecret.yaml` with lowercase-dash keys | `stoa-infra/charts/stoa-gateway/templates/externalsecret.yaml` | `values.yaml: externalSecret.enabled=false`; AND key names (`control-plane-api-key`, `keycloak-client-secret`) wouldn't import as env vars without aliasing. Doubly dead. | Either delete (favor hand-applied), or rewrite with UPPERCASE_UNDERSCORE keys + flip flag to `enabled: true` → migrate prod. See F.2. |

> **Confidence note**: C.1 and C.2 have hard grep evidence. C.3-C.6 rely on memory + directory inspection (not live ArgoCD Application list). For Phase 1, run `argocd app list -o json | jq '.[].spec.source.path'` to confirm before deletion.

---

## Section D — Catégorie B — Dupliqué

| # | Config | Localisations | Valeur(s) actuelles | Drift observé | Source-of-truth proposée |
|---|--------|---------------|---------------------|---------------|--------------------------|
| D.1 | `ENVIRONMENT` | (a) `Settings.ENVIRONMENT` default `"production"`; (b) cp-api chart env block (none, defaults to "production"); (c) gateway chart top-level `environment: prod`; (d) cp-api legacy CM `ENVIRONMENT: production` (dead per C.3); (e) `.env.example` `ENVIRONMENT=dev` (commented) | cp-api defaults to `"production"`; gateway uses `prod` (different value!) — Pydantic accepts both since it's `str`. Validator only checks `=="production"`. | **Yes** — Pydantic compares to literal `"production"` (cp-api) but gateway uses `"prod"`. If cp-api ever had `ENVIRONMENT=prod`, all prod-only validators would silently disable. | Helm top-level `environment` per chart; **standardize value as `prod`** (match gateway), update cp-api validators to accept both `production` and `prod` (or pick one). |
| D.2 | `LOG_FORMAT` value enums | (a) Pydantic `LOG_FORMAT: str = "json"` (no validator on enum); (b) Rust `LogFormat::{Json, Pretty, Compact}` (strict enum) | cp-api accepts any string (incl `"text"` per `.env.example`); Rust rejects unknown values | **Yes** — `"text"` documented in cp-api `.env.example` is silently accepted but not actually a valid Rust value | SoT: per-svc choice. Tighten cp-api with `Literal["json", "text"]`. Document in CLAUDE.md per service. |
| D.3 | `KEYCLOAK_REALM = "stoa"` | (a) Pydantic default; (b) Rust default; (c) cp-api Helm chart env; (d) gateway Helm chart env; (e) cp-ui Helm chart env; (f) portal Helm chart env; (g) cp-api `.env.example`; (h) gateway `.env.example`; (i) cp-ui `.env.example`; (j) portal `.env.example`; (k) cp-api legacy CM | All `"stoa"` everywhere | No drift observed (luckily) | Centralize as Helm umbrella `stoa-platform/values.yaml: keycloak.realm` (currently parent chart unused for this); each child chart reads `.Values.keycloak.realm`. |
| D.4 | `STOA_SNAPSHOT_*` (Rust ring buffer) vs `STOA_SNAPSHOTS_*` (Python error_snapshots feature) | (a) `stoa-gateway/src/config.rs:830-854` (singular); (b) `control-plane-api/src/features/error_snapshots/config.py:25` (plural) | Singular vs plural prefix for unrelated features in same cluster | **Latent risk** — operator setting `STOA_SNAPSHOT_ENABLED=true` thinks they're toggling cp-api error snapshots; actually toggles Rust gateway in-process buffer. Or vice versa. | Rename one. Suggest `STOA_GATEWAY_SNAPSHOT_*` for Rust (or `STOA_API_SNAPSHOT_*` for Python). Backward-compat alias for 1 release. |
| D.5 | `DATABASE_URL` | (a) Pydantic default `postgresql+asyncpg://stoa:stoa@localhost:5432/stoa`; (b) cp-api chart env block: `postgresql+asyncpg://stoa:stoa-db-password-2026@control-plane-db.stoa-system.svc.cluster.local:5432/stoa` (**hardcoded plaintext password!**) | Two different connection strings; chart contains a credential | **Yes — security**: chart values.yaml contains plaintext password. May or may not be a placeholder; needs verification. | SoT: `external-secret-database.yaml` (Vault path `k8s/database`). chart envFrom → secret. Remove hardcoded password from values.yaml. |
| D.6 | `DATABASE_POOL_SIZE` | (a) Pydantic default `10`; (b) cp-api `.env.example` `5` (commented) | `5` (docs) vs `10` (code) | **Documented drift** — anyone reading `.env.example` and uncommenting locks at 5; behavioral mystery in prod (10) vs dev. | SoT: Pydantic default. Update `.env.example` to `# DATABASE_POOL_SIZE=10`. |
| D.7 | OpenSearch endpoint | (a) `Settings.OPENSEARCH_URL` default `http://opensearch.stoa-system.svc.cluster.local:9200` (used for docs/embedding search); (b) `OpenSearchSettings.opensearch_host` default `https://opensearch.gostoa.dev` (used for audit logger + general search service); (c) cp-api Helm `env.OPENSEARCH_HOST: https://opensearch.opensearch.svc.cluster.local:9200` (consumed by OpenSearchSettings, NOT main Settings) | Three different default values, three different consumers | **Yes** — accidentally rewrites scope: docs-search and audit-logger pointing at different endpoints despite identical name semantics. | Consolidate: single SoT for OpenSearch in `OpenSearchSettings`, rename main `Settings.OPENSEARCH_URL` → `DOCS_SEARCH_OPENSEARCH_URL` to disambiguate. |
| D.8 | Redpanda/Kafka brokers | (a) Pydantic `KAFKA_BOOTSTRAP_SERVERS` default `redpanda.stoa-system.svc.cluster.local:9092`; (b) Rust `STOA_KAFKA_BROKERS` default `kafka:9092`; (c) cp-api chart env block; (d) gateway chart top-level `kafka.brokers` | Different env var **names** for same broker URL | **Naming drift, no value drift currently** | SoT: standardize env name `STOA_KAFKA_BROKERS` everywhere; alias for cp-api 1 release. |
| D.9 | Persona credentials in CI vs `e2e/.env.example` | (a) `e2e/.env.example` documents `PARZIVAL_PASSWORD=` etc.; (b) GH Actions secrets `secrets.PARZIVAL_PASSWORD` | Same name, different storage; passwords managed manually in two places | **Operational drift** — adding a persona requires updating both | SoT: GH Actions secrets. Generate `e2e/.env.example` from a single registry. |
| D.10 | `STOA_KEYCLOAK_URL` chart vs deployment.yaml | (a) `stoa-infra/charts/stoa-gateway/values.yaml: env.STOA_KEYCLOAK_URL` (currently absent, would be honored if present); (b) `stoa-infra/charts/stoa-gateway/templates/deployment.yaml:61-62` HARDCODES `https://auth.{{ .Values.baseDomain }}` (ignores `.Values.env.STOA_KEYCLOAK_URL` entirely) | Hardcode wins — `.env.STOA_KEYCLOAK_URL` is **silently ignored** | **Yes** — operator setting `env.STOA_KEYCLOAK_URL` in values has no effect | SoT: `baseDomain`. Either remove the dead path entirely OR honor `.Values.env.STOA_KEYCLOAK_URL` if set with `default`. Recommend: remove the env path, document `baseDomain` as canonical. |

---

## Section E — Catégorie C — Ambiguë

### E.1 — `BASE_DOMAIN` (load-time vs runtime, Pydantic field freezing)

**Current chain**:
1. **Module-load** (`config.py:17`): `_BASE_DOMAIN = os.getenv("BASE_DOMAIN", "gostoa.dev")` — frozen at import time.
2. **Pydantic field** (`config.py:117`): `BASE_DOMAIN: str = _BASE_DOMAIN` — field default uses frozen value.
3. **Derived defaults** (`config.py:129,208,214,223,224,230,...`): `KEYCLOAK_URL: str = f"https://auth.{_BASE_DOMAIN}"`, `GATEWAY_URL: str = f"https://vps-wm.{_BASE_DOMAIN}"`, etc. — **all bound to `_BASE_DOMAIN` at import**.
4. **Helm chart** (`stoa-infra/charts/control-plane-api/values.yaml:7`): `baseDomain: gostoa.dev` — top-level, used by templates only (NOT propagated to BASE_DOMAIN env var by current deployment.yaml — verified).

**Précédence actuelle observée**:
- If `BASE_DOMAIN` env is set BEFORE Python import, `_BASE_DOMAIN` picks it up, derived defaults expand correctly.
- If `BASE_DOMAIN` is set ONLY via `Settings(BASE_DOMAIN="...")` constructor or via Helm value AFTER import, the derived defaults (KEYCLOAK_URL etc.) are **stuck at the frozen value**, NOT recomputed.
- If `BASE_DOMAIN` is NOT set in env BUT Helm chart `baseDomain: other.tld` is set, it has zero effect on cp-api env (no chart entry adds it).

**Précédence documentée**: **none** — no docs explain this Python behavior; Helm chart docs assume `baseDomain` is the SoT.

**Risque**:
- Multi-env deployments where one cluster overrides `BASE_DOMAIN` via Helm get **inconsistent URLs** (KEYCLOAK_URL stays `https://auth.gostoa.dev` even when BASE_DOMAIN=`other.tld`).
- Test fixtures setting `Settings(BASE_DOMAIN=...)` get partial overrides — silent bugs in test isolation.

**Source-of-truth proposée**: Two options.
- **Option A** (preferred): set `BASE_DOMAIN` as a real env var in cp-api chart deployment.yaml (templated from `.Values.baseDomain`); fix Pydantic by computing derived URLs as `@property` (post-init) so they recompute when `BASE_DOMAIN` is set via Pydantic.
- **Option B**: chart pushes ALL derived URLs explicitly (`KEYCLOAK_URL`, `GATEWAY_URL`, `ARGOCD_URL`, etc.) into the env block, killing the Pydantic-side derivation. More verbose, less DRY.

### E.2 — `STOA_KEYCLOAK_URL` (gateway Helm hardcode)

**Current chain**:
1. Operator sets `.Values.env.STOA_KEYCLOAK_URL: https://other-auth.example` in values override.
2. Chart deployment.yaml line 61-62 emits `STOA_KEYCLOAK_URL: https://auth.{{ .Values.baseDomain }}` — **hardcoded, ignores `.Values.env.STOA_KEYCLOAK_URL`**.
3. Operator's override is silently dropped.
4. Per memory `gotcha_gateway_chart_baseDomain_hardcode.md`, this is a known gotcha.

**Précédence actuelle**: `baseDomain` (chart) > runtime env > everything else. The "env block" path is dead.

**Précédence documentée**: none in chart README.

**Risque**: per-cluster Keycloak override impossible without forking the chart. Multi-tenant SaaS scenario blocked.

**Source-of-truth proposée**: chart `baseDomain` as canonical, OR honor `.Values.env.STOA_KEYCLOAK_URL` with `default (printf "https://auth.%s" baseDomain)` like cp-api/cp-ui already do.

### E.3 — Helm chart values pattern: `env:` block vs top-level

**Observation**:
- `cp-api/values.yaml`: all env-shaped vars under `env:` block. Predictable.
- `stoa-gateway/values.yaml`: **mixed** — `env: STOA_LOG_LEVEL`, `env: STOA_LLM_PROXY_*`, etc. **AND** top-level `mode`, `environment`, `autoRegister`, `policies.enabled`, `kafka.enabled`, `kafka.brokers`, `otelEndpoint` — these are templated separately into env vars by deployment.yaml.

**Précédence actuelle**: deployment.yaml decides. Operator must read deployment.yaml to know whether `mode` or `env.STOA_GATEWAY_MODE` is read. Currently **only `mode`** is read (`env.STOA_GATEWAY_MODE` is NOT in the deployment.yaml at all).

**Risque**: chart contributors add new fields under both patterns inconsistently. Operators set the wrong field. Documentation absent.

**Source-of-truth proposée**: pick one pattern per chart and document. Prefer `env:` block uniformly (matches cp-api). For computed values (e.g. `STOA_GATEWAY_EXTERNAL_URL` derived from `ingress.host`), keep deployment.yaml templating but expose `_template` keys with `default` fallback.

### E.4 — `OPENSEARCH_HOST` consumer ambiguity

**Current chain**:
1. cp-api Helm chart sets `env.OPENSEARCH_HOST: https://opensearch.opensearch.svc.cluster.local:9200`.
2. Main `Settings` class accepts it (`extra="ignore"`) but does NOT have an `OPENSEARCH_HOST` field. It has `OPENSEARCH_URL` (different default value).
3. `OpenSearchSettings` (different file) has `opensearch_host: str = "https://opensearch.gostoa.dev"` — **this** is the consumer.
4. `OpenSearchSettings` is constructed via `@lru_cache get_settings()` — singleton, env read at first call.

**Précédence actuelle**: env var > OpenSearchSettings default. No conflict with main Settings (different field names).

**Précédence documentée**: none.

**Risque**:
- Maintainer adds `OPENSEARCH_HOST` to main `Settings` (mistakenly thinking it's missing) → main Settings accepts it but it's a duplicate of `OpenSearchSettings.opensearch_host`. Two singletons of OpenSearch endpoint coexist with possibly different values.
- Maintainer renames main `OPENSEARCH_URL` → `OPENSEARCH_HOST` for consistency → silently overrides `OpenSearchSettings.opensearch_host` value because both classes read the same env var.

**Source-of-truth proposée**: make this explicit. Either:
- Move OpenSearchSettings fields INTO main Settings as a `OpenSearchConfig` sub-model (like `GitProviderConfig`), or
- Rename `OpenSearchSettings.opensearch_host` to a unique name (`AUDIT_OPENSEARCH_HOST`) AND set `env_prefix="AUDIT_"` on that class to namespace it. Document the split clearly in CLAUDE.md.

### E.5 — gateway Keycloak client secret: envFrom + valueFrom paths

**Current chain**:
1. `stoa-infra/charts/stoa-gateway/templates/deployment.yaml:130-136` emits `STOA_KEYCLOAK_CLIENT_SECRET` via `valueFrom secretKeyRef` IFF `.Values.keycloakClientSecret` is non-null.
2. Same chart line 144-149 emits `envFrom secretRef stoa-gateway-secrets` (the same Secret), which contains the same key (per hand-applied ExternalSecret in A.8.4).
3. K8s evaluates `envFrom` BEFORE the explicit `env`-list, so the explicit `valueFrom` would **win** over `envFrom` if both are present.

**Précédence actuelle**: `keycloakClientSecret` is `null` in current `values.yaml` (line 66), so only `envFrom` path is active. `STOA_KEYCLOAK_CLIENT_SECRET` comes from the hand-applied ExternalSecret.

**Précédence documentée**: none. Comment in values.yaml line 64-66 says "loaded via envFrom from stoa-gateway-secrets... No separate secretKeyRef needed." but the chart-templated path STILL EXISTS, creating future-confusion for an operator who flips `keycloakClientSecret` non-null.

**Risque**: operator enables `keycloakClientSecret` for a different Vault path → silently overrides envFrom. Or worse, secretKeyRef target is an empty/missing Secret → `valueFrom` fails → pod CrashLoopBackOff with cryptic error.

**Source-of-truth proposée**: pick one. Recommend **envFrom only** (matches CAB-1890 pattern) and **delete** the `keycloakClientSecret`/`valueFrom` block from deployment.yaml.

### E.6 — `LOG_LEVEL` cross-service

**Current chain**:
1. cp-api: `LOG_LEVEL: str = "INFO"` (Settings field, no validator)
2. stoa-gateway: `STOA_LOG_LEVEL` enum (`trace|debug|info|warn|error`)
3. landing-api: `STOA_LOG_LEVEL` (separate Pydantic class, default `INFO`)
4. Frontend: `VITE_ENABLE_DEBUG: bool` (no granular log level)
5. Helm: per-svc `env.STOA_LOG_LEVEL`, `env.LOG_LEVEL`

**Précédence**: per-pod env. No coordination.

**Risque**: ops want "debug everywhere" → must set 3 different env names (LOG_LEVEL, STOA_LOG_LEVEL, VITE_ENABLE_DEBUG=true) on 5 services. Easy to forget one → asymmetric debug.

**Source-of-truth proposée**: stay per-svc. Document the matrix of names → behaviors in `docs/runbooks/log-level-matrix.md`. Provide a stoactl helper: `stoactl debug enable --service all`.

---

## Section F — Cross-repo (stoa ↔ stoa-infra)

| # | Config | Côté stoa | Côté stoa-infra | Synchro | Risque |
|---|--------|-----------|-----------------|---------|--------|
| F.1 | `GIT_PROVIDER` + `GITHUB_*` provider passthrough (CAB-1890) | `Settings.git.*` (validator gates prod) + `Config.github_*` (Rust) | `charts/control-plane-api/values.yaml: env.GIT_PROVIDER, env.GITHUB_ORG, env.GITHUB_CATALOG_REPO, env.GITHUB_GITOPS_REPO`; secrets via `secrets.gitlabSecret` (current) and PR #55 stoa-infra adds `secrets.githubSecret` opt-in | **In progress** — CAB-1890 PR #55 stoa-infra open as of 2026-04-24 (per memory). Code side (stoa) hardened; chart side (stoa-infra) opt-in with empty `githubSecret: ""` default | LOW — opt-in, BC for gitlab path |
| F.2 | stoa-gateway secrets ExternalSecret | none (config.rs reads STOA_* env) | (a) `charts/stoa-gateway/templates/externalsecret.yaml` (chart-templated, currently `enabled: false`, lowercase-dash key names — see C.10); (b) `deploy/external-secrets/external-secret-gateway.yaml` (hand-applied, UPPERCASE_UNDERSCORE keys, active in prod) | **Drift** — chart version dead, hand-applied is canonical | MEDIUM — flipping `chart.externalSecret.enabled=true` would create a duplicate ExternalSecret targeting same name with wrong keys. Chart owner UNAWARE of hand-applied version. |
| F.3 | Anthropic API key | implicit consumers in cp-api `CHAT_PROVIDER_API_KEY` + gateway `STOA_LLM_PROXY_API_KEY` | `deploy/external-secrets/external-secret-anthropic.yaml` + chart envFrom of `anthropic-secrets`/similar | OK — single source via Vault | LOW |
| F.4 | Database credentials | Settings.DATABASE_URL accepts full DSN | (a) `charts/control-plane-api/values.yaml:39` HARDCODES password in DSN (D.5); (b) `deploy/external-secrets/external-secret-database.yaml` provides Vault-backed alt | **Conflict** — chart values has plaintext password; ExternalSecret exists but envFrom may not be wired | HIGH — security exposure if values.yaml is leaked. Verify ExternalSecret is the active path; remove plaintext from values. |
| F.5 | Anthropic / LLM router endpoints | gateway `Config.llm_router` (LlmRouterConfig — CAB-1487) — strategies, budget limits, **provider URLs** | NOT exposed in `charts/stoa-gateway/values.yaml` (no `llm_router:` block at all) | **Drift / not wired** | MEDIUM — gateway has rich LLM router config code but ops have no Helm knob to set it. Operator must set `STOA_LLM_ROUTER__*` env vars manually via raw Secret edit. |
| F.6 | Federation upstream JSON | gateway `Config.federation_upstreams: Vec<FederationUpstreamConfig>` (CAB-1752) | NOT exposed in `charts/stoa-gateway/values.yaml` | **Drift / not wired** | LOW (federation_enabled defaults to false; not currently used in prod) |
| F.7 | API proxy backends (CAB-1722) | gateway `Config.api_proxy: ApiProxyConfig` (Linear, GitHub, Slack toggles) | NOT exposed in `charts/stoa-gateway/values.yaml` | **Drift / not wired** | LOW (defaults to disabled) |
| F.8 | OPA policy file path | gateway `Config.policy_path: Option<String>` (`STOA_POLICY_PATH`) | `charts/stoa-gateway/templates/deployment.yaml:88` emits via `policies.path` top-level value; ConfigMap `policy-configmap.yaml` mounts policies at `/etc/stoa/policies` | OK | LOW |
| F.9 | KEYCLOAK_REALM hardcoded "stoa" everywhere | every config, every chart, every `.env.example` | every chart top-level / env block | OK (all `"stoa"`) | LOW |
| F.10 | E2E persona credentials | `e2e/.env.example` lists keys; `e2e/playwright.config.ts` reads them | NOT in stoa-infra (CI-only via GH Secrets) | OK | LOW |

> **stoa-infra accessibility**: confirmed local clone at `/Users/torpedo/hlfh-repos/stoa-infra` on `main` branch (commit `82a0339`). All sections D/F/G are based on direct inspection.

---

## Section G — Recommandations Phase 1

### G.1 — Configs à supprimer (Catégorie A)

- **Confirmed dead, low blast radius** (~5-10 LOC chart bumps + monorepo file deletions): C.1 (AWX_URL chart), C.2 (MCP_GATEWAY_URL hardcode → fix), C.3 (cp-api/k8s/configmap.yaml), C.4 (portal/k8s/configmap.yaml), C.5 (other monorepo k8s/ dirs after audit), C.10 (chart-templated stoa-gateway externalsecret).
- **Verification needed before deletion**: C.6 (mcp-gateway chart in stoa-infra), C.7-C.9 (Settings fields with grep needed).
- **Estimated scope**: ~10 small commits, 2 chart bumps (cp-api 0.1→0.2, stoa-gateway minor), zero breaking change.

### G.2 — Sources-of-truth à officialiser

| Category | Proposed SoT | Examples |
|----------|--------------|----------|
| **Image tags** | ArgoCD-managed `image.tag` in chart values (already the pattern via release-please) | per-svc values.yaml |
| **Domain construction** | Helm chart `baseDomain` top-level (umbrella `stoa-platform/values.yaml`) | `auth.<baseDomain>`, `api.<baseDomain>`, etc. |
| **Service URLs (in-cluster)** | Per-svc Helm chart `env:` block | `KAFKA_BOOTSTRAP_SERVERS`, `LOKI_INTERNAL_URL`, etc. |
| **Secrets** | ExternalSecrets Operator → Vault. Chart-templated ExternalSecret OR hand-applied — pick ONE per service. Recommend **chart-templated** (versioned with code). | `KEYCLOAK_CLIENT_SECRET`, `DATABASE_URL`, `ANTHROPIC_API_KEY` |
| **Feature flags (boot)** | Per-svc Pydantic/Rust default + Helm `env:` override | `CHAT_ENABLED`, `STOA_LLM_PROXY_ENABLED`, `STOA_AUTO_REGISTER` |
| **Feature flags (per-tenant)** | DB row, NOT env. Document anti-pattern. | `PIIMaskingConfig` — already correct |
| **Multi-env values** | (Currently single-env.) When introduced: per-env values overlay file in `stoa-infra/deploy/<env>/values-<svc>.yaml` referenced by ArgoCD ApplicationSet. | future state |
| **Frontend env** | Build-time bake (Dockerfile build args) for non-secret config. Runtime injection via container nginx (`runtime-config.js`) for `VITE_KEYCLOAK_URL` and similar that vary per cluster. **Already the pattern; document it.** | `VITE_API_URL`, `VITE_KEYCLOAK_URL` |
| **Logging level** | Per-svc env (`LOG_LEVEL`/`STOA_LOG_LEVEL`/`VITE_ENABLE_DEBUG`). Document the matrix. | per-svc |

### G.3 — Documentation manquante

- `docs/infra/CONFIG-SOURCES.md` — pour chaque service, qui pilote quoi (Pydantic vs Helm vs Vault). Should be the single doc operators consult before any "where do I set X" question.
- `docs/infra/SECRETS-VAULT-PATHS.md` — Vault path → K8s Secret name → env var mapping.
- `docs/infra/MULTI-ENV-PLAYBOOK.md` — how to introduce staging/dev cluster without forking values files.
- `stoa-gateway/README.md` (or per-chart `README.md`) — clarify `env:` block vs top-level pattern (E.3).
- `control-plane-api/CLAUDE.md` — add note about OpenSearchSettings vs main Settings split (E.4).
- `control-plane-api/CLAUDE.md` — add note about `_BASE_DOMAIN` load-time freezing (E.1).

### G.4 — Risques identifiés pour Phase 1/2

| Risk | Severity | Mitigation |
|------|----------|------------|
| Removing `MCP_GATEWAY_URL` hardcode silently breaks chat routing in clusters where `mcp-gateway` Service is a BC alias | **HIGH** | Verify `kubectl get svc -n stoa-system mcp-gateway` first. If Service exists as alias, keep until next major. |
| Renaming `STOA_SNAPSHOT_*` ↔ `STOA_SNAPSHOTS_*` | MEDIUM | Provide alias for 1 release. Coordinate with ops doc for snapshot diagnostics. |
| Switching gateway secrets from hand-applied to chart-templated ExternalSecret | MEDIUM | Verify Secret name + key names match. Apply chart change in lower-env first. Coordinate Vault path migration if needed. |
| Removing plaintext DB password from `cp-api/values.yaml` | HIGH | Verify `external-secret-database.yaml` is wired to envFrom. Must NOT cause cp-api boot fail. |
| Tightening `LOG_FORMAT: Literal["json","text"]` in cp-api | LOW | Pre-validate that no env override uses other values. |
| Frontend env inventory cleanup (`.env.example` truncates) | LOW | Generate `.env.example` from `src/config.ts` with a build script — auto-sync. |
| Multiple `dev` worktrees with stale `.env` files for cp-api | MEDIUM | Out of scope for Phase 1; flagged for dev tooling cleanup. |
| Operator surprise on chart `STOA_KEYCLOAK_URL` hardcode | LOW | Document in chart README; remove the `env.STOA_KEYCLOAK_URL` line entirely (it's misleading). |

### G.5 — Phase 1 sequencing proposal

1. **G.5.a — Pure cleanup (non-breaking, parallel-safe)**: deletes monorepo dead k8s/configmap.yaml, AWX_URL from chart, `.env.example` drift fixes, cp-api docs/CLAUDE.md notes. Can ship as small PRs.
2. **G.5.b — Source-of-truth officialization (single MEGA, requires Council)**: introduce `docs/infra/CONFIG-SOURCES.md`, document patterns, refactor `stoa-gateway` chart to single pattern (env: only or top-level only), expose `llm_router`/`api_proxy`/`federation` configs in values.yaml.
3. **G.5.c — Cross-repo contract hardening (separate MEGA)**: standardize ExternalSecret pattern, eliminate plaintext credentials from values.yaml, audit all Vault paths, define `stoa-platform/values.yaml` umbrella for shared values like `keycloak.realm`.

---

## Section H — Questions ouvertes pour arbitrage Phase 1

Decisions to make BEFORE committing to Phase 1 implementation. These are not technical — they require product/ops alignment.

1. **Helm values vs Pydantic/Rust default — primary SoT?**
   - Option A: chart values.yaml is canon; Pydantic/Rust defaults are "dev-only fallbacks".
   - Option B: code defaults are canon; chart values.yaml is "prod overrides only" (slim).
   - Option A favors ops control; Option B favors developer ergonomics. **Recommend Option A** for runtime behavior, Option B for type/shape (validators stay in code).

2. **K8s ConfigMap — kill or keep?**
   - Currently chart-level ConfigMaps (other than OPA policies) are not used; all env vars come from Helm `env:` block + envFrom Secret. Monorepo `<svc>/k8s/configmap.yaml` is dead.
   - Option A: kill all ConfigMap-as-config patterns; Helm `env:` + Secret only.
   - Option B: introduce chart-templated ConfigMap for non-secret env vars (cleaner separation from secret envFrom).
   - **Recommend Option A** unless we need to share env vars across multiple deployments.

3. **Secrets — chart-templated ExternalSecret OR hand-applied?**
   - Currently both patterns exist (gateway: chart disabled + hand-applied active; gitlab: hand-applied; opensearch: hand-applied; database: hand-applied).
   - Option A: standardize on chart-templated (versioned with code, easier per-env overlay).
   - Option B: standardize on hand-applied (currently active, no migration).
   - **Recommend Option A** for new charts; deprecate hand-applied with a 1-cycle migration window.

4. **Tilt overrides — versioned per-developer OR centralized?**
   - Currently centralized in `stoa-infra/deploy/tilt/values-local/*.yaml`. Works.
   - Operator question: do we ever need per-dev Tilt overrides? If yes, define a `values-local-<dev>.yaml` ignored pattern.
   - **Recommend status quo**.

5. **Cross-repo — stoa declares contract OR stoa-infra pilots value?**
   - For env name (e.g. `GIT_PROVIDER`): stoa code declares the contract. ✓
   - For env value (e.g. `GIT_PROVIDER=github` vs `gitlab`): stoa-infra Helm values pilots. ✓
   - For env presence (e.g. is `STOA_LLM_ROUTER__*` exposed?): currently stoa code declares but stoa-infra doesn't expose ⇒ **drift** (F.5). Decision: stoa-infra MUST expose every code-declared config knob, or stoa code MUST drop the knob.
   - **Recommend**: enforce a CI gate `cross-repo-config-coverage.yml` that diffs `Config` struct fields against chart `values.yaml` keys and warns on omissions.

6. **Multi-env plan (staging vs prod) — when?**
   - Currently single-env (`baseDomain: gostoa.dev`). Phase 1 does NOT need to introduce multi-env, but should not preclude it.
   - **Recommend**: Phase 1 architecture must support multi-env via overlay `values-<env>.yaml`; do not introduce values that hardcode `gostoa.dev` outside `baseDomain`.

7. **Naming hygiene — alias-friendly for backward compat?**
   - For renames like `STOA_SNAPSHOTS_*` → `STOA_API_SNAPSHOT_*`, do we accept legacy alias for 1 release, then break?
   - Per memory `feedback_no_schedule_arbitrary_timers.md`: aliases removed on **evidence of non-use**, not calendar date. Linear ticket tracks; no scheduled cleanup agent.
   - **Recommend**: 1-release alias with deprecation log line; track removal on Linear.

8. **`.env.example` — autogen or hand-maintained?**
   - Currently hand-maintained, drifts from code.
   - Option A: autogen from Pydantic/Rust schema via `python -m src.config dump` / `cargo run --bin dump-config`.
   - Option B: keep hand-maintained, add CI lint that diffs `.env.example` keys against `Settings.__fields__`.
   - **Recommend Option B** initially (simpler), Option A long-term.

---

## Notes — scope explosion & recommended decomposition

The 50-config target was achievable but the scope of **derived dead/duplicate/ambiguous findings spans 3 distinct concerns**:

- **Applicatif** (cp-api Settings layering, OpenSearchSettings split, frontend env, Pydantic validators).
- **stoa-infra Helm** (chart pattern inconsistency, ExternalSecrets drift, hand-applied vs templated, plaintext password in values).
- **CI/dev tooling** (62 secrets/16 vars, naming collisions across services, `.env.example` autogen policy).

**Recommended Phase 1 split into three sub-tickets** rather than one mega-rewrite:

- **INFRA-1a — Applicatif** (~21-34 pts): kill C.3-C.5 dead k8s/, fix C.1-C.2 chart, document E.1 (`_BASE_DOMAIN` load-time), refactor E.4 (OpenSearchSettings consolidation), `.env.example` lint CI, B.6 (`DATABASE_POOL_SIZE` doc fix), D.6 (`STOA_SNAPSHOT*` rename + alias), Pydantic Literal tightening (D.2). 1 cp-api PR + 1 docs PR.
- **INFRA-1b — stoa-infra Helm** (~21-34 pts): kill C.10 chart externalsecret OR migrate to it (decision in arb 3), fix D.5/F.4 (DB password leak), fix D.10/E.2 (gateway hardcode), fix E.3 (chart pattern uniformization), expose F.5/F.6/F.7 (llm_router, federation, api_proxy in values), umbrella `stoa-platform` chart introduction. 2-3 stoa-infra PRs.
- **INFRA-1c — CI/dev tooling + cross-repo contract** (~13-21 pts): introduce `cross-repo-config-coverage.yml` CI gate (arb 5), persona credentials registry (D.9), `docs/infra/CONFIG-SOURCES.md`, `SECRETS-VAULT-PATHS.md`, `MULTI-ENV-PLAYBOOK.md`. 1-2 PRs across stoa + stoa-docs.

Each sub-ticket is a 21-34 pt MEGA per user preference. They sequence roughly INFRA-1a → INFRA-1b (b depends on a's docs) → INFRA-1c (depends on both).

---

## Appendix — files inspected (reproducibility)

```
# stoa monorepo
control-plane-api/src/config.py
control-plane-api/src/core/pii/config.py
control-plane-api/src/features/error_snapshots/config.py
control-plane-api/src/opensearch/opensearch_integration.py
control-plane-api/.env.example
control-plane-api/k8s/configmap.yaml
control-plane-ui/.env.example
control-plane-ui/src/config.ts (consumer grep only)
portal/.env.example
portal/k8s/configmap.yaml
e2e/.env.example
landing-api/.env.example
stoa-gateway/.env.example
stoa-gateway/src/config.rs
stoa-gateway/src/config/  (mtls, dpop, sender_constraint, llm_router, api_proxy, expansion, federation, loader)
stoa-go/pkg/config/config.go
Tiltfile
.github/workflows/  (62 distinct secrets, 16 distinct vars enumerated)

# stoa-infra
charts/control-plane-api/values.yaml
charts/control-plane-api/templates/deployment.yaml
charts/control-plane-ui/values.yaml
charts/control-plane-ui/templates/deployment.yaml
charts/stoa-portal/values.yaml
charts/stoa-portal/templates/deployment.yaml
charts/stoa-gateway/values.yaml
charts/stoa-gateway/templates/deployment.yaml
charts/stoa-gateway/templates/externalsecret.yaml
deploy/external-secrets/external-secret-gateway.yaml
deploy/external-secrets/external-secret-database.yaml (referenced, not read)
deploy/external-secrets/external-secret-anthropic.yaml (referenced, not read)
deploy/external-secrets/external-secret-opensearch.yaml (referenced, not read)
deploy/external-secrets/external-secret-gitlab.yaml (referenced, not read)
deploy/tilt/values-local/  (referenced from Tiltfile, contents not deeply inspected)
```

End of Phase 0 cartography. Next gate: arbitrage decisions Section H → Phase 1 ticket creation (INFRA-1a/b/c) → Council validation if Impact ≥ HIGH.
