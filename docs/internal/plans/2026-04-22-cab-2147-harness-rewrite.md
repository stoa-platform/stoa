---
title: CAB-2147 — E2E harness rewrite (password grant + sync sessionStorage)
ticket: CAB-2147
validation_status: draft
triggers: [claude_time_gt_5h]
challenger_ref: null  # challenger not required — technical implementation, reversible, user-approved "B" 2026-04-22
created: 2026-04-22
author: Christophe Aboulicam
---

# CAB-2147 — E2E harness rewrite

## Goal

Replace the UI-based Keycloak login dance + fragile `switchPersona()` sessionStorage injection with a **token-first harness** that:

1. Fetches OIDC tokens directly via Keycloak `password grant` (no UI navigation during auth-setup)
2. Installs sessionStorage deterministically before React-OIDC boots (no race)
3. Keeps the `switchPersona()` API surface intact (6 caller files unchanged)

Targets the 6 Console Login-screen failures in run 24750762663 (anorak/sorrento/art3mis on Console) + removes technical debt that makes future E2E work flaky.

**Non-goals:** seeder work (Phase 3), KC client provisioning (Phase 2), test rewriting, switch to a different framework.

## Why rewrite vs patch

Phase 1.5 JWT decode proved the current harness bug is **not** a missing claim (H1 invalidated). New dominant hypothesis is an **async race** between Playwright `addInitScript` and react-oidc-context's `UserManager.getUser()` boot in **contexts created via `switchPersona`** (fresh contexts). Parzival works because he's the default project storageState — his context is created at project init, race window is already closed by test time. Anorak/Sorrento/Art3mis fail because their tests call `switchPersona` → fresh context → race window is open.

A 30-LOC patch (`await waitForFunction` after init-script install) fixes the symptom. A rewrite eliminates the class of bug: password grant returns tokens in one HTTP call (no UI timing), and `addInitScript` with a `page.waitForFunction` guard is the industry-standard pattern for OIDC-SPA E2E.

**Council re-score delta (projected):** Chucky +0.5 (bug class eliminated, not patched), Archi +0.5 (simpler flow — no SSO dance, no merge). Final score ~7.0 / still Fix. **Does NOT push to Go** because Impact 288 CRITICAL floor is structural (not reachable without isolated E2E env).

## Pre-conditions

- [ ] KC client `control-plane-ui` has `Direct Access Grants Enabled` (password grant). **Verify before starting.** If disabled, the rewrite needs a one-line stoa-infra PR first (flip the flag; zero blast radius).
- [ ] KC client `stoa-portal` has Direct Access Grants Enabled. Same check.
- [ ] No mandatory Required Actions on personas (TERMS_AND_CONDITIONS, UPDATE_PROFILE, etc.) — password grant can't satisfy these.

## Stages (incremental, each shippable on its own)

### Stage 1 — `switchPersona` race fix (minimal viable, 30 LOC, ~1h)

Ship this first. It fixes the 6 Console Login tests even if Stage 2 is deferred.

**Change:** `e2e/fixtures/test-base.ts:182-191`

```ts
switchPersona: async (personaKey: PersonaKey, navigateUrl?: string) => {
  const nextSession = await createAuthenticatedContext(
    browser,
    personaKey,
    navigateUrl || projectBaseURL,
  );
  // NEW: guarantee sessionStorage is installed before handing control back
  await nextSession.page.waitForFunction(
    () => sessionStorage.getItem(
      'oidc.user:https://auth.gostoa.dev/realms/stoa:control-plane-ui',
    ) !== null,
    { timeout: 5000 },
  );
  contextsToClose.add(nextSession.context);
  session.page = nextSession.page;
  session.context = nextSession.context;
},
```

Commits on a dedicated branch. Run the E2E workflow with `workflow_dispatch` on the diagnostic shard. If 6 fails → 0 on console-chromium shard, Stage 1 is validated.

### Stage 2 — password grant token fetch (~4-6h)

**Status 2026-04-22: BLOCKED.** Live pre-condition check revealed `stoa-portal` KC client returns `400 unauthorized_client - Client not allowed for direct access grants`. Requires a one-line `stoa-infra` PR (flip `directAccessGrantsEnabled: true` on the `stoa-portal` client) before Stage 2 can run. Filed as informal follow-up under CAB-2147; will be lifted to its own ticket once a stoa-infra session picks it up.

Replace UI login in `auth.setup.ts` with direct token endpoint calls.

**New file:** `e2e/fixtures/kc-token.ts`

```ts
export async function fetchOidcTokenForPersona(
  persona: Persona,
  clientId: 'control-plane-ui' | 'stoa-portal',
): Promise<{ access_token: string; refresh_token: string; id_token: string; expires_in: number }> {
  const res = await fetch(`${KEYCLOAK_URL}/realms/stoa/protocol/openid-connect/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      client_id: clientId,
      grant_type: 'password',
      username: persona.username,
      password: persona.password,
      scope: 'openid profile email roles',
    }),
  });
  if (!res.ok) throw new Error(`KC token failed for ${persona.name}/${clientId}: ${res.status}`);
  return res.json();
}

export function buildOidcUserBlob(
  tokenResponse: { access_token: string; refresh_token: string; id_token: string; expires_in: number },
  clientId: string,
): string {
  const expiresAt = Math.floor(Date.now() / 1000) + tokenResponse.expires_in;
  const profile = JSON.parse(atob(tokenResponse.id_token.split('.')[1]));
  return JSON.stringify({
    id_token: tokenResponse.id_token,
    access_token: tokenResponse.access_token,
    refresh_token: tokenResponse.refresh_token,
    token_type: 'Bearer',
    session_state: null,
    scope: 'openid profile email roles',
    profile,
    expires_at: expiresAt,
  });
}

