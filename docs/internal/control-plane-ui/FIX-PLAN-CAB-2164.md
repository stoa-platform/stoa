# CAB-2164 — UI-3 Cleanup — Fix Plan

> **Ticket**: [CAB-2164](https://linear.app/hlfh-workspace/issue/CAB-2164) — UI-3 Cleanup.
> **Scope**: absorbs P2-11 + P2-12 (UI-2) + P2-E (UI-1 W1) + a follow-through on P2-7 (UI-2, WONT-FIX).
> **Pattern**: Phase 1 plan → STOP → arbitrations → Phase 2 commits.

## 0. Pre-flight state (Phase 0 observations)

- Current branch: `fix/ui-1-w1-bug-hunt-batch`, head `8d98d6518`.
- `fix/ui-1-w1-bug-hunt-batch` is **NOT yet merged to main** (PR #2525 OPEN).
- `fix/ui-2-p2-batch` is merged (PR #2521, `b35039a09` on main).
- `rewrite-bugs.md` (lowercase, tracked) — contains BACKEND gaps, BUG-1..BUG-5 (CAB-2159 tracking).
  - **Case-insensitive FS collision risk**: on macOS APFS (default), `rewrite-bugs.md` and `REWRITE-BUGS.md` refer to the same path. Creating the uppercase file would rename or corrupt the existing one.
- All four deferred items have their Schemas counterparts already defined either in `shared/api-types/generated.ts` or `src/types/index.ts` — no type invention required for Item 2.

### Branching strategy

- If UI-1 W1 PR #2525 merges before Phase 2 starts → rebranch `fix/cab-2164-ui-3-cleanup` from `origin/main`.
- If #2525 still open at Phase 2 start → rebranch from `fix/ui-1-w1-bug-hunt-batch` (stacked PR) and rebase onto main after #2525 squash-merges (`git rebase --onto origin/main HEAD~N` per gotcha_rebase_onto_after_squash_merge).

---

## 1. Item-by-item inventory

### Item 4 — P2-E (UI-1 W1, `desired_state`) — **ALREADY-FIXED**

- **Evidence**:
  - `src/types/index.ts:1087-1100` defines `GatewayDeploymentState` with index signature + narrowed `api_name`/`tenant_id`.
  - `GatewayDeployment.desired_state` uses that type (no `any`).
  - Regression guard: `src/__tests__/regression/UI-1-W1-batch.test.ts:108-133` asserts no `desired_state as any` casts remain in `GatewayDeploymentsDashboard.tsx`.
  - Commit: `073b947e9` (part of UI-1 W1 batch `8d98d6518`).
- **Action for CAB-2164**: zero code. Mark **ALREADY-FIXED by commit 073b947e9** in `REWRITE-BUGS.md` §UI-3 findings and in the CAB-2164 Linear close comment. No regression guard needed (already shipped with UI-1 W1).

### Item 3 — P2-7 (auth module-scope state) — **RECOMMEND: Option A (minimal, keep ESLint fence)**

- **Current state**:
  - `src/services/http/auth.ts:1-30` already carries a doc block explaining the intentional module-scope state, the sessionStorage-per-tab rationale, and the ESLint `no-restricted-imports` fence.
  - The doc block **explicitly documents the "refactor-rejected" decision** ("A runtime refactor (namespace class or IIFE closure) was considered but rejected for a P2 — the risk of introducing a bug on the critical auth path outweighs the encapsulation gain that the lint rule already buys.").
  - `.eslintrc.cjs:34,50,79,95` carries two overrides (services/http/ and tests) that constrain imports.
  - Only legitimate consumer is `src/services/http/refresh.ts` (same directory, allowed).
- **Empirical call for Option A vs Option B**:
  - Option B (closure/class refactor) would touch `auth.ts` (core rewrite) + `refresh.ts` (consumer) + tests that poke `isRefreshing` state. Inlining the state into a closure means every caller in `refresh.ts` migrates from function imports to method calls. This is ~1 auth-critical file + 1 consumer + test updates — plausibly 3-5 files, not <5.
  - The auth path is already covered by the ESLint fence. The architecture choice (sessionStorage per tab, no cross-tab sync) explicitly does not need runtime encapsulation: tabs each own their state by design.
  - Value-for-risk: low. The lint rule is sufficient. No known consumer has bypassed it.
- **Decision**: **Option A** (keep current doc block + ESLint rule). The current state of `auth.ts` already satisfies the "doc block explaining why internals are exported" requirement. **Zero code change.** Add a one-line note in `REWRITE-BUGS.md` §UI-3 findings recording the decision and the empirical assessment.
- **Alternative trigger for Option B** (future): if a PR or audit ever shows an import bypass of the ESLint fence, re-open the refactor. Not today.

### Item 1 — `REWRITE-BUGS.md` (zombies + UI-3 findings) — **CODE WORK REQUIRED**

- **Blocker**: macOS case-insensitive FS collision with existing `rewrite-bugs.md`.
- **Arbitration A (decision needed)** — where to put zombies list:
  - **Option A1** — `git mv control-plane-ui/rewrite-bugs.md control-plane-ui/BACKEND-GAPS-CAB-2159.md` (semantic rename — that file is *backend* gaps, not rewrite *bugs*), then create new `REWRITE-BUGS.md` (uppercase) for zombies + UI-3 findings. Clear separation.
  - **Option A2** — keep existing `rewrite-bugs.md` (lowercase), add a new section §B "Zombies preserved + UI-3 findings" to it, rename as whole `REWRITE-BUGS.md` (uppercase). Two topics in one file; §A = backend gaps (CAB-2159), §B = zombies + UI-3 (CAB-2164).
  - **Option A3** — create a distinct file named `REWRITE-ZOMBIES.md` (no collision, no rename). Leaves existing `rewrite-bugs.md` intact.
  - **Recommendation**: **Option A1**. Rationale: (1) `rewrite-bugs.md` is misnamed (it's about backend schema gaps, not about "bugs introduced by the rewrite"); renaming clarifies intent. (2) Fulfills the literal contract of REWRITE-PLAN.md §A.2 ("Noter dans `REWRITE-BUGS.md`"). (3) `git mv` preserves history.
- **Content of new `REWRITE-BUGS.md`**:
  - §A — Zombies (40 methods from REWRITE-PLAN §A.2): list by file (`src/services/api/<domain>.ts`) + current status (preserved / removed / NOT-A-ZOMBIE-anymore). For CAB-2164 we only *document*, we do not *remove* zombies (removing them is a distinct ticket — see §4 follow-ups).
  - §B — UI-3 findings deferred from earlier batches:
    - P2-E UI-1 W1: **FIXED by commit 073b947e9**.
    - P2-7 UI-2: **WONT-FIX confirmed** (Option A).
    - P2-11 UI-2: **FIXED by this batch** (the file itself is the fix).
    - P2-12 UI-2: **FIXED by this batch** (see Item 2).
  - §C — Convention for future additions (same shape as existing `rewrite-bugs.md` §Convention).
  - §D — Sunset criteria (when to delete this file).

### Item 2 — `any` pervasif sur gateways/deployments — **CODE WORK REQUIRED**

- **Actual inventory** (re-counted 2026-04-24):

| File | `any` sites (method-lines) | `any` tokens (total) | Already-available replacement |
|---|---|---|---|
| `src/services/api/gateways.ts` | 15 | ~20 | ✓ |
| `src/services/api/gatewayDeployments.ts` | 5 | 5 | ✓ |
| `src/services/api.ts` (façade) | ~10 gateway methods | ~20 | mirror from clients |

- **Mapping `any` → target type**:

| Method | Current signature | Target |
|---|---|---|
| `listInstances` | `Promise<{ items: any[]; total; page; page_size }>` | `Promise<PaginatedGatewayInstances>` *(already exported from `src/types`)* |
| `getInstance` | `Promise<any>` | `Promise<GatewayInstance>` *(already exported)* |
| `listTools` | `Promise<any[]>` | `Promise<Schemas['ListToolsResponse']['tools']>` or narrowed inline `Array<{ name: string; description?: string; ... }>` — **decision**: use `Schemas['ListToolsResponse']['tools']` (exists in snapshot). |
| `createInstance` | `(payload: any): Promise<any>` | `(payload: GatewayInstanceCreate): Promise<GatewayInstance>` *(both exported)* |
| `updateInstance` | `(id, payload: any): Promise<any>` | `(id, payload: GatewayInstanceUpdate): Promise<GatewayInstance>` *(both exported)* |
| `restoreInstance` | `Promise<any>` | `Promise<GatewayInstance>` |
| `checkHealth` | `Promise<any>` | `Promise<Schemas['GatewayHealthCheckResponse']>` |
| `getAggregatedMetrics` | `Promise<any>` | `Promise<AggregatedMetrics>` *(already in `src/types`)* |
| `getGuardrailsEvents` | `Promise<any>` | `Promise<{ events: Array<{ ts: string; type: string; summary: string }>; total: number }>` — **no Schemas candidate found** → local wrapper type (document in commit). **TODO(WAVE-2)**. |
| `getHealthSummary` | `Promise<any>` | `Promise<Schemas['GatewayHealthResponse']>` |
| `getInstanceMetrics` | `Promise<any>` | **No direct Schemas** (per-instance metrics endpoint = shape aligned with `AggregatedMetrics['health']` slice) → local wrapper `GatewayInstanceMetrics` with `// TODO(WAVE-2): promote to Schemas['X']` |
| `listPolicies` | `Promise<any[]>` | `Promise<GatewayPolicy[]>` *(already exported)* |
| `createPolicy` | `(payload: any): Promise<any>` | `(payload: Schemas['GatewayPolicyCreate']): Promise<GatewayPolicy>` |
| `updatePolicy` | `(id, payload: any): Promise<any>` | `(id, payload: Schemas['GatewayPolicyUpdate']): Promise<GatewayPolicy>` |
| `createPolicyBinding` | `(payload: any): Promise<any>` | `(payload: Schemas['PolicyBindingCreate']): Promise<Schemas['EnableBindingResponse']>` or local `{ id; policy_id; resource_id; ... }` if Schemas missing — verify in Phase 2. |
| `getStatusSummary` (deployments) | `Promise<any>` | No Schemas candidate (deployment dashboard aggregation) → local `DeploymentStatusSummary` wrapper. **TODO(WAVE-2)**. |
| `list` (deployments) | `Promise<{ items: any[]; total; page; page_size }>` | `Promise<Schemas['PaginatedGatewayDeployments']>` |
| `get` (deployments) | `Promise<any>` | `Promise<GatewayDeployment>` *(exported)* or `Promise<Schemas['GatewayDeploymentResponse']>` — **decision**: `GatewayDeployment` (UI-specific type with narrowed `desired_state`). |
| `deployApiToGateways` | `Promise<any[]>` | `Promise<GatewayDeployment[]>` |
| `forceSync` | `Promise<any>` | `Promise<GatewayDeployment>` |

- **Façade (`api.ts`) mirroring** — for each client method above, update the façade wrapper to import and use the same type. Keep the `// eslint-disable-next-line` comments removed once `any` is gone.

- **Arbitration B (decision needed)** — for the 4 sites without a first-class Schemas source (`getGuardrailsEvents`, `getInstanceMetrics`, `getStatusSummary`, `createPolicyBinding`):
  - **Option B1** — create local wrapper interfaces with explicit `// TODO(WAVE-2): align with Schemas['X'] once backend ships` comments. Track as backend follow-up in `rewrite-bugs.md`/new `BACKEND-GAPS-CAB-2159.md`.
  - **Option B2** — keep `any` for those 4 sites + eslint-disable comments, document why in `REWRITE-BUGS.md`.
  - **Recommendation**: **Option B1**. Four small interfaces cost ~40 LOC, eliminate 100 % of `any` in the target files, and create backend-visible TODOs that can become follow-up tickets if the backend schema eventually ships. The alternative (keep `any`) leaves the invariant `grep any src/services/api/gateways.ts | wc -l → 0` unverifiable. B1 matches the DoD on the Linear ticket.

- **Arbitration C (decision needed)** — touch consumers or stop at clients + façade?
  - **Option C1** — change client + façade signatures only; consumers that called `apiService.getGatewayInstance(id)` and got `any` still compile (TypeScript widens on assign).
  - **Option C2** — walk every consumer and replace `any` inference with explicit types. Scope-risk: tests mocking `gatewaysClient.getInstance` with arbitrary shapes will fail.
  - **Recommendation**: **Option C1 with spot-fixes only for strict consumers** (e.g. pages that type-annotate state). Rationale: the goal is the invariant at the `api/*` boundary. Consumers have their own typing contracts that will be hardened in UI-1 Wave 2. Mixing cleanup scopes re-creates the risk the UI-2 audit explicitly called out.

### C1.3 — Tests touched

- `src/test/services/api/ui2-s2d-clients.test.ts` already exists and tests `gatewaysClient`/`gatewayDeploymentsClient` shape. Will need payload types aligned; verify in Phase 2.
- `src/test/regression/*` — no new test strictly required. Optional additional `cab-2164.test.ts` regression asserting no `: any` in target files + `eslint-disable-next-line @typescript-eslint/no-explicit-any` comments removed.

---

## 2. Commit strategy

- **All-in-one commit** (estimated ~200-300 LOC):
  - Rename `rewrite-bugs.md` → `BACKEND-GAPS-CAB-2159.md` (Option A1).
  - Create `REWRITE-BUGS.md` (zombies §A + UI-3 findings §B + convention §C + sunset §D).
  - Type `gateways.ts` + `gatewayDeployments.ts` (20 + 5 = 25 `any` removed; ~40 LOC of local wrappers added).
  - Mirror façade signatures in `api.ts`.
  - (Optional) Add `src/__tests__/regression/CAB-2164.test.ts` asserting invariants.
- **Split into 2 commits** ONLY if Phase 2 blows past 400 LOC OR consumer test updates are required:
  - Commit 1: Documentation + file rename (zero behaviour change).
  - Commit 2: Type hardening (gateways/deployments/façade).

Estimated total: ~250-350 LOC net. Borderline threshold; default to **one commit** unless Phase 2 reveals surprises.

---

## 3. Regression guards

- **Invariant check** (baked into commit message + re-run locally):
  - `grep -cE "[^a-zA-Z]any[^a-zA-Z]" src/services/api/gateways.ts src/services/api/gatewayDeployments.ts` → must be `0` (after stripping legitimate non-type uses — none expected).
  - `grep -cE "eslint-disable-next-line @typescript-eslint/no-explicit-any" src/services/api/gateways.ts src/services/api/gatewayDeployments.ts` → must be `0`.
- **tsc baseline**: pre-existing `sse.ts` errors (5, unrelated); no new error introduced.
- **vitest**: all current tests pass (2198 tests post-UI-2 P1).
- **eslint**: zero new warning or error (max-warnings 100 ratchet).
- **Contract test**: `contract.test.ts` (tight guard from P2-B UI-1 W1) already validates the full `required[]` of migrated schemas. No new entry needed *if* we align on `GatewayInstance` / `GatewayDeployment` (both already covered via their `Schemas` parents).

---

## 4. Out-of-scope / follow-ups

- **Actual removal of zombies** — CAB-2164 *documents* them, not removes them. Removing a zombie implies: audit consumers (shared/ wraps, portal/, e2e/), verify no `apiService.<name>` bypass survived. That's a separate codemod. Create a follow-up ticket `CAB-2164-removal` *only* if product owner confirms appetite; otherwise leave as a perpetual cleanup candidate noted in REWRITE-BUGS.md §A.
- **4 backend schema gaps** (getGuardrailsEvents, getInstanceMetrics, getStatusSummary, createPolicyBinding if Schemas missing) — append to `BACKEND-GAPS-CAB-2159.md` §BUG-N new sections. Already-open ticket CAB-2159 absorbs.
- **Consumer-side `any` sweep** — explicitly deferred to UI-1 Wave 2 (`CAB-2158`). Documented as such in REWRITE-BUGS.md §B.

---

## 5. STOP before Phase 2

**Arbitrations requiring user sign-off**:

- **ARB-A** (Item 1): file strategy — A1 rename `rewrite-bugs.md` → `BACKEND-GAPS-CAB-2159.md` + new `REWRITE-BUGS.md`? OR A2 single-file merge? OR A3 distinct `REWRITE-ZOMBIES.md`? — **Reco: A1.**
- **ARB-B** (Item 2): 4 sites without Schemas — B1 local wrappers with TODO(WAVE-2)? OR B2 keep `any` with documented justification? — **Reco: B1.**
- **ARB-C** (Item 2): consumer scope — C1 client + façade only? OR C2 walk all consumers? — **Reco: C1.**
- **ARB-D** (Branching): Phase 2 branch off `main` (wait for #2525) or stack on `fix/ui-1-w1-bug-hunt-batch`? — **Reco**: wait for #2525 merge if it lands within ~1h; else stack.

**Optional follow-ups to confirm**:
- Create `CAB-2164-removal` follow-up ticket for actual zombie removal? (Reco: no — leave documented candidates in place.)
- Append 4 new BUG-N sections to `BACKEND-GAPS-CAB-2159.md`? (Reco: yes, same commit.)

Phase 2 starts only after user validates the four arbitrations above.
