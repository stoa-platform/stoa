# BUG-REPORT — UI-1 Wave 1 (Shared types / OpenAPI source of truth)

**Module**: `shared/api-types/` + consumers in `control-plane-ui/src/` and `portal/src/`
**Scope**: Wave 1 rewrite (5 entities migrated, ENRICHED pattern, `// @ts-nocheck` workaround)
**Audit date**: 2026-04-24
**Method**: phase-audit only — no fixes applied.
**Baseline**: `tsc -p control-plane-ui/tsconfig.app.json --noEmit` = 0 errors (once deps are installed via `npm ci`). Portal `tsc` = 0 errors. The pre-audit measurement of 5 errors was a false reading taken before running `npm ci` in a fresh worktree.

---

## Executive summary

Findings: **7 bugs** (2 P1, 5 P2). No P0. Module is **light** as predicted — most of what W1 touched is covered by `tsc`, so runtime hazards are scarce.

| P | Count | Theme |
|---|-------|-------|
| P0 | 0 | — |
| P1 | 2 | Narrowing-without-guard runtime crash + non-deterministic CI drift gate |
| P2 | 5 | Redundant workarounds, weak contract test, optionality drift, test-time `as unknown as` hiding drift |

Backend CAB-2159 (merged 2026-04-22) **resolved BUG-1, BUG-2, and the `audience`/`created_at`/`updated_at` part of BUG-4** — but the UI still carries **stale workarounds** that now disagree with the canonical schema. BUG-3 (`operationId` dupes) is **worse**: 16+ duplicate operationIds now in the snapshot (vs 11 in the original report). `@ts-nocheck` is still required.

**Most urgent single fix**: P1-A (`Application.client_id` narrowed to `string` triggers runtime crash in `Applications.tsx:197`).

---

## Critical (P0)

_None._

---

## High (P1)

### P1-A — `Application.client_id` narrowing triggers `TypeError` on search

**File**: `control-plane-ui/src/types/index.ts:74-81` + consumer `control-plane-ui/src/pages/Applications.tsx:197`
**Category**: A (typing) + E (nullish) — **runtime crash**.

The UI alias narrows `client_id: string | null` → `client_id: string` via intersection **without a runtime guard**:

```ts
// types/index.ts:74-81
export type Application = Omit<Schemas['ApplicationResponse'], 'client_id' | 'tenant_id'> & {
  /** UI assumes always set (BUG-1: backend should make it required). */
  client_id: string;
  tenant_id: string;
  environment?: string;
};
```

Backend contract (`openapi-snapshot.json:1472-1481`) declares `client_id` as required but `anyOf: [string, null]`. The comment at line 75 says "UI assumes always set" — that assumption is never enforced and the backend can legitimately emit `null` (e.g., a freshly-created application before OAuth client provisioning).

**Reproduction**:
`Applications.tsx:197`:
```ts
app.client_id.toLowerCase().includes(searchLower)
```
If any row in the list has `client_id: null`, the search filter throws `TypeError: Cannot read properties of null (reading 'toLowerCase')`. tsc cannot catch it because the type lies.

Note: `Applications.tsx:195` already defends the optional `display_name` with `(app.display_name || '')`. The same guard is missing on `client_id` — which was deliberately typed as non-nullable.

`Applications.tsx:505` renders `{app.client_id}` — React renders `null` as empty (not a crash).

**Fix direction (for separate ticket)**: either (a) change alias to `client_id: string | null` + guard at all call sites (honest), or (b) backend makes `client_id` truly non-nullable (then drop the `Omit`-and-re-add). The comment "UI assumes always set" is the smoking gun: the lie is intentional but unguarded.

**Parallel dormant hazard**: same narrowing exists for `tenant_id` (same intersection). No active consumer does `.foo()` on `application.tenant_id`, so it's not exploding — but the same pattern will bite when any new consumer appears.

---

### P1-B — Drift-gate CI ignores the `shared/` lockfile (non-deterministic)

**File**: `.github/workflows/api-contract-check.yml:36-38`
**Category**: C (pipeline) — **false-positive CI failures possible on unrelated PRs**.

```yaml
- name: Install openapi-typescript
  working-directory: shared
  run: npm install --no-save openapi-typescript
```

