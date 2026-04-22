# CAB-2147 Phase 1.5 — Harness Diagnostic (Console persona auth)

**Date:** 2026-04-22
**Time-box:** 4h hard limit per Council #2 — **investigation read-only, ~1h spent**
**Status:** Partial diagnosis. Full root cause needs interactive debugging (out of read-only scope). Hypotheses ranked + actionable next steps captured.

---

## Symptom recap

In run [24750762663](https://github.com/stoa-platform/stoa/actions/runs/24750762663), 6 unique Console tests render the Keycloak `Login with Keycloak` page instead of the Console shell:

- `Admin accesses tenants page` (anorak)
- `CPI admin can access all admin sections` (anorak)
- `Platform admin views Access Requests page` (art3mis)
- `Tenant admin views AI Tool Catalog` (sorrento)
- `Tenant admin views AI Tool subscriptions` (sorrento)
- `Tenant admin views Applications page` (sorrento)

---

## What works (positive evidence)

### 1. Auth-setup ran successfully for ALL 7 personas in ALL 3 shards

```
✓ authenticate Parzival (parzival) — passed
✓ authenticate Art3mis (art3mis) — passed
✓ authenticate Aech (aech) — passed
✓ authenticate Sorrento (sorrento) — passed
✓ authenticate i-R0k (i-r0k) — passed
✓ authenticate Alex Freelance (alex) — passed
✓ authenticate Anorak (anorak) — passed
```

Source: `jq` over `reports/results.json` for each shard.

### 2. Storage state files contain BOTH OIDC client keys

Captured from auth-setup stdout in shard1 results.json:

```
Storage state saved to fixtures/.auth/anorak.json
(2 OIDC keys: oidc.user:https://auth.gostoa.dev/realms/stoa:control-plane-ui,
              oidc.user:https://auth.gostoa.dev/realms/stoa:stoa-portal)
```

Identical 2-key signature for all 7 personas: `control-plane-ui` (Console client) + `stoa-portal` (Portal client). So the SSO leg in `auth.setup.ts` lines 263-267 succeeded for every persona — the storage states are NOT empty.

### 3. Parzival works on Console

The trace for `Tenant admin creates an API` (uses parzival) shows the Console **shell rendered** with sidebar (Dashboard, APIs, Subscriptions, AI & MCP) — only the "Create API" button is disabled (backend gating). Parzival's storage state restores cleanly. So the restoration mechanism in `test-base.ts` (Playwright `storageState` + `installSessionStorageInitScript`) is functionally correct for at least one persona.

### 4. Project config is correct

`e2e/playwright.config.ts`:
- `console-chromium` project: `dependencies: ['auth-setup']`, `storageState: 'fixtures/.auth/parzival.json'`
- All 7 storage states exist by the time downstream projects start (per dependency declaration)

---

## What breaks (the asymmetry)

| Persona | DefaultApp | Console behavior |
|---------|-----------|------------------|
| parzival | console | ✅ Console shell (auth OK) |
| sorrento | console | ❌ Login screen |
| anorak | console | ❌ Login screen |
| art3mis | portal | ❌ Login screen (Console via SSO) |

Both parzival and sorrento have `defaultApp: 'console'` and both go through the same auth.setup flow (login on Console first, SSO to Portal). Both produce identical-looking storage states. **Yet only Parzival's restores correctly on Console at test time.**

---

## Hypotheses ranked

### H1 — Console UI requires a JWT claim that some personas don't carry — ⭐ MOST LIKELY

Anorak has `tenant: '*'` (`scopes: ['stoa:admin', 'stoa:platform:read', 'stoa:platform:write']`). Sorrento has tenant `ioi`. Parzival has tenant `high-five` AND scopes `['stoa:catalog:*', 'stoa:subscriptions:*']`.

If Console's react-oidc-context user-loaded callback checks for a specific scope (e.g., `stoa:catalog:read`) and treats absence as "not authenticated" → redirect to login. Anorak only has `stoa:admin`, Sorrento has subscription scopes but maybe missing one.

**Verify:** read `control-plane-ui/src/auth/` for any post-login validation that gates on scopes/claims.

### H2 — Cookie-domain mismatch between auth.setup capture and test-time replay

When auth.setup.ts captures `storageState`, it captures cookies for `auth.gostoa.dev`, `console.gostoa.dev`, `portal.gostoa.dev` — whichever the page visited. For personas with `defaultApp: 'portal'` (art3mis, aech, alex), the SSO leg goes Portal → Console. The console.gostoa.dev cookies set during SSO might be flagged `SameSite=Lax` and not get re-sent on a fresh context navigation.

**Verify:** inspect a captured `<persona>.json` (locally, not in CI) and check the cookie list — is there a console.gostoa.dev cookie for art3mis?

### H3 — sessionStorage initScript races with react-oidc-context's auth check

`addInitScript` runs BEFORE `domcontentloaded` event. Console's React app doesn't read sessionStorage until it boots. So the ordering is correct in theory. But if Console is using `lazy()` chunks or async OIDC loading, there may be a brief window where the auth check fires before initScript completes (very edge-case).

**Verify:** add `console.log` inside the initScript and check timing in browser dev tools.

### H4 — KC session cookie expired between auth.setup completion and Console test start

KC's `KEYCLOAK_SESSION` cookie has a default lifetime, but `KEYCLOAK_IDENTITY` is the actual session marker. If it's session-only (no maxAge), Playwright captures it but it gets dropped on context recreation. Then react-oidc-context tries to refresh the access token via the refresh-token grant → KC asks for re-auth → login screen.

**Verify:** check KC cookie expiry in `<persona>.json` for `auth.gostoa.dev` cookies.

### H5 — Token expiry between auth-setup and test execution

Auth-setup runs at job start. Anorak runs LAST (alphabetical insertion order in PERSONAS map). By the time Console tests run minutes later, Anorak's access_token may have hit `exp` (KC default 5min). react-oidc-context tries refresh. **But this should affect Parzival too** (he runs FIRST, his token is OLDEST when tests run). Yet Parzival works. **De-prioritized**.

---

## What I cannot verify read-only

The smoking-gun would be inspecting one persona's actual `<persona>.json` content (cookies + sessionStorage). These are gitignored locally and not uploaded as CI artifacts. To progress:

1. **Run `npx playwright test --project=auth-setup --headed` locally** with `KEYCLOAK_URL=https://auth.gostoa.dev` + the same Vault-fetched persona credentials, then `cat fixtures/.auth/anorak.json | jq` to inspect cookies + sessionStorage.
2. **OR** add a temporary debug step to `auth.setup.ts` that writes a sanitized summary (cookie domains, sessionStorage keys, JWT claims via `jwtDecode(...)`) to a separate JSON file that DOES get uploaded as artifact. This is the cheapest CI-side validation — single file change, one re-run.
3. **OR** patch `test-base.ts` to log the JWT claims of the loaded OIDC user when `switchPersona` runs, so a CI re-run surfaces the difference between parzival (works) and anorak (fails).

---

## Recommendation

**Proceed with Phase 2-3 ASSUMING H1 is the cause** (most likely + addressable in Phase 2 anyway). When provisioning the new e2e personas (per Spike A's Option A3):

- Give every e2e persona at minimum the union of all scopes used in the persona definitions: `['stoa:catalog:read', 'stoa:catalog:write', 'stoa:subscriptions:read', 'stoa:subscriptions:write', 'stoa:admin', 'stoa:platform:read', 'stoa:platform:write']`
- Always emit `tenant_id` claim, even for `e2e-anorak` (set it to `e2e-shared` or `*` depending on what Console accepts)
- Add a smoke test in auth.setup.ts that reads the captured OIDC user's JWT and asserts the expected claims are present — fail loudly if `tenant_id` or required scopes are missing

If H1 is wrong and the issue is H2/H3, the smoke test will surface that during Phase 2 dry-runs, before Phase 3 commits.

**Don't block Phase 2 on full root-cause**. The new e2e personas with proper scope/claim provisioning will likely sidestep H1 entirely. If after Phase 2 the 6 Console-on-login tests still fail, **then** invest in interactive debugging as a separate small ticket.

---

## Time-box accounting

- ~1h spent on read-only artifact analysis + code reading
- 3h remaining in Council #2 budget
- Recommendation: **bank the remaining time** for Phase 2 implementation. Re-allocate to harness if Phase 2 dry-run shows persistent Login-screen issues.

---

## Update 2026-04-22 — H1 verification pass (local JWT inspection)

**Method:** Decoded `oidc.user:...:control-plane-ui` access_token from existing local storage states under `e2e/fixtures/.auth/*.json` (tokens themselves expired Feb 2026, but claim structure is preserved and useful for structural comparison). Also inspected cookie domains and Console auth logic (`control-plane-ui/src/contexts/AuthContext.tsx`).

### Evidence

| Claim | Parzival (works) | Anorak (fails) | Sorrento (fails) | Art3mis (fails) |
|-------|------------------|----------------|------------------|-----------------|
| `preferred_username` | parzival | anorak | sorrento | art3mis |
| `tenant_id` | `oasis` | `oasis` | `ioi` | `oasis-gunters` |
| `scope` | `openid email profile` | `openid email profile` | `openid email profile` | `openid email profile` |
| `realm_access.roles` contains | `tenant-admin, namespace_developer` | `cpi-admin` | `tenant-admin` | `devops, tenant-admin` |
| `aud` | `[control-plane-api, account]` | same | same | same |
| Cookie domains | `auth.gostoa.dev` only | same | same | same |

### Conclusions

1. **H1 significantly weakened.** Claim structure is **identical** across working and failing personas (all have `tenant_id`, `realm_access.roles`, `aud`, valid scopes). Console's `AuthContext.extractUserFromToken` only reads `realm_access.roles` + `profile.sub/email/tenant_id` — all present in all four personas. There is no JWT claim Console gates on that is missing for anorak/sorrento/art3mis but present for parzival.

2. **H2 ruled out.** Storage states for every persona contain ONLY `auth.gostoa.dev` KC cookies (`KEYCLOAK_IDENTITY`, `KEYCLOAK_SESSION`, `AUTH_SESSION_ID`, etc.). No `console.gostoa.dev` or `portal.gostoa.dev` cookies exist for any persona (expected SPA pattern — apps use sessionStorage, not cookies). There is no cookie-domain asymmetry to explain the failure.

3. **H3 (initScript race) + H4 (KC session expiry during CI) + test-time timing remain** the last credible hypotheses. None can be verified read-only from local artifacts alone.

4. **Inconsistent KC state vs personas.ts declarations** — Parzival's JWT says `tenant_id=oasis`, but `personas.ts` declares `tenant: 'high-five'`. Art3mis similarly. This doesn't explain the Login-redirect, but it confirms the test fixtures are decoupled from actual KC state. Worth tracking separately — tests asserting tenant-specific behavior may pass for the wrong reasons.

5. **H5 (token expiry between auth-setup and test) still rejected** — Parzival is auth'd FIRST in CI (highFivePersonas first in PERSONAS map), so his token is the OLDEST at test time. He works anyway.

### New dominant hypothesis set

- **H3 (initScript race)** — plausible mechanism: for personas whose tests call `switchPersona()` (creates a NEW context), the addInitScript hook might not complete before React boots, leaving `sessionStorage` empty at the moment `UserManager.getUser()` runs. Parzival is the default `console-chromium` project storageState, so his tests do NOT call `switchPersona` — they use the default context, where the init script is installed at context creation. This asymmetry is consistent with the observed failures.
- **H6 (new): silent-renew failure for switched contexts** — when switchPersona creates a fresh context, the KC `KEYCLOAK_IDENTITY` cookie may be present but `oidc.signinSilent()` calls `iframe` flow that requires `SameSite` permissive cookies. If KC's `KEYCLOAK_IDENTITY_LEGACY` is `SameSite=None` and the fresh context doesn't restore it correctly, silent-renew fails → `signinRedirect` → Login page.

### Cheapest definitive test

Add ONE diagnostic step to `auth.setup.ts`: after capturing storage state, decode the JWT and write a sanitized `<persona>.jwt-summary.json` (claims only, no token) next to the storage state. Add it to the CI artifact upload. **One CI re-run** gives us every claim Console sees, not the stale local copy. ~15 min of work.

Second diagnostic: in `test-base.ts`, after `switchPersona`, log `oidc.isAuthenticated` and `oidc.isLoading` after 1s wait + 5s wait, to see if H3 timing window is real.

### Verdict for Phase 2

- **Phase 2 JWT-claim assertion mitigation is unlikely to fix the Login-screen issue** on its own (claims are already present).
- Phase 2 should **additionally** include an `installSessionStorageInitScript` synchronization check (e.g., `await page.waitForFunction(() => sessionStorage.getItem('oidc.user:...') !== null)` before first assertion).
- **Do not start Phase 2 without adding the diagnostic artifact first.** 15 min of CI instrumentation saves 6–9 pts of blind Phase 2 execution.
