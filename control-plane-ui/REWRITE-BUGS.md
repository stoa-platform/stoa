# UI Rewrite — Zombies preserved + UI-3 Cleanup findings

> **Tracking ticket**: [CAB-2164](https://linear.app/hlfh-workspace/issue/CAB-2164)
> — UI-3 Cleanup. Absorbs P2-11 + P2-12 (UI-2), P2-E (UI-1 W1), P2-7 follow-through.
>
> **Purpose**: the UI-2 rewrite (CAB-2079) preserved ~40 zombie methods
> (declared but 0 external caller) in the domain clients under
> `src/services/api/*` — removal was explicitly out of scope of the rewrite
> (`rewrite ≠ cleanup`). This file is the follow-through promised in
> `REWRITE-PLAN.md §A.2` and documents UI-3 findings that did not require
> a code change in this batch.
>
> For backend contract gaps (`/v1/admin/gateways/metrics` untyped, etc.),
> see the sibling file `BACKEND-GAPS-CAB-2159.md`.

---

## §A — Zombies preserved (REWRITE-PLAN §A.2)

**Status**: documented, NOT removed. Removing a zombie requires auditing
consumers beyond `control-plane-ui/` (portal/, shared/, e2e/) to confirm
no cross-package consumer bypasses the façade. CAB-2164 chose to preserve
and document rather than remove to avoid silent breakage. A follow-up
removal ticket may be opened if/when a product owner confirms appetite.

**40 methods** were identified in REWRITE-PLAN §A.2 as zombies at UI-2
merge time. Organized by domain client below.

### Tenants (`src/services/api/tenants.ts`)

- `createTenant` — zombie
- `updateTenant` — zombie
- `deleteTenant` — zombie
- `getTenant` — zombie
- `getTenantCA` — partially zombie (read side used; write methods cold)
- `revokeTenantCA` — zombie

### Applications (`src/services/api/applications.ts`)

- `getApplication` — zombie

### Consumers (`src/services/api/consumers.ts`)

- `getConsumer` — zombie
- `blockConsumer` — zombie

### Deployments (`src/services/api/deployments.ts`)

- `getDeployment` — zombie
- `getPromotion` — zombie
- `getDeployableEnvironments` — zombie
- `getEnvironmentStatus` — zombie
- `getEnvironments` — zombie
- `getApiGatewayAssignments` — zombie
- `createApiGatewayAssignment` — zombie
- `deleteApiGatewayAssignment` — zombie

### Traces (`src/services/api/traces.ts`)

- `getTrace` — zombie
- `getTraceTimeline` — zombie
- `getLiveTraces` — zombie

### Git (`src/services/api/git.ts`)

- `getMergeRequests` — zombie
- `getCommits` — zombie

### Platform (`src/services/api/platform.ts`)

- `getOperationsMetrics` — zombie
- `getExpiringCertificates` — zombie

### Gateways (`src/services/api/gateways.ts`)

- `getInstance` (aliased `getGatewayInstance`) — zombie **at REWRITE-PLAN
  time**, now **LIVE** (consumed by `GatewayDetail.tsx` — not a zombie
  anymore post-UI-3).
- `getInstanceMetrics` — zombie
- `listPolicies` — zombie
- `createPolicy` — zombie
- `updatePolicy` — zombie
- `removePolicy` — zombie
- `createPolicyBinding` — zombie
- `removePolicyBinding` — zombie

### Gateway Deployments (`src/services/api/gatewayDeployments.ts`)

- `get` (aliased `getGatewayDeployment`) — zombie
- `deployApiToGateways` — zombie
- `listCatalogEntries` (aliased `getCatalogEntries`) — zombie

### Chat (`src/services/api/chat.ts`)

- `getChatUsageStats` — zombie
- `getTransactionStats` — zombie

### Webhooks (`src/services/api/webhooks.ts`)

- `getWebhook` — zombie

### Subscriptions (`src/services/api/subscriptions.ts`)

- `getPendingSubscriptions` — zombie

### LLM (`src/services/api/llm.ts`)

- `getLlmBudget` — zombie
- `updateLlmBudget` — zombie

### Contracts (`src/services/api/contracts.ts`)

- `getContractBindings` — zombie

### Workflows (`src/services/api/workflows.ts`)

- `updateWorkflowTemplate` — zombie
- `seedWorkflowTemplates` — zombie
- `startWorkflow` — zombie

---

## §B — UI-3 findings digest

### B.1 — P2-11 UI-2 (`REWRITE-BUGS.md` absent) — **FIXED by CAB-2164**

Source: `BUG-REPORT-UI-2.md P2-11`, decision: `FIX-PLAN-UI2-P2.md ARB-7`.

This file **is** the fix. The commit renaming `rewrite-bugs.md` →
`BACKEND-GAPS-CAB-2159.md` (to disambiguate scope) and creating
`REWRITE-BUGS.md` (this file, for zombies + UI-3 scope) fulfils the
REWRITE-PLAN §A.2 contract. Closes P2-11.

### B.2 — P2-12 UI-2 (`any` pervasif sur gateways/deployments) — **FIXED by CAB-2164**

Source: `BUG-REPORT-UI-2.md P2-12`.

Typed every `any` in `src/services/api/gateways.ts` and
`src/services/api/gatewayDeployments.ts` plus their façade mirrors in
`src/services/api.ts`. Payload types use `Schemas['...']` aliases from
`shared/api-types/generated.ts` where available; four endpoints without
canonical schemas use UI wrapper interfaces in `src/types/index.ts` with
`TODO(WAVE-2)` markers pointing at the corresponding `BACKEND-GAPS-CAB-2159.md`
entries (BUG-6..9).

Invariant enforced post-commit: 0 `any` in target files, 0
`eslint-disable-next-line @typescript-eslint/no-explicit-any` markers in
target files.

Consumer spot-fixes (ARB-C scope): `GuardrailsDashboard.tsx` contract
honoured via `AggregatedMetrics.guardrails` / `.rate_limiting` slices +
aligned `GatewayGuardrailsEvent`; `GatewayDetail.tsx` deployment row reads
`desired_state.api_name` / `.api_version` + `gateway_environment` (real
backend fields) instead of flat mock-only `api_name` / `api_version` /
`environment` (latent bug fix); `GatewaySecurityDashboard.tsx` removed
shadowing local `GatewayInstance` interface; `GatewayDetail.test.tsx`
mock reshaped to match real backend payload.

### B.3 — P2-E UI-1 W1 (`desired_state` typed) — **ALREADY-FIXED by commit 073b947e9**

Source: `BUG-REPORT-UI-1-W1.md P2-E`. No work in CAB-2164. Regression
guard in `src/__tests__/regression/UI-1-W1-batch.test.ts:108-133` (asserts
no `desired_state as any` casts survive in `GatewayDeploymentsDashboard.tsx`).

### B.4 — P2-7 UI-2 (auth module-scope state) — **WONT-FIX confirmed by CAB-2164 Option A**

Source: `BUG-REPORT-UI-2.md P2-7`, decision: `FIX-PLAN-UI2-P2.md` (inline
ESLint rule only, refactor rejected for a P2).

Reassessed empirically in CAB-2164:
- `auth.ts` already carries a doc block (L1-30) that explains the
  module-scope rationale (sessionStorage-per-tab XSS blast radius reduction)
  and explicitly documents why the refactor was rejected.
- `.eslintrc.cjs` carries two `no-restricted-imports` overrides
  (services/http/ + tests) that constrain consumer imports.
- The single legitimate consumer (`services/http/refresh.ts`) lives in
  the allowed directory.
- Empirical scope of a closure/class refactor: 3-5 files touching the
  critical auth path for no runtime gain over the ESLint fence.

**Decision** (CAB-2164): keep Option A — ESLint rule + doc block. No code
change. Re-open only if a future PR or audit shows an import bypass.

---

## §C — Convention pour ajouts

Quand un nouveau finding non-bloquant est identifié pendant un cleanup
batch suivant :

1. Ajouter une section `### B.N — <titre>` sous §B (UI-3 findings digest).
2. Préciser : source (`BUG-REPORT-*.md` ou audit ID), décision (FIXED /
   ALREADY-FIXED / WONT-FIX / DEFERRED), commit SHA si FIXED.
3. Si un backend gap est découvert, l'ajouter dans
   `BACKEND-GAPS-CAB-2159.md` comme `BUG-N` et référencer la section dans
   le finding UI-3.
4. Si une méthode zombie §A devient live (consommée), mentionner la
   transition dans §A avec `**LIVE** (consumed by ...)`.

---

## §D — Sunset

Supprimer `REWRITE-BUGS.md` quand TOUTES les conditions sont remplies :

1. §A (zombies) soit vide, soit toutes les entrées marquées **LIVE** ou
   **REMOVED** (via un follow-up `CAB-2164-removal` ou équivalent).
2. §B (UI-3 findings) toutes marquées **FIXED** ou **WONT-FIX confirmé**
   sans dette résiduelle.
3. `control-plane-ui/BACKEND-GAPS-CAB-2159.md` supprimé (les TODO(WAVE-2)
   qui pointent vers ce fichier n'ont plus de cible).

Tant que `BACKEND-GAPS-CAB-2159.md` existe avec au moins un BUG ouvert,
`REWRITE-BUGS.md` doit rester (les wrappers locaux référencés survivent).