`shared/package-lock.json` exists (`lockfileVersion: 3`) and locks a specific `openapi-typescript` version. `npm install --no-save openapi-typescript` **bypasses the lockfile** and resolves the latest version matching `^7.13.0` from `package.json`. Local developers running `npm run generate:api-types` hit their cached resolved version; CI pulls the latest-at-run-time. If openapi-typescript releases 7.14.x with ANY output-format change (whitespace, ordering, comment), CI would:
1. Produce a different `/tmp/generated-check.ts` than the committed `shared/api-types/generated.ts`.
2. The `diff -q` gate at line 46 fails.
3. The PR — which touched nothing in `shared/` — turns red.

The fix is `npm ci` inside `shared/` (honors lockfile) plus dropping `--no-save`. The `shared/package.json` already lists `openapi-typescript` as a devDep — `npm ci` installs it.

Secondary concern: the same drift can happen locally between developers running `generate:api-types` with different cached versions, silently producing a diff during review.

**Reproduction**: tag a new openapi-typescript patch in npm (or rebase after one lands upstream). CI goes red on every subsequent PR until someone regenerates — even though no contributor broke the contract.

---

## Medium (P2)

### P2-A — Stale workarounds in ENRICHED types disagree with post-CAB-2159 schema

**File**: `control-plane-ui/src/types/index.ts:51-56` (`API`), `1040-1055` (`GatewayInstance`)
**Category**: A (typing) + F (W1/W2 compat).

Backend PR #2473 (`c6abef8f2`, merged 2026-04-22) closed BUG-1/BUG-2/half of BUG-4 — the UI file still carries the pre-fix shims. Concrete mismatches **today**:

1. **`API.created_at?: string` (line 54) vs backend `created_at: string | null`** (openapi-snapshot.json:454-464).
   Intersection result: `(string | null) & (string | undefined) = string`. The UI type lies about non-nullability. No current consumer of the `API` alias reads `created_at`, so dormant. If someone wires up "Updated {new Date(api.created_at).toLocaleDateString()}" (pattern already present for `BackendApi` at `BackendApiDetail.tsx:415`), backend `null` → `new Date(null).toLocaleDateString()` → `"Invalid Date"` (no crash but wrong display).
2. **`API.audience?: 'public' | 'internal' | 'partner'` (line 53)** — now **redundant**. Backend has `audience: enum(...)` with default 'public', so `Schemas['APIResponse']['audience']` is already `'public' | 'internal' | 'partner'`. The intersection adding `?:` is a no-op / actively loses information about nullability vs default handling.
3. **`GatewayInstance.mode?: GatewayMode` (line 1044)** — backend schema: `mode` is **required** with type `GatewayMode | null` (openapi-snapshot.json:11528-11546, listed in `required` at line 11662). UI marks it optional. Consumers using `if (instance.mode == null)` work for both; consumers using `'mode' in instance` always hit true at runtime; consumers using the object-spread default (`mode: GatewayMode = 'edge-mcp'` via `...instance`) get `null` not `'edge-mcp'`.
4. **`GatewayInstance.enabled: boolean` (line 1048)** — now redundant (backend has it at line 11474). The intersection ENRICHES a field the backend already emits.
5. **`GatewayInstance.source?: 'argocd' | 'self_register' | 'manual'`** — now redundant (backend enum at line 11569).

These are "dormant" in the sense that tsc won't scream, but they signal a stale file. Removal belongs to UI-1 Wave 2 per the rewrite-bugs.md sunset section. **Not a runtime bug today — medium because it weakens the source-of-truth contract**.

---

### P2-B — Contract test is one-way + hardcoded → rubber-stamp

**File**: `control-plane-ui/src/__tests__/contract.test.ts`
**Category**: G (drift gate).

Two weaknesses:

1. **Hardcoded property lists (lines 47-87)** are not introspected from actual TS types. If someone renames `tenant_id → tenantId` in `src/types/index.ts`, the test never sees it.
2. **Line 112**: `expect(covered.length).toBeGreaterThanOrEqual(Math.min(required.length, 3))`. Coverage threshold capped at 3 — if backend adds a 4th, 5th, 6th required field, the assertion still passes because it only needs 3.

Example pass-through: a backend PR adding `required: [...old, 'compliance_tier']` to `TenantResponse` would silently ship to prod without UI seeing the field. Since we already saw this exact class of drift in BUG-2/BUG-4 originally, the contract test would not have caught it.

No exploit today, but the test gives false confidence. Tightening (pull properties from `expectTypeOf<Tenant>()`-derived keys, require full coverage of `required[]`) is low-effort.

---

### P2-C — `RoleDefinition.permissions: RolePermission[]` disagrees with backend `permissions: string[]`

**File**: `control-plane-ui/src/types/index.ts:1381-1397`
**Category**: F (W1/W2 compat).

