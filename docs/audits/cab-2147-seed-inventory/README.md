# CAB-2147 — Phase 1 Inventory: E2E Seed & Auth Dependencies

**Source:** Playwright artifacts of run [24750762663](https://github.com/stoa-platform/stoa/actions/runs/24750762663) @ commit `47f3d6fa` (PR #2455 head).
**Date:** 2026-04-22
**Status:** Phase 1 deliverable — not validated yet, **do not start Phase 2 until challenge-gate sign-off** (ticket is 21 pts → Council recommended; CLAUDE.md says ≥16 pts triggers Council).

---

## Headline numbers

- **46 unique failing tests** confirmed (matches ticket).
- **138 error-context.md files** across retries.
- **18** show the Keycloak login screen → **auth still failing** for some tests (contradicts the ticket's premise that "personas are now authenticated past login").
- **36** show authenticated shell with empty catalog → seed missing.
- **84** are gateway/integration/demo API-level (no UI snapshot).

---

## Failure families (revised after artifact review)

| ID | Family | # tests | Trace evidence | Owning component | Existing seed? |
|----|--------|--------:|----------------|------------------|----------------|
| A | **Console persona auth → Keycloak login screen** | 6 | `Login with Keycloak` button visible. Tests: `Admin accesses tenants page`, `CPI admin can access all admin sections`, `Platform admin views Access Requests page`, `Tenant admin views AI Tool Catalog`, `Tenant admin views AI Tool subscriptions`, `Tenant admin views Applications page`. | E2E **harness** (auth.setup.ts / test-base.ts persona switching on Console). NOT a seed problem. | n/a — needs harness fix |
| B | Portal authenticated, **catalog 0 APIs** | ~12 | Page badge `parzival Test`, `0 APIs / 0 AI Tools / "No APIs or tools are published yet"`. Tests: `Parzival/Sorrento sees all public OASIS APIs`, `Public APIs are visible to all users`, `Consumer registers/subscribes/discovers`, `Developer opens/sends Chat Agent`, `User views Contracts list`, `Viewer can access contracts page`, `User views credential mappings page`, `Consumer uploads certificate during subscription`, `discovers and tests an API`. | **CP-API seed** (published APIs, AI tools, MCP servers per tenant) | Partial: `python -m scripts.seeder --profile dev` exists with `apis`/`mcp_servers` steps but **never runs in E2E CI** (workflow has no seed step) |
| C | Console authenticated but **action button disabled** | 5 | "Create API" `disabled`. Tests: `Tenant admin creates an API`, `Admin creates a new gateway instance`, `Admin sees the Credential Mappings page on a gateway`, `Chat Agent responds to a simple greeting`, `Viewer cannot access admin pages`, `View workflow templates tab`. | **CP-API seed** (tenant config, gateway pre-registered, chat-settings flag) | Same as B |
| D | Gateway DPoP — `invalid_client` | 1 (+ retries) | KC returns `{"error":"invalid_client"}` for client `stoa-e2e-dpop`. Test: `Gateway health check is reachable for DPoP tests`. | **Keycloak realm** (KC client) + **Vault** (`secret/e2e/clients/dpop`) | None |
| E | Gateway mTLS — explicit `No credentials for api-consumer-001` | 2 | Test source: `Run seed-mtls-demo.py or set MTLS_API_CONSUMER_001_CLIENT_ID/SECRET`. Tests: `Valid cert-bound token with matching certificate`, `Sub-account can call allowed tools`. | **mTLS seed**: `scripts/demo/seed-mtls-demo.py` + `generate-mtls-certs.sh` + Vault `secret/e2e/mtls/*` | Script exists; never run in E2E env. Needs cert mount + env injection |
| F | Gateway federation / credential mapping | 2 | Auth-related 401/404. Tests: `Sub-account can call allowed tools`, `Create a per-consumer credential mapping via admin API`. | **CP-API seed** (federation parent client + per-consumer mapping) | None for E2E |
| G | Gateway UAC contract / MCP discovery | 4 | Pre-created contracts `e2e-gw-sync`, `e2e-mcp-gen` absent. Tests: `Deploy a UAC contract and verify REST/tool route`, `MCP capabilities advertise prompt/resource support`. | **CP-API seed** (UAC contracts) + **gateway sync trigger** | None |
| H | Gateway LLM proxy — 404 on `/v1/chat/completions` & `/v1/messages` | 3 | Tests: `LLM proxy detects OpenAI/Anthropic format`, `LLM proxy rejects request without API key`. | **Demo wiring** — Azure OpenAI proxy backend (CAB-1609) not configured | `scripts/ops/seed-proxy-backends.sh` exists; not run in E2E |
| I | Demo "IA pour tous" (CAB-1609) — 404 on Chat Completions | 5 | `Expected 401 Received 404`. Tests: `Chat Completions endpoint rejects invalid/unauthenticated`, `routes OpenAI-format requests`, `Different API keys cannot cross-access tenants`, `Portal user browses catalog and calls the gateway`. | Same as H | Same |
| J | Integration CP-API contract — 404 on POST `/v1/contracts` | 4 | `Expected 201 Received 404`. Project: `integration` (no auth fixture). Tests: `Create draft contract`, `Generate MCP tools`, `Promote API dev→staging`, `Published contract appears in gateway discovery`. | **Integration test auth** (JWT) + CP-API prefix verification | None — `integration` project uses `request` fixture without bearer token injection |
| K | Integration chat-settings | 2 | Tests: `Tenant admin can read/update chat settings via API`. | CP-API config (chat-settings router enabled per tenant) | None |

**Total: 46 unique fails** (some tests appear in multiple families due to dependencies; e.g. `Sub-account can call allowed tools` straddles E and F).

---

## Discrepancies with the ticket as written

The ticket's framing assumes the harness fix is complete. Evidence shows otherwise. **Three points need correction or expanded scope before Phase 2 starts:**

### 1. Console persona auth is NOT cleared

Ticket says: *"personas (parzival, tenant-admin, cpi-admin) are now authenticated past login"*.
Evidence: 6 console tests render the `STOA Control Plane / Login with Keycloak` page. Personas affected on Console: `anorak` (cpi-admin), `sorrento` (tenant-admin), `art3mis`. The sessionStorage init-script + Proxy-on-page-fixture from PR #2455 works for *some* paths (Portal as parzival) but not for switchPersona-driven Console contexts. Likely cause: `auth.setup.ts` writes per-persona `fixtures/.auth/<persona>.json` with merged sessionStorage from BOTH portal & console; if the SSO step (lines 263-267) silently fails, the console-side sessionStorage entries are missing for that persona. Worth re-running auth.setup with verbose logging before declaring this a seed problem.

**Recommendation:** insert **Phase 1.5 — finish harness diag (2 pts)** before Phase 2. Without it, Phase 2-3 work won't move the pass rate for Family A.

### 2. Tenant names are wrong in the ticket

Ticket says: *"tenants `oasis` + `oasis-gunters`"*.
Reality (`e2e/fixtures/personas.ts`): tenants are `high-five` (parzival/art3mis/aech), `ioi` (sorrento/i-r0k), `oasis` (alex), `*` (anorak). No `oasis-gunters`. Phase 3 must seed for `high-five`, `ioi`, `oasis` — not the ticket's list.

### 3. Existing unified seeder isn't risk-free for prod

`control-plane-api/scripts/seeder/` (with `dev/staging/prod` profiles + steps `tenants, gateway, apis, plans, consumers, mcp_servers, security_posture`) is the right hammer — but `--profile dev` is meant for an isolated local stack with local KC/DB. Running it against the prod CP-API URL (current E2E target) would create demo data in prod. **Phase 3 needs a NEW `e2e` profile** that:
- targets a scoped tenant subset (`high-five`, `ioi`, `oasis`)
- skips Keycloak provisioning steps (KC users come from the existing realm, not from the seeder)
- uses idempotent UPSERT semantics
- is gated by an env var like `STOA_SEED_E2E_OK=1` to prevent accidental runs

---

## Existing seed assets (audit)

| Asset | Path | Status | Used in E2E CI? |
|-------|------|--------|----------------|
| Unified seeder | `control-plane-api/scripts/seeder/__main__.py` | Active, has `dev/staging/prod` profiles | **No** |
| Seed steps | `control-plane-api/scripts/seeder/steps/{tenants,gateway,apis,plans,consumers,mcp_servers,security_posture}.py` | Active | **No** |
| Legacy seed_demo_tenant | `control-plane-api/scripts/seed_demo_tenant.py` | Marked DEPRECATED | No |
| mTLS demo seed | `scripts/demo/seed-mtls-demo.py` | Active (CAB-864) | **No** |
| mTLS cert generator | `scripts/demo/generate-mtls-certs.sh` | Required prerequisite for above | **No** |
| Proxy backend seed | `scripts/ops/seed-proxy-backends.sh` | For Azure OpenAI demo (CAB-1609) | **No** |
| Vault E2E secrets | `secret/e2e/{urls,personas/*}` on hcvault.gostoa.dev | Live (handoff 2026-04-21) | **Yes** (vault-action step in workflow) |
| Vault E2E api-keys | `secret/e2e/api-keys` | **Missing** — vault step logged `not found` for run 24750762663 | Attempted (silently fails) |

**E2E workflow seed step:** `.github/workflows/e2e-tests.yml` has no seed step at all. CP-API state is whatever the prod instance happens to hold at run-time. This is the single biggest gap.

---

## Phases 2-4 — work breakdown for Council input

### Phase 1.5 — finish harness diag (NEW, 2 pts) — RECOMMENDED PREREQUISITE

- Re-run `auth.setup.ts` with `DEBUG=pw:api` and inspect SSO step log lines for anorak/sorrento/art3mis
- Confirm whether per-persona auth state JSON contains console-origin OIDC keys
- If missing, fix the SSO loop in `auth.setup.ts` (lines 263-267) to handle the consent grant flow that prod's `control-plane-ui` KC client may now require
- Acceptance: 6 Family-A tests render Console shell (not Login screen) on next run

### Phase 2 — KC clients + new e2e personas + Vault secrets (6-9 pts, was 5-8 — Spike A revision)

- Provision **7 new e2e Keycloak users** in realm `stoa` (Spike A Option A3 — see `phase-1.5-spike-report.md`):
  - `parzival-e2e@e2e-high-five.io`, `sorrento-e2e@e2e-ioi.corp`, `aech-e2e@e2e-high-five.io`, `art3mis-e2e@e2e-high-five.io`, `i-r0k-e2e@e2e-ioi.corp`, `alex-e2e@e2e-oasis.dev`, `anorak-e2e@gostoa.dev`
  - Each gets `tenant_id=e2e-<x>` group/role mapping (anorak-e2e → `tenant_id=e2e-shared`, NOT `*`)
  - Each gets the **union of all persona scopes**: `stoa:catalog:read`, `stoa:catalog:write`, `stoa:subscriptions:read`, `stoa:subscriptions:write`, `stoa:admin`, `stoa:platform:read`, `stoa:platform:write` (mitigates H1 from harness diag)
- Provision KC client `stoa-e2e-dpop` (DPoP enabled, client-secret auth)
- Store all secrets in Vault: `secret/e2e/clients/dpop`, `secret/e2e/personas/<name>-e2e`, `secret/e2e/api-keys` (test=<value>)
- Vault action mapping: add `secret/data/e2e/clients/dpop client_secret | DPOP_E2E_CLIENT_SECRET` + 7 persona pairs to `e2e-tests.yml`
- E2E workflow swaps `*_USER`/`*_PASSWORD` env-vars to point at e2e variants when running in CI (local `e2e/.env` keeps prod personas)
- mTLS cert generation in E2E bootstrap step (run `generate-mtls-certs.sh` → mount under `RUNNER_TEMP/certs` per Council #4) → seed via `seed-mtls-demo.py`
- All KC ops via `stoa-infra` (idempotent ansible role or terraform), NOT inline in workflow
- `auth.setup.ts` gets JWT-claim assertion: fail loudly if `tenant_id` or required scopes missing on the captured OIDC user

### Phase 3 — CP-API E2E seed runner (10 pts, was 8 — Council Path A) — **REVISED 2026-04-22**

> **Architectural compromise — see `docs/decisions/2026-04-22-cab-2147-e2e-tenant-prefix.md`.**
> Seeder writes into prod CP-API but scoped to a `e2e-*` tenant namespace, never touches prod tenants. Time-boxed; follow-up ticket required for fully isolated E2E env.

- New profile `control-plane-api/scripts/seeder/profiles/e2e.py`:
  - **Tenants prefixed**: `e2e-high-five`, `e2e-ioi`, `e2e-oasis`, `e2e-shared` (NOT the prod tenants `high-five`/`ioi`/`oasis`)
  - **Persona dual-membership**: existing KC users (parzival, sorrento, etc.) get added to corresponding `e2e-*` tenant via the seeder, retain their prod tenant membership
  - per `e2e-*` tenant: 1 published API + 1 AI tool + 1 MCP server (idempotent UPSERT on slug)
  - UAC contracts: `e2e-gw-sync`, `e2e-mcp-gen` (pre-created drafts under `e2e-shared`)
  - 1 gateway instance pre-registered per `e2e-*` tenant
  - chat-settings enabled for tenant admin on `e2e-high-five`, `e2e-ioi`
  - Every seeded row tagged `metadata.purpose=e2e, metadata.owner=cab-2147`
  - Audit log entries emit `e2e=true` annotation
- **Safety rails (Council adjustments #1, #11)**:
  - Refuses to run unless `STOA_SEED_E2E_OK=1` AND `CONTROL_PLANE_URL` matches the allowlist `(api.gostoa.dev|api-staging.gostoa.dev|localhost:*)`
  - Sends `X-Seed-Profile: e2e` header on every write; aborts if CP-API doesn't echo it back
  - Idempotency contract tests in `control-plane-api/tests/test_seeder_e2e.py` (run twice → row counts unchanged, no Kafka event duplication)
- E2E workflow new step (between vault-fetch and test-run): `python -m scripts.seeder --profile e2e --target=$E2E_API_URL`
- Service account JWT: existing `gha-stoa-e2e` Vault role, scoped to seed permissions only
- **Pinning (Council #5)**: workflow checks out `scripts.seeder` at a fixed ref via `actions/checkout` `ref:` parameter

### Phase 4 — Demo + integration wiring + validation (3-5 pts)

- Run `seed-proxy-backends.sh` for Azure OpenAI demo route (CAB-1609 dependency), scoped to `e2e-shared` tenant
- Integration project: inject service-account JWT for `request` fixture (Family J/K)
- Re-run E2E on `fix/cab-2147` branch
- Acceptance: ≥95% pass (≥122/129) — current 81/129 = 63%
- Bump `e2e-environment.md` runbook with cleanup procedure: `python -m scripts.seeder --profile e2e --reset` PLUS `DELETE FROM tenants WHERE slug LIKE 'e2e-%'` PLUS KC cleanup script for `stoa-e2e-dpop` + mTLS consumers
- Unblock CAB-2142 (PR #2450)
- CI artifact retention reduced to ≤7 days (Council #13)
- mTLS cert generation in `RUNNER_TEMP` + explicit `shred` on cleanup (Council #4)

### Council adjustments — tracking matrix

| # | Adjustment | Phase | Status |
|--:|------------|-------|--------|
| 1 | URL allowlist + `X-Seed-Profile` echo handshake | Phase 3 | Planned |
| 2 | Phase 1.5 hard 4h timebox + escalation fallback | Phase 1.5 | Planned |
| 3 | `--reset` works end-to-end before Phase 4 closes | Phase 4 | Planned |
| 4 | mTLS cert gen in tmpfs/`RUNNER_TEMP` + shred | Phase 2/4 | Planned |
| 5 | Pin `scripts.seeder` ref in `e2e-tests.yml` | Phase 3 | Planned |
| 6 | Tag E2E artifacts `purpose=e2e,owner=cab-2147` | Phase 3 | Planned |
| 7 | 90-day rotation cadence for KC + mTLS CA | Phase 2 + runbook | Planned |
| 8 | Explicit `::add-mask::` on Vault secrets | Phase 2 (workflow) | Planned |
| 9 | ADR / decision log entry | Phase 0 | **Done + revised** — `docs/decisions/2026-04-22-cab-2147-e2e-tenant-prefix.md` |
| 10 | Seed into `e2e-*` prefixed tenants | Phase 3 | **Designed** (with new e2e personas per Spike A Option A3) |
| 11 | Idempotency contract tests | Phase 3 | Planned |
| 12 | Confirm synthetic-persona status in ADR | Phase 0 | **Done** (in ADR open questions) |
| 13 | E2E artifact retention ≤7 days | Phase 4 (workflow) | Planned |
| 14 | `e2e=true` annotation on audit rows | Phase 3 | **Mostly moot** (Spike C: seeder doesn't trigger Kafka/audit) — kept as defensive measure for future seeder steps |

### Phase 1.5 — DONE 2026-04-22

Spikes A/B/C resolved (`phase-1.5-spike-report.md`):
- Spike A: CP-API single-tenant-per-user → dual-membership infeasible → **switched to Option A3** (new e2e personas)
- Spike B: catalog query is **global** → no tenant-scoping work needed
- Spike C: seeder uses raw SQL only → **zero Kafka pollution** → Archi's biggest concern cleared

Harness diag (`phase-1.5-harness-diag.md`): partial — read-only investigation hit limit. H1 (missing JWT claims) is the most-likely cause of the 6 Console-Login failures. Phase 2 builds in the mitigation (union scopes + always-emit `tenant_id` + claim assertion in auth.setup). If after Phase 2 the failures persist, allocate a separate small ticket for interactive root-cause.

---

## Notes for the next session

- Council Stage 1/2 ran 2026-04-22 → first pass **Redo 5.75/10**, Path A re-plan complete, **re-score pending** (this revision should land 6.5-7.5 = `council:plan-fix` + user confirm).
- **Phase 1.5 is now load-bearing for Phase 3 design**, not just harness diag — the three open-question spikes must close before the seeder profile can be implemented.
- Linear label `council:plan-fix` to apply on CAB-2147 after re-scoring.
- Follow-up ticket pending: "Stand up isolated E2E environment (replace e2e-* tenant prefix workaround)" — file once Phase 4 ships green.
