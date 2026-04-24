# FIX-PLAN — UI-1 Wave 1 all-in-one batch

**Branch**: `fix/ui-1-w1-bug-hunt-batch` (from `main`, TBD — current working branch is `fix/gw-2-bug-hunt-batch`)
**Baseline commit**: current `main` = `80017fb9d` (GW-2 batch merged)
**Scope**: 8 items from `BUG-REPORT-UI-1-W1.md` (2 P1 + 6 P2), one atomic commit, ~2-3h IA-time.
**Gate**: STOP after this plan, await validation before Phase 2.

---

## Pre-analysis (what the grep/tsc/openapi checks tell us)

Results from the scope-estimation greps (Phase 1 diligence — inform arbitrages, not in the commit):

| Check | Result | Implication |
|---|---|---|
| `app.client_id\.` / `application.client_id\.` call sites | **1 unsafe** (`Applications.tsx:197`) + 1 safe render (`Applications.tsx:505`, React tolerates `null`) | P1-A scope contained — 1 guard only. |
| `app.tenant_id\.` call sites on narrowed `Application` | **0** active consumer. Dormant hazard only. | Same-shape fix as client_id, no consumer guard needed today. |
| `api.audience` consumers | 3 sites (`AudienceGovernance.tsx:185/204/207`, `APIDetail.tsx:338`) — **all already guard with `?? 'public'` or `\|\| 'public'`** | Cleanup of ENRICHED `audience?` is safe — code already defensive. |
| `api.created_at` on the `API` alias (not `BackendApi`) | **0** consumers (`BackendApiDetail.tsx:415` uses `BackendApi` local type) | Cleanup of ENRICHED `created_at?` is safe. |
| `gateway.enabled` consumers | 5 sites (`GatewayDetail.tsx:116/165/202/208/228`) | Cleanup of ENRICHED `enabled: boolean` safe because backend has the field with same shape. |
| `shared/package-lock.json` + `cd shared && npm ci --dry-run` | **Clean**, 4 packages added, 0 errors | P1-B is safe to implement. |
| Canonical Schema for P2-D | `Schemas['TransactionDetailWithDemoResponse']` at `openapi-snapshot.json:27071` (required: id/trace_id/api_name/method/path/status_code/status/started_at/total_duration_ms/spans) | P2-D has a real canonical target — unification is possible without manual shape. |
| `CAB-2164 scope verification` | CAB-2164 covers `any` in **`gateways.ts` + `gatewayDeployments.ts` services (17 sites)** — NOT `GatewayDeploymentsDashboard.tsx` (the 3 `as any` on `desired_state`) | P2-E is a separate concern. Option a (local fix) chosen — see B.5. |

tsc baseline: **0 errors** after `cd control-plane-ui && npm ci`. The pre-audit "5 errors in sse.ts" reading was a false measurement taken in a worktree whose `node_modules` had not been installed; the missing-module errors disappear once deps are present. Anchor Phase 2 on the post-install baseline.

---

## A. Ordre d'exécution dans le commit

Sequenced to minimize re-edits on the same file + do triviaux-first so noise stays isolated.

| # | Item | File(s) touched | Scope |
|---|------|----------------|-------|
| 1 | **P2-C** delete dead `RolePermission`/`RoleDefinition` | `types/index.ts` (lines 1381-1397) | -17 LOC, zero dep |
| 2 | **P2-A** clean stale ENRICHED on `API` and `GatewayInstance` | `types/index.ts:51-56` + `1040-1055` | -15 LOC, no consumer breaks (verified above) |
| 3 | **P1-A** honest `client_id`/`tenant_id` typing + guard | `types/index.ts:74-81` + `Applications.tsx:197` | -5/+8 LOC |
| 4 | **P1-B** npm ci in CI workflow | `.github/workflows/api-contract-check.yml:36-38` | 2 lines changed |
| 5 | **P2-F** null-safe `certificate_status` cast | `Consumers.tsx:511,592` + `ConsumerDetailModal.tsx:115` | 3 cast sites → guard |
| 6 | **P2-E** type `GatewayDeployment.desired_state` | `types/index.ts:1095-1116` + `GatewayDeploymentsDashboard.tsx:271,274,310` | New interface + 3 `as any` removed |
| 7 | **P2-D** unify TransactionDetail | `types/index.ts:556-576`, `services/api/monitoring.ts:28-44`, `CallFlow/TraceDetail.tsx:30-49,132` | Biggest refactor — done last before docs |
| 8 | **P2-B** tighten `contract.test.ts` | `control-plane-ui/src/__tests__/contract.test.ts` | 1 test file |
| 9 | **Regression guards** | New tests (see §C) | — |
| 10 | **Docs** update | `rewrite-bugs.md` + `BUG-REPORT-UI-1-W1.md` | — |