```ts
export interface RolePermission { name: string; description: string; }
export interface RoleDefinition {
  // ...
  permissions: RolePermission[];  // expects rich objects
}
```

Backend ships `RoleDetail.permissions: string[]` (openapi-snapshot.json:20777-20783). UI `RoleDefinition` is **never imported** by any consumer (no active use), so no runtime fallout today. But it is dead/misleading code: the rewrite-bugs.md BUG-5 comment at `types/index.ts:29-33` still describes the object shape. Will break the first consumer that wires `role.permissions.map(p => p.name)`. 

Because no consumer uses it, priority is P2 (would be P1 on first use).

---

### P2-D — `TraceDetail.tsx` uses `as unknown as TransactionDetail` to hide 3-way type duplication

**File**: `control-plane-ui/src/pages/CallFlow/TraceDetail.tsx:30-49, 132`
**Category**: A (typing) + G (tests).

Three overlapping type definitions for the same API transaction:

| Location | Fields |
|----------|--------|
| `CallFlow/TraceDetail.tsx:30-49` (local `TransactionDetail`) | no `demo_mode`, no `deployment_mode`; `metadata` required on spans |
| `services/api/monitoring.ts:28-44` (`MonitoringTransactionDetail`) | `demo_mode: boolean` **required**; spans `metadata: Record<string,unknown>` required |
| `types/index.ts:556-576` (`APITransaction`) | `demo_mode?: boolean`; spans `metadata?` optional |

`TraceDetail.tsx:132`:
```ts
const data = await apiService.getTransactionDetail(traceId);
return data as unknown as TransactionDetail;  // launders MonitoringTransactionDetail into local shape
```

`apiService.getTransactionDetail` is typed `Promise<MonitoringTransactionDetail>`. The double cast (`as unknown as TransactionDetail`) strips typecheck. No active field-access reads `demo_mode` or `deployment_mode` in `TraceDetail.tsx`, so no crash today — but it's a classic drift footgun: if the backend starts returning spans **without** `metadata`, the local type guarantees it, the cast lies, and `span.metadata.foo` blows up.

Lower priority because no current read path diverges. But this is what bug hunts exist to find.

---

### P2-E — `GatewayDeployment.desired_state` typed `Record<string, unknown>` → 3× `as any` to dig into it

**File**: `control-plane-ui/src/pages/GatewayDeployments/GatewayDeploymentsDashboard.tsx:271, 274, 310`
**Category**: A (typing).

```ts
{(dep.desired_state as any)?.api_name || dep.api_catalog_id.slice(0, 8)}
{(dep.desired_state as any)?.tenant_id || '-'}
handleUndeploy(dep.id, (dep.desired_state as any)?.api_name)
```

`GatewayDeployment.desired_state` is `Record<string, unknown>` (types/index.ts:1099). The backend emits a structured object with `api_name`, `tenant_id`, etc. Optional chaining + `||` fallbacks prevent crashes. **Not a runtime bug today**.

Mark as P2 because this is a legitimate UI-1 scope signal: the wire schema for this field is under-typed. Either backend exposes a typed inline object, or UI adds a narrowed wrapper. Until then, the 3× `as any` is a known smell and the fallback coverage is real.

---

### P2-F — `CertificateHealthBadge` gets `null` cast as `CertificateStatus`

**File**: `control-plane-ui/src/pages/Consumers.tsx:511, 592` (also `ConsumerDetailModal.tsx:115`)
**Category**: A (typing).

```ts
<CertificateHealthBadge
  status={consumer.certificate_status as CertificateStatus}
  ...
/>
```

`consumer.certificate_status` is `string | null` in the backend schema (`openapi-snapshot.json:4691-4701`). The cast to `CertificateStatus = 'active' | 'rotating' | 'revoked' | 'expired'` is a **lie** for both `null` and any future backend value. Badge prop signature is `status?: CertificateStatus` (undefined-tolerant) — so `null` passes through to `getHealthLevel(null, ...)`, skips the `revoked`/`expired` branches, and falls through to `'valid'` when `notAfter` is absent. **Not a crash** but potentially a misleading green badge for a cert with ambiguous status.

Additionally at `Consumers.tsx:508`, the render is gated on `consumer.certificate_fingerprint` existing — when fingerprint is set, status is almost always non-null in practice. Low probability, low blast radius, P2.

---

## Low (none promoted)

