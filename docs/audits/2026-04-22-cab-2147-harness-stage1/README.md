# CAB-2147 Stage 1 + 1.1 — Harness fix evidence archive

**Date:** 2026-04-22
**PR:** https://github.com/stoa-platform/stoa/pull/2456
**Branch:** `fix/cab-2147-harness-rewrite` HEAD `104b9f65`

## TL;DR

Stage 1.1 resolves the 6 Console Login-screen failures from run 24750762663. 5/6 scenarios clean pass, 1/6 flaky (passed on retry, different root cause).

## Validation run

https://github.com/stoa-platform/stoa/actions/runs/24766592184

| Scenario | Persona | Result |
|----------|---------|--------|
| Admin accesses tenants page | anorak | expected |
| CPI admin can access all admin sections | anorak | flaky (waitForLoadState timeout, NOT Login) |
| Platform admin views Access Requests page | anorak | expected |
| Tenant admin views AI Tool Catalog | parzival | expected |
| Tenant admin views AI Tool subscriptions | parzival | expected |
| Tenant admin views Applications page | parzival | expected |

Archive: `results-shard1.json` (console-chromium project).

## Root cause evolution

| Phase | Hypothesis | Outcome |
|-------|-----------|---------|
| Phase 1.5 harness diag | H1: Console rejects missing JWT claim | **Invalidated** — JWT decode showed structurally identical claims across working/failing personas |
| Stage 1 | `addInitScript` / React-OIDC boot race | **Partially correct** — defensive guard added, but trace showed sessionStorage WAS present. Actual bug was deeper. |
| Stage 1.1 | **Token expiry** (KC 5min TTL vs 4-9min job duration; silent-renew broken by SameSite cookies) | **Confirmed** — refresh via `refresh_token` grant resolved all 6 Login-screen fails |

## Fix summary

`e2e/fixtures/test-base.ts` — new `refreshExpiredOidcTokens(sessionData)` helper:
1. Walks captured OIDC storage entries (`oidc.user:{authority}:{clientId}`)
2. Parses `expires_at`, checks against `now + 60s` buffer
3. If expired: POSTs `refresh_token` grant directly to KC token endpoint
4. Rebuilds OIDC user blob with fresh access/refresh/id tokens + updated profile (if id_token rotated)
5. Returns updated sessionData for `installSessionStorageInitScript`

Wired into:
- `createContextFromStorageState` (used by authSession fixture init + switchPersona)
- `authenticatedContext` fixture
- `loadPersonaContext` export

Stage 1 defensive guard (`ensureSessionStorageLoaded`) kept in place — covers the race window for the rare case where initScript timing matters on cold contexts.

## Residual fails (out of scope)

~40 remaining fails on run 24766592184 are NOT auth-related:
- Gateway 401 on `/dpop/` routes (`stoa-e2e-dpop` client absent)
- mTLS 401 (`api-consumer-001` creds missing)
- Portal catalog empty (no seeded APIs on e2e tenants)
- Console action buttons disabled (backend preconditions missing)
- Integration endpoints 404 (chat-settings, pre-created contracts absent)

All tracked under CAB-2147 Phase 2 (stoa-infra KC+Vault) and Phase 3 (CP-API seeder e2e-* tenants).

## Files touched

- `e2e/fixtures/test-base.ts` — +119 / -13 LOC (refresh helper + defensive guard + typed returns)
- `e2e/steps/common.steps.ts` — dropped 6 redundant `page.goto(URLS.console)` (pre-nav now in switchPersona)
- 6 feature files: `@regression` tag on failing scenarios
- `docs/plans/2026-04-22-cab-2147-harness-rewrite.md` — staged plan (Stage 2-3 blocked on stoa-infra)
- `docs/audits/cab-2147-seed-inventory/` — Phase 1 inventory + Phase 1.5 spike/harness diag reports

## Next session starting points

1. **Stoa-infra PR for `directAccessGrantsEnabled: true`** on `stoa-portal` KC client — unblocks Stage 2 (password-grant rewrite, eliminates UI login dance). ~10 LOC terraform/ansible.
2. **Phase 2 MEGA** — 7 e2e KC users + `stoa-e2e-dpop` + mTLS bulk + Vault entries. Requires own Council ack (Decision Gate #9 likely).
3. **Phase 3 MEGA** — CP-API seeder profile for `e2e-*` tenants. Requires own plan + Council.
