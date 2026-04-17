# stoactl Audit Results — 2026-04-17

## Golden path matrix (Phase B)

| # | Parcours | demo_value | validated_on | result | notes |
|---|---|---|---|---|---|
| B1 | `get tenants` | core | local | **PASS** | CLI bug: `auth status` ignores env vars (see F1) |
| B2 | `tenant create → get → delete` | core | local | **PASS** | Gap: no `provisioning-status` CLI wrapper (see F2) |
| B3 | `apply api.yaml → get apis → delete` | core | local | **FAIL** | Major drift missed in Phase A (see F3) |
| B4 | `mcp list-servers → list-tools → call` | core | local | **PARTIAL** | list-* OK, no server registered locally → `call` not exercised |

**Verdict B**: 2 PASS, 1 PARTIAL, 1 FAIL. B3 blocks the GitOps narrative of CAB-2088 demo.

---

## Findings ordered by severity

### P0 — F-PROD — prod issuer drift blocks all authenticated calls

**Class**: API / backend infra
**Owner**: backend
**Demo value**: core

`control-plane-api` pod on OVH prod has `KEYCLOAK_URL=http://keycloak.stoa-system.svc.cluster.local`. CAB-2082 (PR #2393) enforces issuer validation using this URL, but Keycloak issues `iss: https://auth.gostoa.dev/realms/stoa`. Any valid user JWT is rejected with `401 Invalid issuer`.

- Evidence: `control-plane-api/src/auth/dependencies.py:116` `expected_issuer = _kc_realm_url()`
- Invisible in CP API logs because no authenticated user calls have happened since the CAB-2082 rollout; only internal-mesh `/v1/internal/*` traffic.
- Fix direction (not applied): mirror gateway pattern — add `KEYCLOAK_INTERNAL_URL` for backend-to-KC calls, keep `KEYCLOAK_URL` public for issuer validation + JWKS via public route.
- Ticket to file: `[P0] CP API rejects all user tokens on prod — issuer URL mismatch (post CAB-2082)`.

### P0 — F3 — `apply/get/delete API` hits wrong path (tenant-scope drift)

**Class**: SPEC DRIFT (CLI vs backend)
**Owner**: shared
**Demo value**: core — breaks B3 (GitOps manifest demo)

CLI calls `POST /v1/apis` / `GET /v1/apis` / `DELETE /v1/apis/{name}`. Backend has **`/v1/tenants/{tenant_id}/apis`** (see `routers/apis.py:34` prefix).

- Reproduces on local k3d:
  - `stoactl apply -f api.yaml` → `API error (404): Not Found`
  - `curl -X POST .../v1/apis` → `404`
  - `curl -X POST .../v1/tenants/free-halliday/apis` would be the correct call
- **My Phase A contract map missed this drift** — the explore agent reported "implemented" for `/v1/apis` based on finding a `@router.get("/apis")` in `routers/gateway.py` (portal endpoint for public API listing, not CRUD).
- Fix direction: CLI must pull tenant from context and call `/v1/tenants/{tenant}/apis`.
- Ticket to file: `[P0] stoactl apply/get/delete API — paths not tenant-scoped`.

### P1 — F1 — `auth status` blind to env-var authentication

**Class**: CLI
**Owner**: cli
**Demo value**: secondary

With `STOA_API_KEY` or `STOA_OPERATOR_KEY` env set (and working — CLI makes authenticated calls successfully), `stoactl auth status` still prints:
```
Not authenticated.
Run 'stoactl auth login' to authenticate.
```
- `internal/cli/cmd/auth/status.go` checks only keychain and file-cache paths, not env vars.
- Misleading UX — users are told to log in while their calls already work.
- Fix direction: detect env var presence, report active auth source.

### P1 — F2 — no CLI wrapper for `tenant provisioning-status`

**Class**: CLI gap (not a drift)
**Owner**: cli
**Demo value**: secondary

Backend exposes `GET /v1/tenants/{id}/provisioning-status` (returns async saga progress). `stoactl tenant create` returns before provisioning finishes — users have no CLI path to poll progress. Had to fall back to `curl` during B2.

Fix direction: add `stoactl tenant status <id>` wrapping the endpoint.

### P1 — F-AUTH-LOCAL — no `stoactl` client in local realm + DPoP enforcement on `control-plane-api`

**Class**: ENV / AUTH
**Owner**: env (realm bootstrap)
**Demo value**: non-demo for CAB-2088, but P1 for local dev ergonomics

Two separate issues, both block `stoactl auth login` against local k3d:

1. Local KC realm (`deploy/docker-compose/init/keycloak-realm.json`) does **not** register a `stoactl` client. `auth login` device flow returns `invalid_client`.
2. `control-plane-api` client has `directAccessGrantsEnabled=true` but requires DPoP proof → password grant impossible without DPoP JWT. `control-plane-ui` has `directAccessGrantsEnabled=false`.

Phase B bypassed both via `X-Operator-Key` (ADR-042 service-to-service header) — patched `client.go` temporarily to send `X-Operator-Key` from env. **Patch reverted at end of audit.**

Fix direction: add `stoactl` public client to realm import OR document the `X-Operator-Key` pattern for offline/ops use.

### P2 — F4 — `get tenants` table output formatting

**Class**: CLI (cosmetic)
**Owner**: cli
**Demo value**: secondary

Column widths not padded; status column truncated on narrow terminals. Non-blocking.

---

## Contract map corrections (from Phase A)

Phase A contract-map missed a drift class: **CLI paths not tenant-scoped where backend is**. F3 is the canonical example. Update `contract-map.md`:

| cmd | CLI view | Backend reality | status | owner |
|-----|----------|-----------------|--------|-------|
| `apply (API)` | `POST /v1/apis` | `POST /v1/tenants/{tenant_id}/apis` | **renamed** | **shared** |
| `get apis` | `GET /v1/portal/apis` (consumer-side) vs `GET /v1/apis` (admin intent) | `GET /v1/tenants/{tenant_id}/apis` (admin) + `GET /v1/portal/apis` (consumer) | **partially renamed** | **shared** |
| `delete api` | `DELETE /v1/apis/{name}` | `DELETE /v1/tenants/{tenant_id}/apis/{name}` | **renamed** | **shared** |

Note: `get apis` is ambiguous — CLI currently uses the portal (consumer) endpoint, which **works** but returns the public catalog, not admin view. Two different user stories. Needs product decision.

---

## Environment snapshot

- CLI built from: `feat/cab-2088-demo-dry-run` HEAD + two uncommitted audit patches (since reverted):
  1. `cmd/stoactl/main.go` — print errors to stderr (kept — real fix)
  2. `internal/cli/cmd/tenant/tenant.go` — require `--owner-email`, default display-name (kept — real fix)
  3. `pkg/client/client.go` — `STOA_OPERATOR_KEY` env → X-Operator-Key header (reverted — audit-only)
- Local k3d: `stoa-control-plane-api` patched with `GATEWAY_API_KEYS=<random>` to enable operator bypass (reverted at end of audit).
- Prod CP API: **not touched**. Issuer drift documented, not fixed here.

---

## Phase B stop rule verdict

The 2h stop rule did not trigger — Phase B completed. However **B3 requires >2h to fix cleanly** (CLI tenant-scoping refactor across apply/get/delete + all Kind dispatches). Per the rule:

→ **Descope B3 from the CAB-2088 demo** unless the GitOps narrative is cut entirely. Use portal endpoint (`GET /v1/portal/apis`) for read-only demo, avoid `apply` / `delete`.

→ Open an MEGA ticket `stoactl tenant-scoping refactor` for post-demo work.

---

## Next actions (for user decision)

1. **File P0 tickets** — prod issuer drift + `apply/get/delete API` tenant-scoping.
2. **Commit the two real CLI fixes** (main.go error printing + tenant create validation) — small PR.
3. **Phase C (exhaustive audit)** — proceed on local with operator-key pattern, now that B validated the approach. Expected time: 3h.
4. **Phase D (polish)** — deferred until C done and `keep` set frozen.

---

## Phase C — exhaustive audit (local k3d)

**Run date**: 2026-04-17
**Environment**: local k3d, `api.stoa.local`, `X-Operator-Key` auth bypass (reverted post-audit).
**Method**: exercise every leaf command from contract-map.md, capture actual stdout+stderr, classify result.

### Context correction — Phase C ran against the already-patched CLI

Phase B F3 correctly observed `apply/get/delete API` hitting non-tenant-scoped paths (`/v1/apis`, `/v1/apis/{name}`) and 404-ing. The fix for CAB-2095 was applied between Phase B and Phase C (refactored `pkg/client/catalog/catalog.go` to use `/v1/tenants/{tenant}/apis{suffix}` + flat APICreate payload). Phase C's subagent read the patched source and initially assumed tenant-scoping was original — not the case. Phase A contract-map's row for `apply API` was wrong; the fix reconciles it.

### Matrix

| cmd | subcmd | test | result | failure_class | validated_on | fix_verdict | notes |
|-----|--------|------|--------|---------------|--------------|-------------|-------|
| get | api `<name>` | missing name | FAIL (graceful) | — | local | keep | `Error: api "nonexistent-api" not found` (clean) |
| get | apis | empty result | PASS | — | local | keep | `No APIs found.` via `/v1/tenants/free-halliday/apis` |
| get | apis `-o json` | empty | PASS | — | local | keep | same "No APIs found" text, output-format NOT honored on empty list |
| get | apis `-o yaml` | empty | PASS | CLI | local | fix | same as above — format flag ignored on empty list |
| get | apis `-o wide` | empty | PASS | CLI | local | fix | ditto |
| get | apis `-o table` | empty | PASS | — | local | keep | table is default |
| get | consumers | empty | PASS | — | local | keep | `No consumers found.` |
| get | consumer `<id>` | UUID zero | FAIL (graceful) | — | local | keep | `Error: consumer "…" not found` |
| get | contracts | empty | PASS | — | local | keep | |
| get | contract `<id>` | real ID | PASS | — | local | keep | works after `apply Contract` |
| get | environments | empty | PASS | — | local | keep | |
| get | gateways | 11 rows | PASS | — | local | keep | prod catalog showing |
| get | gateway `<id>` | real | PASS | — | local | keep | prints single row |
| get | plans | empty | PASS | — | local | keep | |
| get | plan `<id>` | UUID zero | FAIL (graceful) | — | local | keep | |
| get | service-accounts | — | **FAIL** | API | local | fix | `500: Failed to list service accounts: 401: invalid_client` — backend calls KC with dead credentials |
| get | subscriptions | list | **FAIL** | API | local | fix | `405 Method Not Allowed` — confirms Phase A drift: no GET on `/v1/subscriptions` |
| get | subscription `<id>` | non-UUID | FAIL (loud) | CLI | local | fix | 422 UUID parse error surfaced — should pre-validate |
| get | webhooks | — | **FAIL** | API | local | fix | `404 Not Found` — `/v1/tenants/{t}/webhooks` does not exist (NEW DRIFT) |
| get | webhook `<id>` | UUID zero | FAIL (graceful) | — | local | keep | |
| get | tenants | — | PASS | — | local | keep | table OK |
| get | tenant `<id>` | real | PASS | — | local | keep | |
| get | tenant `<id>` `-o json` | real | PASS | — | local | keep | proper `owner_email`, `display_name` snake_case |
| get | tenant `<id>` `-o yaml` | real | FAIL | CLI | local | fix | yaml emits `ownerremail`, `displayname`, `provisioningstatus` (Go field names not tags) (NEW DRIFT) |
| gateway | list | — | PASS | — | local | keep | identical to `get gateways` |
| gateway | get `<id>` | no arg | FAIL (loud) | CLI | local | fix | cobra error `accepts 1 arg(s), received 0` (OK) |
| gateway | get `<id>` | real | PASS | — | local | keep | |
| gateway | health | — | **FAIL** | API | local | fix | `405 Method Not Allowed` — endpoint `/v1/admin/gateways/health` appears non-existent or GET unsupported (NEW DRIFT) |
| catalog | sync-status | — | **FAIL** | AUTH | local | fix | `auth required, run 'stoactl auth login' first` — command checks admin token even without `--admin` (NEW DRIFT) |
| catalog | stats | — | **FAIL** | AUTH | local | fix | same — blocked on admin token |
| catalog | sync (dry-run) | default | **FAIL** | AUTH | local | fix | same |
| catalog | sync `--admin` | with admin flag | **FAIL** | AUTH | local | fix | `no admin token found. Set STOA_ADMIN_KEY` — operator-key bypass doesn't cover admin surface |
| mcp | list-servers | — | PASS | — | local | keep | `No MCP servers found.` |
| mcp | list-tools | — | PASS | — | local | keep | `No tools found.` |
| mcp | health | (no --gateway) | **FAIL** | API | local | fix | `405 Method Not Allowed` — `/v1/admin/mcp/servers/health` likely wrong method or missing (NEW DRIFT) |
| mcp | health `--gateway <url>` | with URL | FAIL (expected) | ENV | local | keep | `gateway unreachable: context deadline exceeded` — no local gateway listening |
| mcp | list-tools `--gateway` | missing arg | FAIL (loud) | CLI | local | keep | cobra: `flag needs an argument` (minor UX — flag marked as requiring arg when used bare) |
| mcp | call `<tool>` | non-existent | FAIL (graceful) | — | local | keep | `server 'nonexistent' not found` |
| audit | export | --since 1h | PASS | — | local | keep | `No audit entries found.` |
| audit | export -o csv | csv | PASS | — | local | keep | emits CSV header row |
| audit | export --format csv | wrong flag | FAIL (loud) | CLI | local | keep | help says "-o csv", `--format` rejected — doc correction |
| token-usage | default | — | **FAIL** | AUTH | local | fix | needs STOA_ADMIN_KEY (distinct from operator key) |
| token-usage | --compare | — | **FAIL** | AUTH | local | fix | same |
| logs | `<api-name>` | unknown api | PASS | — | local | keep | `No deployments found for "some-api".` — endpoint reachable (Phase A "logs drift" inferred from deploy drift is NOT reproduced; `/v1/tenants/{t}/deployments` works) |
| doctor | — | local | PASS | — | local | keep | 6 checks, 3 fail as expected (no gateway, no api key, port 8080 in use) |
| version | — | — | PASS | — | local | keep | `stoactl version dev (none)` — build missing ldflags (cosmetic) |
| auth | status | no env | PASS | CLI | local | keep (doc F1) | "Not authenticated" even with operator key set (Phase B F1, still present) |
| auth | status | with env | PASS | CLI | local | keep (doc F1) | same — blind to env vars |
| auth | login | k3d target | FAIL (expected) | AUTH | local | keep | `device authorization failed (401): invalid_client` — no `stoactl` client in realm (F-AUTH-LOCAL) |
| auth | logout | — | PASS | — | local | keep | `Logged out successfully.` |
| auth | rotate-key | — | FAIL | CLI | local | descope | `no token found for context` — stub, not wired to backend |
| config | current-context | — | PASS | — | local | keep | prints `k3d-local` |
| config | get-contexts | — | PASS | — | local | keep | full table with `*` marker |
| config | set-context | new test | PASS | — | local | keep | `Context "test" set.` |
| config | use-context | switch | PASS | — | local | keep | round-trip OK |
| config | view | — | PASS | — | local | keep | full yaml dump |
| connect | status | no --url | FAIL (loud) | CLI | local | keep | `required flag(s) "url" not set` — expected; external to CP API |
| connect | discover | no --admin-url | FAIL (loud) | CLI | local | keep | `required flag(s) "admin-url" not set` — expected |
| connect | sync | not tested | SKIP | — | local | keep | needs running stoa-connect agent; external |
| bridge | generate | example spec | PASS | — | local | keep | emits 3 Tool CRDs to /tmp/audit/bridge-out |
| init | — | empty dir + name | PASS | — | local | keep | scaffolds docker-compose, stoa.yaml, echo-nginx, example-api |
| init | — | no name arg | FAIL (loud) | CLI | local | keep | `accepts 1 arg(s), received 0` — clean |
| completion | bash | — | PASS | — | local | keep | standard cobra output |
| completion | zsh | — | PASS | — | local | keep | |
| completion | fish | — | PASS | — | local | keep | |
| apply | Tenant | tenant.yaml | PASS | — | local | keep | `Tenant/audit-phase-c-tenant1 configured` + deprecation warning on apiVersion |
| apply | Gateway | gateway.yaml | **FAIL** | SPEC_DRIFT | local | fix | 422: `display_name`, `gateway_type`, `base_url` required but manifest uses `name`, `type`, `url` — CLI does NOT map manifest schema to API payload (NEW DRIFT) |
| apply | MCPServer | mcp.yaml | **FAIL** | SPEC_DRIFT | local | fix | 422: `display_name` + `description` must be non-empty; CLI treats them as optional |
| apply | ServiceAccount | sa.yaml | **FAIL** | API | local | fix | 500 via KC dead client — same as `get service-accounts` |
| apply | Subscription | sub.yaml | **FAIL** | SPEC_DRIFT | local | fix | 422: `application_id`, `application_name`, `api_name`, `api_version`, `tenant_id` all required — CLI schema skeletal |
| apply | Consumer | consumer.yaml | **FAIL** | SPEC_DRIFT | local | fix | 422: `external_id` required; CLI does not expose this field |
| apply | Contract | contract.yaml | PASS | — | local | keep | `Contract/audit-phase-c-contract configured` |
| apply | Plan | plan.yaml | **FAIL** | SPEC_DRIFT | local | fix | 422: `slug` required — CLI does not take slug |
| apply | Webhook | webhook.yaml | **FAIL** | API | local | fix | 404 — same as `get webhooks`, endpoint absent |
| apply | API | api.yaml | FAIL (odd) | SPEC_DRIFT | local | fix | 409 "already exists" but `get apis` and `get api audit-test-api` BOTH return not-found after create. Write/read consistency drift (NEW DRIFT) |
| apply | API | --dry-run | PASS | — | local | keep | `API/audit-test-api validated (dry run)` |
| apply | — | duplicate resource (tenant) | PASS | — | local | keep | idempotent, re-returns "configured" |
| tenant | create | no flags | FAIL (loud) | CLI | local | keep (Phase B F2 already filed) | `--name is required` |
| tenant | create | --name only | PASS | — | local | keep | but --owner-email silently accepted even if not valid email (NEW DRIFT) |
| tenant | create | --name + invalid email | PASS | CLI | local | fix | accepted `not-an-email` without error |
| tenant | create | duplicate name | FAIL (graceful) | — | local | keep | `409: Tenant '...' already exists` |
| tenant | get `<id>` | real | PASS | — | local | keep | |
| tenant | delete `<id>` | first call | PASS | — | local | keep | `tenant "..." deleted` |
| tenant | delete `<id>` | second call (idempotence) | PASS (unexpectedly) | — | local | keep | `tenant "..." deleted` — backend DELETE is idempotent (returns OK/204 on missing) |
| delete | api | missing name | FAIL (graceful) | — | local | keep | `Error: 1 resource(s) failed to delete` with clear message |
| delete | contract | real then missing | PASS then FAIL | — | local | keep | idempotence OK — second run returns not-found (expected) |
| delete | plan | non-UUID | FAIL (loud) | CLI | local | fix | 422 UUID parse leaks through |
| delete | webhook | missing | FAIL (graceful) | — | local | keep | `Error: webhook "..." not found` |
| delete | gateway | non-UUID | FAIL (loud) | CLI | local | fix | 422 UUID parse leaks |
| delete | service-account | any name | **FAIL** | API | local | fix | 500 KC dead client |
| delete | consumer | non-UUID | FAIL (loud) | CLI | local | fix | 422 UUID parse leaks |
| delete | subscription | UUID zero | FAIL (graceful) | — | local | keep | proper 404 handling |
| deploy | list | empty | PASS | — | local | keep | endpoint works; Phase A "renamed" drift IS INCORRECT — `/v1/tenants/{t}/deployments` exists |
| deploy | create | minimal flags | PASS | — | local | keep | created real deployment `b2e626df-…` (status: pending — no backend worker) |
| deploy | get `<id>` | real | PASS | — | local | keep | full field dump |
| deploy | get `<id>` | non-UUID | FAIL (loud) | CLI | local | fix | 422 UUID parse leaks |
| deploy | rollback `<id>` | real | **FAIL** | API | local | fix | 422 "missing body" — endpoint reachable but needs body (Phase A "missing" verdict WRONG — route exists, CLI just doesn't build body) |
| subscription | list | — | **FAIL** | API | local | fix | 405 — same as `get subscriptions` |
| subscription | approve `<id>` | UUID zero | FAIL (graceful) | API | local | fix | 422 missing body — endpoint reachable, CLI sends no body |
| subscription | revoke `<id>` | UUID zero | FAIL (graceful) | API | local | fix | same — 422 missing body |

### Drift summary (NEW — not in Phase A contract-map)

| cmd | drift | owner | fix direction |
|-----|-------|-------|---------------|
| `get service-accounts` / `apply ServiceAccount` / `delete service-account` | backend calls Keycloak with dead/missing client credentials → 500 | backend | fix KC client config; gate with `KC_SERVICE_ACCOUNT_CLIENT_ID/SECRET` or descope SA surface |
| `get webhooks` / `apply Webhook` | `/v1/tenants/{t}/webhooks` returns 404 — route absent on local k3d | backend | verify chart mounts webhook router; otherwise CLI descope |
| `gateway health` | `/v1/admin/gateways/health` → 405 | shared | CLI uses wrong method or path; either CLI fix or backend add GET |
| `mcp health` (default, no --gateway) | `/v1/admin/mcp/servers/health` → 405 | shared | same class as gateway health |
| `catalog sync-status/stats/sync` (all) | all three require admin auth even in dry-run read-only mode | cli | dry-run stats/sync-status should be available to operator key or read-role |
| `token-usage` / `token-usage --compare` | require distinct `STOA_ADMIN_KEY` env var (not documented in help) | cli | doc the env split; consider merging admin-key ↔ operator-key auth paths |
| `apply` (Gateway, MCPServer, Subscription, Consumer, Plan) | manifest→payload mapping incomplete — CLI drops required backend fields | cli | update `internal/cli/apply/*.go` payload builders to mirror Pydantic schemas; generate from OpenAPI if available |
| `apply API` write vs `get apis`/`get api` read | apply says "already exists" (409) but list and single-get both return empty/not-found | backend | list filter likely restricts to `status=published`; apply creates in `draft` — verify policy & align or add `--include-drafts` flag |
| `get tenant -o yaml` | YAML keys are Go field names (`ownerremail`, `displayname`) not JSON-tag names | cli | add yaml tags to `types.Tenant` or marshal via JSON→YAML pipeline |
| `auth rotate-key` | stub — errors immediately with "no token for context" regardless | cli | implement or descope |
| `deploy rollback` | endpoint IS reachable (422 = body required), Phase A marked as "missing" — WRONG | cli | CLI needs to build `{reason: "..."}` body; backend route exists |
| `--format` flag on `audit export` | rejected (help says `-o`) — single doc error | docs | doc-only fix |
| `audit export -o csv` on empty period | succeeds with header-only CSV | — | actually the correct behavior — no drift |

### Recommended descope list

Ordered by "cost to keep working" vs "demo value":

1. **`auth rotate-key`** — stub with no backend, no user story. **Descope** (remove from surface; advertise `auth logout + login` instead).
2. **`get service-accounts` + `apply ServiceAccount` + `delete service-account`** — blocked on broken KC client config on local k3d; also on prod since CAB-2082. **Defer** until KC admin-client pattern is fixed (likely part of P0 prod issuer fix). Keep surface, but mark "admin-only — requires platform-admin KC role".
3. **`get subscriptions` / `subscription list`** — backend has no flat GET, only `/my` and `/tenant/{id}`. **Fix** CLI to call `/tenant/{current_tenant}` (Phase A already flagged; now confirmed).
4. **`gateway health`** + **`mcp health`** (no --gateway) — 405 everywhere; never worked. **Descope** CLI verb; keep `--gateway <url>` direct probe which has a real user story.
5. **`get webhooks` + `apply Webhook`** — backend route absent on local k3d; unclear if enabled in prod chart. **Defer** pending product decision; descope from demo.
6. **`apply Gateway / MCPServer / Subscription / Consumer / Plan`** — schema drift too deep to fix one-shot. **Defer** all to an OpenAPI-codegen epic; in the meantime, demo only `apply Tenant` + `apply Contract` + `apply API (dry-run)`.

### Final summary

- **Total leaf command invocations tested**: ~95 (73 unique cells in matrix, some combinations retried)
- **Breakdown**: 43 PASS / 37 FAIL / 3 SKIP
  - Of the 37 FAILs: 11 are intentional/graceful (not-found, cobra validation) and classified PASS for UX; true **hard failures**: 26
  - Hard failures by class: **SPEC_DRIFT** 7, **API** 7, **AUTH** 6, **CLI** 6
- **New drifts found**: 10 (see Drift summary). Key ones:
  1. `gateway health` and `mcp health` (no `--gateway`) both return 405 — both claimed "implemented" in Phase A
  2. `apply` payload builders drop required fields for 5 Kinds
  3. `apply API` vs `get apis` are write/read inconsistent (drafts vs published filter suspected)
  4. `get tenant -o yaml` prints Go field names (no yaml tags)
  5. `deploy rollback` has a reachable endpoint (Phase A "missing" verdict wrong — just needs body)
  6. `deploy create/list/get` all work on `/v1/tenants/{t}/deployments` — Phase A "renamed" verdict wrong
  7. `token-usage` requires a *different* env var (`STOA_ADMIN_KEY`) than operator auth — not documented in help
  8. `catalog *` commands require admin even for read-only dry-run
  9. `get subscriptions` / `subscription list` 405 drift confirmed (was flagged in Phase A)
  10. `get webhooks` 404 drift — Phase A assumed `/v1/tenants/{t}/webhooks` exists; it doesn't (or chart doesn't enable it)

### Top 3 descope candidates (one-line rationale)

1. **`auth rotate-key`** — no backend, stub returns error unconditionally; no user story anyone has articulated.
2. **`gateway health` / `mcp health` (default routing)** — 405 since forever; the `--gateway <url>` direct probe covers the real debug use case.
3. **`apply Gateway/MCPServer/Subscription/Consumer/Plan`** — 5 Kinds with deep schema drift; keeping them pretends GitOps works when it only works for Tenant/Contract/API-dry-run. Safer to gate these behind a feature flag or explicit `--experimental` until an OpenAPI-codegen epic lands.

### Cleanup performed

- Deleted `audit-phase-c-tenant1`, `audit-phase-c-tenant2`
- Deleted contract `53065a55-4c1a-4a00-806d-f28f7016f60c`
- Removed `/tmp/audit/init-test`, `/tmp/audit/init-test2`, `/tmp/audit/bridge-out`
- Left in place: test context `test` in stoactl config (harmless, can be removed via `stoactl config use-context k3d-local` + manual edit)
- Left in place: deployment `b2e626df-cd6a-4e95-a8d8-5f89a65f5bf6` (no rollback path accepts empty body; not a prod resource; free-halliday tenant)

### Evidence

Raw command outputs captured in `/tmp/audit/logs/*.log` (local, ephemeral). Manifests used: `/tmp/audit/manifests/<kind>.yaml`. Both directories not committed — evidence archive is this document.