Items considered and deliberately NOT flagged as bugs:
- `APITransaction` vs local `TransactionSpan` in `TraceDetail.tsx` — both local types, no current divergence that crashes. Under P2-D.
- `portal/src/types/index.ts` 1134 lines of manual types → **scope Wave 2** (see below).
- `as any` count in tests (132 out of 142 `as any` are in test files) — normal mock ergonomics, not a W1 typing bug.
- `User` view-model has `name` field not present in `UserPermissionsResponse` — documented as OIDC-assembled, not a wire bug.

---

## Scope Wave 2 (NOT bugs Wave 1)

Items explicitly tracked as Wave 2 dette, **not** to be fixed under this audit:

1. **Portal has zero `Schemas[...]` usage.** `grep Schemas\[ portal/src` → 0 hits. All portal types are manual (1134 LOC of `types/index.ts`), including `Application`, `User`, `UserPermissionsResponse`, `APISubscription`, `TenantWebhook`. This matches the "150 wrappers non migrés" note. Not a Wave 1 bug.
2. **Portal-local `APIResponse` interface (line 234)** — name clash with backend `APIResponse` (different shape). Confusing but not imported together. W2.
3. **Console wrapper services (`services/api/*.ts`)** not migrated to Schemas return types (`BackendApi`, `SaasApiKey`, `Deployment`, etc. in `types/index.ts` are still manual view-models).
4. **`RolePermission` / `RoleDefinition` dead types** in `types/index.ts:1381-1397` — could be deleted or aligned with `Schemas['RoleDetail']` (W2 clean-up; P2-C above notes this as bug-only-on-first-use).

---

## Status of the 5 documented BUGs (`rewrite-bugs.md`)

Reconciled against `control-plane-api/openapi-snapshot.json` (@ commit `c6abef8f2`, 2026-04-22):

| BUG | Description | Status | Evidence |
|-----|-------------|--------|----------|
| **BUG-1** | `ApplicationResponse` absent | **RÉSOLU backend** | schema present at openapi-snapshot.json:1439 with 14 props + `required[]`. Portal router owns canonical name; admin schema renamed to `AdminApplicationResponse`. **UI narrowing workaround lingers → P1-A above.** |
| **BUG-2** | `GatewayInstanceResponse` missing fields + stringy enums | **RÉSOLU backend** | `gateway_type`/`mode`/`status` are now enum-typed (snapshot:11484-11589); `enabled`, `source`, `visibility`, `protected`, `deleted_by`, `target_gateway_url`, `ui_url` all declared. **UI intersection workarounds lingers → P2-A above.** |
| **BUG-3** | Duplicate `operationId` dupes | **STILL OPEN (worse)** | `regenerate_secret` now × 3 (vs × 2 reported); 15 other operationIds still × 2. `// @ts-nocheck` still required. Backend ticket unchanged. |
| **BUG-4** | `APIResponse` missing fields + stringy status | **PARTIEL** | `audience` (enum), `created_at` (nullable), `updated_at` (nullable) now present. Remaining: `status: string` still un-typed (no literal union); `openapi_spec` absent (likely intentional — separate endpoint). UI `created_at?: string` narrowing → P2-A. |
| **BUG-5** | `RolePermission` not extracted | **NOT RESOLVED (design shift)** | Backend emits `RoleDetail.permissions: string[]` (plain strings, no `{name, description}`). UI `RolePermission` shape no longer matches design intent. UI type is dead/unused today → P2-C. |

**Conclusion on `rewrite-bugs.md` file**: not yet deletable per the sunset checklist at line 181 — because BUG-3 is still open and `@ts-nocheck` is still required. But the file should be updated to mark **BUG-1/2 as RÉSOLU** and note the partial on BUG-4.

---

## Fix priority

Sequencing suggestion (not a commit plan — user to arbitrate batch composition):

1. **P1-A** — `Application.client_id` narrowing. Either honest type (`string | null` + call-site guards at `Applications.tsx:197`) or backend makes it non-null. Fix unblocks removing the `Omit`/re-add intersection.
2. **P1-B** — Swap `npm install --no-save` → `npm ci` in `api-contract-check.yml`, protects every PR from spurious drift failure.
3. **P2-A** — Clean stale ENRICHED intersections (API / GatewayInstance) now that CAB-2159 landed. Groundwork for removing BUG-1/BUG-2/BUG-4 blocks from `rewrite-bugs.md`.
4. **P2-B** — Strengthen `contract.test.ts` (drop hardcoded prop lists, require full `required[]` coverage).
5. **P2-C** — Delete or realign `RolePermission`/`RoleDefinition` (dead code today).
6. **P2-D** — Unify `TransactionDetail` / `MonitoringTransactionDetail` / `APITransaction` under a single Schemas-derived type; drop the `as unknown as` cast.
7. **P2-E** — Type `GatewayDeployment.desired_state` properly (either backend schema narrowing or a wrapper), remove 3× `as any`.
8. **P2-F** — Guard `certificate_status` cast with a null check (or widen `CertificateHealthBadge` prop to accept `string | null`).