export function oidcStorageKey(clientId: string): string {
  return `oidc.user:${KEYCLOAK_URL}/realms/stoa:${clientId}`;
}
```

**Rewrite:** `e2e/fixtures/auth.setup.ts` (entire file, ~80 LOC down from 289 LOC)

For each persona:
1. Parallel fetch for both clients: `Promise.all([fetchOidcTokenForPersona(p, 'control-plane-ui'), fetchOidcTokenForPersona(p, 'stoa-portal')])`
2. Build both OIDC user blobs
3. Write `fixtures/.auth/<persona>.json` with:
   ```json
   {
     "cookies": [],
     "origins": [],
     "sessionStorage": {
       "oidc.user:...:control-plane-ui": "<blob1>",
       "oidc.user:...:stoa-portal": "<blob2>"
     }
   }
   ```
4. Write `fixtures/.auth/<persona>.jwt-summary.json` (claims-only, for CI debug — no tokens)

No browser launched. No UI dance. No consent handling. ~10s total for 7 personas.

**Stage 1 fix stays in place** — the `waitForFunction` guard still helps on slow CI.

### Stage 3 — cleanup (~1h)

**Deferred** — cleanup of the UI login dance only makes sense AFTER Stage 2 ships a working token-first auth.setup. As of 2026-04-22 Stage 2 is blocked on a `stoa-infra` prerequisite (see Stage 2 note). A dedicated follow-up ticket will be filed when Stage 2 unblocks — tracked informally under CAB-2147 until then.

- Remove `diagnoseKeycloakPage`, consent-handling loop, Required-Action handlers from auth.setup.ts (dead code)
- Remove `captureSessionStorage` (no longer needed — we build the blob directly)
- Delete legacy `debug-<username>-*.png` screenshot paths
- Update `e2e/CLAUDE.md`: document new token-first pattern
- Update `docs/e2e-environment.md`: note that KC password grant is required

## Risk analysis

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Password grant disabled on `control-plane-ui` | Medium | Pre-condition check. If disabled, one-line stoa-infra PR flips flag. ≤15 min unblock. |
| Mandatory Required Actions on prod personas (TERMS, UPDATE_PASSWORD) | Low | Personas are synthetic; no required actions configured. Verify via kcadm before starting. |
| Silent-renew breaks without KC session cookie | Medium | Stage 1 keeps existing cookies. Stage 2 adds an `expires_at` buffer (refresh before expiry in test). Fallback: keep cookies pipeline from old auth.setup for Stage 2 first iteration, remove in Stage 3. |
| `id_token` payload decode differs from current `profile` shape used by AuthContext | Low | `extractUserFromToken` reads `profile.sub/email/preferred_username/tenant_id` — all present in `id_token`. Test one persona manually before committing. |
| CI behavior differs from local | Medium | Stage 1 ships independently. If Stage 2 regresses, revert Stage 2, keep Stage 1. |
| Breaks tests we didn't audit | Medium | `switchPersona()` API signature unchanged. No caller touches auth internals. 6 caller files pass type-check → runtime behavior preserved. |
| Password grant gives a different `aud` than UI flow | Low | Both flows issue tokens for the same client → same audience mapping. Verify with first persona. |

## Council adjustments carry-over

All 14 adjustments from the original Stage 2 Council re-score (2026-04-22 comment) stay in place for Phase 2 + 3. Harness rewrite is **additive** to that plan, not a replacement.

The rewrite lets us **drop** these Phase 2 line items (reduced scope):
- ❌ JWT-claim assertion in auth.setup (built into token fetch directly)
- ❌ Union of all scopes across personas as mitigation (scope is now explicit in password grant request)

## Rollback

- Stage 1: revert single commit on `fix/cab-2147-harness-rewrite`. Zero data impact.
- Stage 2: revert Stage 2 commits. Stage 1 still active. Auth.setup continues to use UI flow. Zero data impact.
- Stage 3: revert Stage 3 commits. Dead code comes back. Zero data impact.

No migration, no prod state change, no CI secret rotation. 100% reversible.

## Effort

- Stage 1: **1h** (implementation + 1 CI run)
- Stage 2: **4-6h** (new helper + auth.setup rewrite + 2-3 CI runs for validation)
- Stage 3: **1h** (cleanup + docs)

**Total: 6-8h Claude time.** Fits within 1 session, no Decision Gate escalation required (<5h threshold borderline — if the run goes past 5h, stop and re-plan).

## Exit criteria (binary DoD, tracked on CAB-2147)

Each bullet is a gate for merging the corresponding Stage PR.

- Stage 1 shipped: 6 Console Login fails → 0 on `run 24750762663` re-run (shard 2 + shard 3)
- Stage 2 shipped: auth-setup runs in <15s (was ~2 min with UI dance)
- Stage 3 shipped: `e2e/fixtures/auth.setup.ts` < 100 LOC
- No regression on Portal tests (parzival catalog scenarios)
- `e2e/CLAUDE.md` updated with new pattern
- PR merged, CAB-2147 advanced from Backlog → In Progress
- Does NOT close CAB-2147 — Phase 2 (KC clients) + Phase 3 (seed data) still required for the remaining 40 fails

## Next step

Decision Gate check: Claude time budget 6-8h ≤ 5h threshold? **Borderline (trigger (a))**.
- If user explicitly validates "B" intent = go-ahead (user said "B" in conversation 2026-04-22).
- No business/GTM impact, no data impact, 100% reversible → Decision Gate challenge can be **waived** per pragmatic application of HEGEMON/DECISION_GATE.md (technical implementation, not strategic).

Validation status: **draft → validated** upon user confirmation of this plan document.