Rationale for ordering:
- 1 (P2-C) first: pure deletion, no dep. Isolates easy win.
- 2 (P2-A) before 3 (P1-A): both touch `types/index.ts`. P2-A removes lines around the `API`/`GatewayInstance` intersections; P1-A touches `Application` intersection. Different regions but doing stale cleanup first clarifies P1-A's shape of change.
- 4 (P1-B) standalone — YAML only, commit order-free.
- 5 (P2-F) + 6 (P2-E) small + focused after the type-shape changes.
- 7 (P2-D) last of code changes — biggest cross-file churn; doing it last lets us verify tsc still green with all earlier changes in place.
- 8 (P2-B) at end because the tightened assertion may surface new drifts that require one-shot small fixes (e.g., TS type missing a backend required field we didn't catch).

---

## B. Arbitrages résolus

### B.1 — P1-A : Option 1 (honest `string | null` + guards)

**Decision**: Option 1. Change alias to honest typing.

**Concrete changes**:

```ts
// types/index.ts:74-81 BEFORE
export type Application = Omit<Schemas['ApplicationResponse'], 'client_id' | 'tenant_id'> & {
  client_id: string;
  tenant_id: string;
  environment?: string;
};

// AFTER
export type Application = Schemas['ApplicationResponse'] & {
  /** UI-only field, populated client-side via filters/context. */
  environment?: string;
};
```

Now `Application.client_id` is `string | null` and `Application.tenant_id` is `string | null`, matching the backend contract.

**Call sites to guard** (grep results above):
- `Applications.tsx:197` — change `app.client_id.toLowerCase()` to `(app.client_id ?? '').toLowerCase()` (matches the pattern used at line 195 for `display_name`).
- `Applications.tsx:505` — already safe (React renders `null` as empty).
- No other `client_id.X` call sites in UI sources.
- `app.tenant_id` — zero active call sites, but tsc will complain if any future consumer assumes non-null. That's the design intent — tsc becomes the guard.

**Why Option 1 and not backend fix**: cross-repo scope creep avoided. Backend already made `client_id` "required but nullable" intentionally — UI must honor that.

---

### B.2 — P1-B : `npm ci` substitution

**Verified**: `cd shared && npm ci --dry-run` → `added 4 packages in 191ms, 0 errors`. Safe.

**Change to `.github/workflows/api-contract-check.yml:36-38`**:

```yaml
# BEFORE
- name: Install openapi-typescript
  working-directory: shared
  run: npm install --no-save openapi-typescript

# AFTER
- name: Install shared deps (lockfile-enforced)
  working-directory: shared
  run: npm ci
```

The `openapi-typescript` dep is already in `shared/devDependencies` (package.json line 20 : `"openapi-typescript": "^7.13.0"`). `npm ci` honors the lockfile, installs it, removes CI drift risk.

**No other change needed**: the rest of the workflow uses `npx openapi-typescript` which will resolve the locally-installed version from `node_modules/.bin`.

---

### B.3 — P2-A cleanup ENRICHED

All three cleanups are safe per pre-analysis consumer checks. Concrete changes:

**`types/index.ts:51-56` (API)**:

```ts
// BEFORE
export type API = Schemas['APIResponse'] & {
  openapi_spec?: string | Record<string, unknown>;
  audience?: 'public' | 'internal' | 'partner';
  created_at?: string;
  updated_at?: string;
};

// AFTER
export type API = Schemas['APIResponse'] & {
  /** Backend exposes OpenAPI spec through a separate endpoint. UI stashes it here when fetched. */
  openapi_spec?: string | Record<string, unknown>;
};
```

Rationale: `audience`/`created_at`/`updated_at` are now in `Schemas['APIResponse']` post-CAB-2159. `openapi_spec` is genuinely UI-side (separate fetch path per `rewrite-bugs.md` BUG-4).

**`types/index.ts:1040-1055` (GatewayInstance)**:

```ts
// BEFORE — 16 lines with Omit + re-add + 4 ENRICHED fields
export type GatewayInstance = Omit<
  Schemas['GatewayInstanceResponse'],
  'gateway_type' | 'mode' | 'status'
> & {
  gateway_type: GatewayType;
  mode?: GatewayMode;
  status: GatewayInstanceStatus;
  enabled: boolean;
  source?: 'argocd' | 'self_register' | 'manual';
  visibility?: { tenant_ids: string[] } | null;
  ui_url?: string | null;
};

// AFTER
export type GatewayInstance = Schemas['GatewayInstanceResponse'];
```

Rationale:
- Backend now emits `gateway_type`/`mode`/`status` as proper enums (verified in snapshot) — the UI literal unions match.
- `enabled`/`source`/`visibility`/`ui_url` all declared in backend schema.
- Result: `GatewayInstance` is a pure alias. The UI-only `GatewayType`/`GatewayMode`/`GatewayInstanceStatus` type literals in the file (lines 1015-1026) remain useful for discriminator guards and can stay.

**Cross-check after cleanup**: grep consumers that do e.g. `instance.source === 'self_register'` — backend emits exact same enum, so compatible. `gateway.enabled` sites (GatewayDetail.tsx) remain valid because backend has `enabled: boolean` as well.

---

### B.4 — P2-D : unify on `Schemas['TransactionDetailWithDemoResponse']`

**Canonical schema verified**: `openapi-snapshot.json:27071-27225`. Required fields: `id, trace_id, api_name, method, path, status_code, status, started_at, total_duration_ms, spans`.

**Concrete strategy**:

1. Update `services/api/monitoring.ts:28-44`:
   ```ts
   // BEFORE
   export interface MonitoringTransactionDetail extends MonitoringTransaction { ... }
   // AFTER
   export type MonitoringTransactionDetail = Schemas['TransactionDetailWithDemoResponse'];
   ```
   (Keep `MonitoringTransaction` for the list endpoint if it's a different schema — verify list endpoint canonical schema when touching; if same, collapse too.)

2. Update `CallFlow/TraceDetail.tsx:30-49` — **delete the local `TransactionDetail` interface entirely**. Import `MonitoringTransactionDetail` from `../../services/api/monitoring`.

3. `CallFlow/TraceDetail.tsx:132` — drop `as unknown as TransactionDetail` cast. `apiService.getTransactionDetail` is already typed `Promise<MonitoringTransactionDetail>` — just return.

4. Update `types/index.ts:556-576` (`APITransaction`) — **verify alignment with canonical** first:
   - If used only for `/v1/monitoring/transactions` LIST view (which uses a different schema), keep but re-align with that schema.
   - If it's a dead duplicate of `MonitoringTransactionDetail`, delete.

**Decision on APITransaction**: inspect during Phase 2. If backend has a `TransactionListResponse.items[number]` schema reusable, canonicalize. If not, keep `APITransaction` but add `// DRIFT: awaiting backend schema extraction` marker. Don't over-scope.

**Risk mitigation**: run tsc after each sub-step (monitoring.ts → TraceDetail.tsx → types/index.ts) to catch consumer breakage incrementally.

---

### B.5 — P2-E : Option a (local fix)

**Decision**: Option a. Type the field locally, remove the 3× `as any`.

**Rationale**:
- Scope is ~20 LOC (one new interface + 3 line changes in the consumer).
- CAB-2164 covers the **17 `any` in `gateways.ts`/`gatewayDeployments.ts` services**, not the `desired_state` field in the data shape — different concern.
- Mixing dilutes both: CAB-2164's scope stays clean on `any` in service wrappers, this commit closes the `desired_state` shape gap.
- Backend schema verification: `GatewayDeployment.desired_state` is declared `Record<string, unknown>` currently (no backend change to await). UI types what it observes.

**Concrete changes**:

```ts
// types/index.ts — add near GatewayDeployment interface
export interface GatewayDeploymentDesiredState {
  api_name?: string;
  tenant_id?: string;
  // add fields as they're used; start with the two observed in consumers
  [key: string]: unknown; // forward-compat for backend additions
}

// Modify GatewayDeployment.desired_state field:
// BEFORE: desired_state: Record<string, unknown>;
// AFTER:  desired_state: GatewayDeploymentDesiredState;
```

```ts
// GatewayDeploymentsDashboard.tsx
// BEFORE (lines 271, 274, 310)
{(dep.desired_state as any)?.api_name || dep.api_catalog_id.slice(0, 8)}
{(dep.desired_state as any)?.tenant_id || '-'}
handleUndeploy(dep.id, (dep.desired_state as any)?.api_name)

// AFTER
{dep.desired_state.api_name || dep.api_catalog_id.slice(0, 8)}
{dep.desired_state.tenant_id || '-'}
handleUndeploy(dep.id, dep.desired_state.api_name)
```

Typed access; index signature keeps forward-compat if backend adds fields. The `|| fallback` idiom stays — runtime safety unchanged.

---

### B.7 — P2-F : explicit `?? undefined` coercion

**Decision**: coerce, don't widen.

The target component `CertificateHealthBadge` accepts `status?: CertificateStatus` (undefined-tolerant). The current cast `consumer.certificate_status as CertificateStatus` tries to make `string | null` fit — but `null` is not a valid `CertificateStatus` at any time.

**Concrete change at `Consumers.tsx:511`, `Consumers.tsx:592`, `ConsumerDetailModal.tsx:115`**:

```ts
// BEFORE
status={consumer.certificate_status as CertificateStatus}

// AFTER (coerce null → undefined, narrow string-with-valid-value via type guard)
status={normalizeCertificateStatus(consumer.certificate_status)}
```

Where `normalizeCertificateStatus` is a tiny helper (colocated in `types/index.ts` or `src/utils/certificates.ts` if it exists):

```ts
export function normalizeCertificateStatus(
  value: string | null | undefined
): CertificateStatus | undefined {
  if (value === 'active' || value === 'rotating' || value === 'revoked' || value === 'expired') {
    return value;
  }
  return undefined;
}
```

Rationale: a backend value outside the four known statuses now coerces to `undefined` cleanly (no silent `null` flowing into component logic). No widening of the component contract. No blind cast.

---

### B.6 — P2-B : contract test tightening

**Decision**: tighten, but keep minimal-invasive.

**Concrete changes to `src/__tests__/contract.test.ts`**:

1. Keep explicit property lists (runtime `keyof` is unavailable — TS types are erased at runtime). Instead, **align the lists with the current TS declarations** and add a dedicated `expectTypeOf` compile-time check for a subset of critical aliases (`Tenant`, `GatewayInstance`, `Application` after P1-A honest-typing). Runtime test keeps declarative coverage + compile test anchors the TS shape.

2. Replace line 112 threshold:
   ```ts
   // BEFORE
   expect(covered.length).toBeGreaterThanOrEqual(Math.min(required.length, 3));
   // AFTER
   expect(covered).toEqual(required); // full coverage, exact match
   ```

3. Add a **new soft-check** (warn-only, not assertion) that lists backend-side properties NOT covered by the TS side, to surface drifts without breaking CI on benign additions:
   ```ts
   const apiOnly = apiProps.filter((p) => !tsProperties.includes(p));
   if (apiOnly.length > 0) {
     console.warn(`[contract drift] ${schemaName}: TS does not declare: ${apiOnly.join(', ')}`);
   }
   ```

Risk: tightening to `toEqual(required)` may surface real gaps we didn't catch. If the tightening fails on a schema (e.g. backend added a required field we missed), either add to TS type or demote specific schema with an explicit `// KNOWN: not yet migrated (W2)` marker. No silent relaxation.

---

## C. Régression guards

New test files, each with the `// regression for CAB-XXXX` marker on a standalone line (CAB-2159-like pattern):

1. **`src/__tests__/regression/UI1-W1-application-client-id-null.test.tsx`**:
   - Render `Applications` list with mocked query returning `[{ ..., client_id: null }]`
   - Type search text in the search input
   - Assert: no crash, filter excludes the null-client_id row from search matches (or includes via display_name match)
   - `// regression for UI-1 W1 P1-A`

2. **`src/__tests__/regression/UI1-W1-contract-full-coverage.test.ts`**:
   - Extend contract test: assert `TenantResponse`, `ApplicationResponse`, `APIResponse`, `GatewayInstanceResponse` have **all** their `required[]` covered by the UI type.
   - `// regression for UI-1 W1 P2-B`

3. **`src/__tests__/regression/UI1-W1-desired-state-typed.test.ts`**:
   - TypeScript-level: `expectTypeOf<GatewayDeployment['desired_state']>().toMatchTypeOf<GatewayDeploymentDesiredState>()`.
   - Runtime: build a `GatewayDeployment` with `desired_state: { api_name: 'x', tenant_id: 'y' }`, assert typed access works.
   - `// regression for UI-1 W1 P2-E`

4. **Smoke tsc** (no dedicated test, checked in CI via existing type-check step): post-commit `tsc -p tsconfig.app.json --noEmit` must stay at exactly 5 sse.ts errors. Any new error = commit reject.

Total: 3 new regression tests, all under 40 LOC each.

---

## D. Risques identifiés (updated with pre-analysis)

| Risk | Likelihood | Mitigation |
|---|---|---|
| **P1-A scope explosion** (multiple call sites to guard) | ✅ **Low** — pre-analysis showed 1 unsafe call site | N/A |
| **P2-A breaking a silent consumer** of ENRICHED fields | ✅ **Low** — pre-analysis showed all consumers already defensive or absent | tsc catches any missed case during Phase 2 |
| **P2-D unification masks real divergence** | Medium — 3 types exist, may have diverged for valid reasons | Inspect APITransaction usage during Phase 2, document canonical choice, don't force-collapse without verifying the list endpoint schema |
| **P1-B CI immediate failure post-merge** | ✅ **Low** — `npm ci --dry-run` succeeds locally | Run `npm ci` in CI workflow against a PR before merge |
| **P2-B tightening surfaces unknown gaps** | Medium — we don't know what's missing | Treat as discovery: if a schema fails the tight assertion, decide per-schema (fix TS type, or `// KNOWN` skip with ticket). No merge with silent skip. |
| **P2-E `desired_state` index signature too permissive** | Low — index signature `[key: string]: unknown` means any typo-access compiles | Document that only `api_name`/`tenant_id` are guaranteed; add lint rule or clearer type later |

No risk classified as **High** after pre-analysis. The biggest unknown is P2-B tightening — that's a controlled discovery, not a blind risk.

---

## E. Commit message (draft)

```
fix(ui-1): close UI-1 Wave 1 bug hunt batch (8 items)

Final UI-1 W1 hardening after CAB-2159 backend fixes landed (2026-04-22,
commit c6abef8f2). Closes the 8 findings in BUG-REPORT-UI-1-W1.md.

P1 fixes (runtime correctness):
- P1-A: honest client_id/tenant_id: string | null typing on Application
  alias (matches backend ApplicationResponse). Guard added at
  Applications.tsx:197 (`(app.client_id ?? '').toLowerCase()`, matches
  the pattern already used for display_name on line 195). tsc enforces
  guards at every future call site.
- P1-B: `npm ci` replaces `npm install --no-save` in
  api-contract-check.yml. Lockfile now enforced — eliminates spurious
  red CI on PRs unrelated to shared/ whenever openapi-typescript
  releases a minor/patch.

P2 fixes (drift + dead code + test strength):
- P2-A: remove stale ENRICHED intersections. API alias reduced to
  Schemas['APIResponse'] + openapi_spec (separate endpoint).
  GatewayInstance becomes a pure Schemas['GatewayInstanceResponse']
  alias — all narrowing/re-adds were redundant post-CAB-2159.
- P2-B: contract.test.ts tightened. Full required[] coverage enforced
  (was: min(required, 3) cap, rubber-stamp). Soft warnings surface TS
  gaps on backend-only properties.
- P2-C: delete dead RolePermission + RoleDefinition types. Backend
  emits RoleDetail.permissions: string[], no UI consumer exists.
- P2-D: unify on Schemas['TransactionDetailWithDemoResponse']. Drop
  local TransactionDetail interface in TraceDetail.tsx. Drop
  `as unknown as` cast at TraceDetail.tsx:132. MonitoringTransactionDetail
  becomes a Schemas alias.
- P2-E: type GatewayDeployment.desired_state with explicit
  GatewayDeploymentDesiredState interface. Remove 3× `as any` in
  GatewayDeploymentsDashboard.tsx. (Separate scope from CAB-2164 which
  tracks `any` in gateways.ts/gatewayDeployments.ts services.)
- P2-F: null-safe certificate_status cast. Widen prop or explicit
  undefined coercion at 3 call sites.

Regression guards:
- UI1-W1-application-client-id-null.test.tsx (runtime null-safety)
- UI1-W1-contract-full-coverage.test.ts (required[] coverage)
- UI1-W1-desired-state-typed.test.ts (typed access no any)

Docs:
- rewrite-bugs.md: BUG-1 + BUG-2 marked RÉSOLU (CAB-2159 merged
  2026-04-22). BUG-4 partial (audience/created_at/updated_at resolved;
  status stringy + openapi_spec separate endpoint remain). BUG-3
  unchanged (16+ dupe operationIds — worse than reported; @ts-nocheck
  still required). BUG-5 design-shift documented (backend emits
  string[], not {name, description}).
- BUG-REPORT-UI-1-W1.md: "UI-1 W1 CLOSED" section. 8/8 findings
  resolved.

Module UI-1 Wave 1 CLOSED.

Closes: P1-A, P1-B, P2-A, P2-B, P2-C, P2-D, P2-E, P2-F
(BUG-REPORT-UI-1-W1.md)
```

---

## F. Validation gate — BEFORE Phase 2

The following arbitrages are decided in this plan and DO NOT need further user input:
- ✅ B.1 P1-A: Option 1 (honest typing)
- ✅ B.2 P1-B: `npm ci`
- ✅ B.3 P2-A: full cleanup of stale ENRICHED on API + GatewayInstance
- ✅ B.4 P2-D: canonicalize on `Schemas['TransactionDetailWithDemoResponse']` (with APITransaction inspection during Phase 2)
- ✅ B.5 P2-E: Option a (local fix, not deferred)
- ✅ B.6 P2-B: tighten to full coverage + soft-warn on TS-gaps

**Items that need user confirmation**:
1. ❓ Branch strategy: create `fix/ui-1-w1-bug-hunt-batch` from `main` (fresh rebase, post-GW-2 merge) — or stack on current branch? Current working branch is `fix/gw-2-bug-hunt-batch` with 5 untracked files including this plan.
2. ❓ Scope of P2-D: should `APITransaction` in `types/index.ts:556-576` be collapsed if aligned with another canonical schema, or kept as-is with a `// DRIFT` marker pending backend extraction of the list schema? (Default: inspect during Phase 2, choose conservatively.)
3. ❓ Rotate docs file name: should `rewrite-bugs.md` be renamed to `REWRITE-BUGS.md` to match the UI-2 precedent? (Default: leave as-is, avoid scope creep.)

**STOP. Await validation on branch strategy + P2-D scope boundary before proceeding to Phase 2.**