Category D (security via types) came up empty — no field leaks via UI types, no `internal_*` fields exposed, no role-granting mismatches. Backend enforces; UI types are consistent with principle of least surprise at the wire layer. Clean bill of health on the security axis.

---

## Notes on method & caveats

- All concrete line numbers verified against files on `fix/gw-2-bug-hunt-batch` branch (current HEAD `80017fb9d`).
- `tsc` clean for the UI-1 slice (sse.ts errors are unrelated module resolution).
- No runtime reproduction attempted — P1-A is backed by schema contract + consumer-code reading, not an observed crash. Marked as HYPOTHÈSE À VÉRIFIER only for frequency-of-null in production `ApplicationResponse` payloads (the schema *allows* null; whether the backend *currently emits* null depends on the Pydantic field and the DB state).
- "Scope W2 vs bugs W1" distinction respected: portal's un-migrated surface is deferred, not flagged.

**END.**

---

## UI-1 W1 CLOSED — 2026-04-24 (batch-fix)

| # | Item | Status | Evidence |
|---|------|--------|----------|
| P1-A | `Application.client_id` narrowing runtime crash | **FIXED** | `types/index.ts` — alias now `Schemas['ApplicationResponse'] & { environment? }`; `Applications.tsx:197` coerces with `?? ''`. Regression `src/__tests__/regression/UI-1-W1-batch.test.ts`. |
| P1-B | CI drift-gate ignores shared lockfile | **FIXED** | `.github/workflows/api-contract-check.yml` → `npm ci`. |
| P2-A | Stale ENRICHED on `API` and `GatewayInstance` | **FIXED** | `types/index.ts` — `API` reduced to `Schemas['APIResponse'] & { openapi_spec? }`; `GatewayInstance` keeps only `visibility` narrow. |
| P2-B | `contract.test.ts` rubber-stamp | **FIXED** | Assertion upgraded to full `required[]` coverage + soft-warn on backend-only props. Mappings aligned (added `health_details`, `visibility`). |
| P2-C | `RolePermission`/`RoleDefinition` dead types | **FALSE POSITIVE / WONT-FIX** | Types are consumed by `AdminRoles.tsx:124` (`role.permissions[].name/description`, `role.user_count`). Admin endpoint `/v1/admin/roles` is not in the public OpenAPI snapshot. Types are legitimate view-models for a distinct endpoint. See `rewrite-bugs.md` BUG-5 digest. |
| P2-D | 3-way `TransactionDetail` duplication + blind cast | **FIXED** | `services/api/monitoring.ts` aliases `Schemas['TransactionDetailWithDemoResponse']`. `TraceDetail.tsx` imports canonical type, local duplicate deleted, `as unknown as` removed. `redactHeaders` widened to `Record<string, unknown>`. |
| P2-E | `desired_state: Record<string, unknown>` + 3× `as any` | **FIXED** | New `GatewayDeploymentState` interface (typed keys + index signature). All 3 `as any` sites in `GatewayDeploymentsDashboard.tsx` removed. |
| P2-F | `certificate_status` blind cast | **FIXED** | New `normalizeCertificateStatus` helper in `types/index.ts`. 3 call sites (`Consumers.tsx` × 2, `ConsumerDetailModal.tsx`) use it. Regression tests cover null/unknown/valid coercion. |

**Summary**: 7 **FIXED**, 1 **FALSE POSITIVE** (P2-C reclassified after finding the active `AdminRoles.tsx` consumer). Module UI-1 Wave 1 **CLOSED** — 8/8 findings handled.

**Tsc invariant**: 0 errors (post-`npm ci` — the pre-audit "5 errors" reading was a stale measurement in a worktree whose `node_modules` had not yet been installed; the missing-module errors in `sse.ts` disappear once deps are present).

**Follow-up tickets**: none new. CAB-2158 (UI-1 Wave 2 migration) and CAB-2160 (UI-1 polish) remain on backlog. CAB-2159 (BUG-3 operationId dedupe + BUG-4 status enum) remains open backend-side; UI keeps `@ts-nocheck` on `generated.ts` until backend ships.
