---
name: decompose
description: Decompose a MEGA ticket into component-scoped sub-issues on Linear, with dependency DAG and parallel execution plan.
argument-hint: "<CAB-XXXX or feature description>"
---

# Decompose — Component-Scoped Ticket Splitter

Target: $ARGUMENTS

## Purpose

Split a MEGA ticket (or feature description) into independent, component-scoped sub-issues
optimized for parallel execution by multiple Claude Code instances.

## Step 1: Gather Source Material

### If $ARGUMENTS is a CAB-XXXX ticket ID:

```
linear.get_issue("CAB-XXXX", includeRelations=true)
```

Extract: title, description, DoD, estimate, labels, parent.

### If $ARGUMENTS is a feature description:

Use the description directly. Proceed without Linear context.

### Always read:

- `memory.md` — current sprint context
- Relevant source files — to understand which components are impacted

## Step 2: Identify Affected Components

Analyze the feature and map to STOA components:

| Component | Path | Linear Label ID | Tech |
|-----------|------|-----------------|------|
| **cp-api** | `control-plane-api/` | `3d9dcfcc-2578-447f-ab94-0b00b73022f0` | Python, FastAPI |
| **cp-ui** | `control-plane-ui/` | `1c4d11ff-da26-466d-a2ac-e49786bac927` | React, Console |
| **portal** | `portal/` | `df33f1d3-bb93-463d-bf60-7d602a6add10` | React, Portal |
| **gateway** | `stoa-gateway/` | `b14f839d-cde8-4fee-9f1c-894431143b35` | Rust, axum |
| **operator** | `stoa-operator/` | _(create if needed)_ | Python, kopf |
| **e2e** | `e2e/` | _(create if needed)_ | Playwright |
| **docs** | `stoa-docs` (separate repo) | `8a23f909-d1fb-45be-9516-4e33a72998e1` | Docusaurus |
| **infra** | `charts/`, `k8s/` | `ad81cb7f-31a7-4b9c-ac1f-fe0827bfea03` | Helm, K8s |

For each component, check:
1. Does this feature require changes in this component?
2. What is the scope? (model, endpoint, page, route, config, test)
3. Estimated LOC for this component slice?

## Step 3: Build the Dependency DAG

Classify each component-issue into phases based on data flow:

```
Phase 1 (no dependencies — fully parallel):
  ├── cp-api    — models, schemas, endpoints (upstream data provider)
  ├── gateway   — routing rules, middleware (independent data plane)
  ├── docs      — ADR, guide (separate repo, zero code dependency)
  └── infra     — Helm values, CRDs (independent)

Phase 2 (depends on Phase 1 — parallel within phase):
  ├── cp-ui     — Console pages (needs API endpoints from cp-api)
  ├── portal    — Portal pages (needs API endpoints from cp-api)
  └── operator  — CRD reconciler (needs CRDs from infra)

Phase 3 (depends on Phase 2 — sequential):
  └── e2e       — Integration tests (needs UI + API + Gateway running)
```

### Dependency Rules

| Component | Typical Dependencies | Can Run Parallel With |
|-----------|---------------------|----------------------|
| cp-api | None (data source) | gateway, docs, infra |
| gateway | None (data plane) | cp-api, docs, infra |
| docs | None (separate repo) | Everything |
| infra | None (config) | Everything |
| cp-ui | cp-api (needs endpoints) | portal, operator |
| portal | cp-api (needs endpoints) | cp-ui, operator |
| operator | infra (needs CRDs) | cp-ui, portal |
| e2e | cp-ui OR portal + cp-api | Nothing (last) |

### Override Rules

- If the feature has **shared types** (`shared/` directory): cp-ui and portal MUST be sequential (same shared/ changes)
- If the feature has **API contract changes**: cp-api MUST complete and merge before cp-ui/portal start
- If the feature is **UI-only** (no API changes): cp-ui and portal can start immediately (Phase 1)

## Step 4: Estimate Points Per Component

Use historical velocity data:

| Component | Typical Points | LOC Range | Session Duration |
|-----------|---------------|-----------|-----------------|
| cp-api (model + endpoints + tests) | 8-13 pts | 100-300 LOC | 1-2 sessions |
| cp-ui (pages + tests) | 8-13 pts | 100-250 LOC | 1-2 sessions |
| portal (pages + tests) | 5-8 pts | 80-200 LOC | 1 session |
| gateway (route + middleware) | 5-8 pts | 50-150 LOC | 1 session |
| operator (reconciler) | 5-8 pts | 80-200 LOC | 1 session |
| e2e (integration tests) | 3-5 pts | 50-150 LOC | 1 session |
| docs (ADR + guide) | 3-5 pts | 200-500 words | 1 session |
| infra (Helm + k8s) | 2-3 pts | 20-80 LOC | <1 session |

Total sub-issue points should approximately equal the parent MEGA ticket estimate.

## Step 5: Create Sub-Issues on Linear

For each component-issue, create a Linear sub-issue:

```
linear.create_issue(
  title: "[<component>] <action verb> <what> (<parent-ticket-id>)",
  description: <see template below>,
  team: "624a9948-a160-4e47-aba5-7f9404d23506",
  project: "227427af-6844-484d-bb4a-dedeffc68825",
  assignee: "0543749d-ecde-4edf-aec1-6f372aafafce",
  parentId: "<parent-issue-id>",
  estimate: <component-specific points>,
  priority: <inherit from parent>,
  labels: [<component label>, <type label>, "flow-ready"],
  state: "Todo"
)
```

### Sub-Issue Title Convention

```
[cp-api] Add consumer model + endpoints (CAB-XXXX)
[portal] Consumer registration page (CAB-XXXX)
[cp-ui]  Consumer management table (CAB-XXXX)
[gateway] Consumer ID propagation (CAB-XXXX)
[e2e]    Consumer flow integration test (CAB-XXXX)
[docs]   Consumer onboarding guide (CAB-XXXX)
```

### Sub-Issue Description Template

```markdown
## Parent
CAB-XXXX — <parent title>

## Scope
**Component**: `<path>/`
**Phase**: <1|2|3> (parallel|depends on CAB-YYYY)
**Estimated LOC**: ~<N>

## What to Build
- <bullet 1: specific deliverable>
- <bullet 2: specific deliverable>
- <bullet 3: specific deliverable>

## Files to Touch
- `<path/to/file1>` — <what changes>
- `<path/to/file2>` — <what changes>

## DoD (component-scoped)
- [ ] Code compiles (`<build command>`)
- [ ] Tests pass (`<test command>`)
- [ ] Lint clean (`<lint command>`)
- [ ] PR created with < 300 LOC
- [ ] CI green

## Parallel Execution Notes
- **Can start immediately**: Yes | No (blocked by CAB-YYYY)
- **Worktree command**: `git worktree add ../<project>-<component> feat/<branch>`
- **Isolation**: No shared state with other sub-issues
```

## Step 6: Set Up Relations

After all sub-issues are created, establish blocking relations:

```
# Phase 2 issues are blocked by Phase 1 issues
linear.update_issue(phase2_issue_id, relation: { type: "blocks", relatedId: phase1_issue_id })
```

Use Linear's native `blocks` / `blockedBy` relations so the dependency graph is visible in Linear UI.

## Step 7: Generate Execution Plan

Present the DAG visually:

```
Execution Plan for CAB-XXXX — <Feature Name>
═══════════════════════════════════════════════

Phase 1 (parallel — start immediately):
  ┌─────────────────────────────────────────┐
  │ CAB-AAAA [cp-api]  8 pts  ~200 LOC     │ → Agent 1 (main worktree)
  │ CAB-BBBB [gateway] 5 pts  ~100 LOC     │ → Agent 2 (worktree)
  │ CAB-CCCC [docs]    3 pts  ~400 words   │ → Agent 3 (stoa-docs repo)
  └─────────────────────────────────────────┘
  ⏱ Estimated: 1-2 sessions (~45 min)

Phase 2 (parallel — after Phase 1 merges):
  ┌─────────────────────────────────────────┐
  │ CAB-DDDD [portal]  8 pts  ~180 LOC     │ → Agent 1
  │ CAB-EEEE [cp-ui]   8 pts  ~200 LOC     │ → Agent 2
  └─────────────────────────────────────────┘
  ⏱ Estimated: 1 session (~30 min)

Phase 3 (sequential — after Phase 2 merges):
  ┌─────────────────────────────────────────┐
  │ CAB-FFFF [e2e]     3 pts  ~100 LOC     │ → Agent 1
  └─────────────────────────────────────────┘
  ⏱ Estimated: 1 session (~20 min)

───────────────────────────────────────────
Total: 35 pts │ 6 sub-issues │ 3 phases
Sequential time: ~6 sessions
Parallel time:   ~3 sessions (2x speedup)
Max agents needed: 3 (Phase 1)

Worktree Setup:
  git worktree add ../stoa-portal feat/CAB-XXXX-portal
  git worktree add ../stoa-gateway feat/CAB-XXXX-gateway
```

## Step 8: Update Parent Ticket

Add a comment to the parent MEGA ticket with the decomposition summary:

```
linear.create_comment(
  issueId: "<parent-id>",
  body: "## Decomposed into N sub-issues\n\n<execution plan table>\n\nPhase 1 (parallel): CAB-AAAA, CAB-BBBB, CAB-CCCC\nPhase 2 (after API merge): CAB-DDDD, CAB-EEEE\nPhase 3 (after UI merge): CAB-FFFF\n\nMax parallelism: 3 agents"
)
```

Add `needs-split` label removal if it was present:
```
linear.update_issue(parentId, removeLabelIds: ["768f96b2-69f0-4ed3-83de-538f657dd001"])
```

## Step 9: Initialize Claim File

After creating sub-issues (Steps 5-6) and updating the parent (Step 8), generate the claim file for multi-instance coordination:

Create `.claude/claims/<parent-id>.json`:

```json
{
  "mega": "<parent-id>",
  "title": "<parent title>",
  "created": "<ISO-timestamp>",
  "phases": [
    {
      "id": 1,
      "name": "<phase name from DAG, e.g. 'API + Gateway (parallel)'>",
      "tickets": ["<CAB-AAAA>", "<CAB-BBBB>"],
      "owner": null,
      "claimed_at": null,
      "branch": null,
      "mode": "parallel",
      "deps": [],
      "completed_at": null
    },
    {
      "id": 2,
      "name": "<phase name, e.g. 'Console + Portal (parallel)'>",
      "tickets": ["<CAB-DDDD>", "<CAB-EEEE>"],
      "owner": null,
      "claimed_at": null,
      "branch": null,
      "mode": "parallel",
      "deps": [1],
      "completed_at": null
    },
    {
      "id": 3,
      "name": "<phase name, e.g. 'E2E Integration Tests'>",
      "tickets": ["<CAB-FFFF>"],
      "owner": null,
      "claimed_at": null,
      "branch": null,
      "mode": "sequential",
      "deps": [1, 2],
      "completed_at": null
    }
  ]
}
```

**Rules**:
- One phase per DAG level (Phase 1 = all items with no deps, Phase 2 = depends on Phase 1, etc.)
- `mode` is `parallel` if multiple tickets in the phase, `sequential` if single ticket
- `deps` references phase IDs (not ticket IDs)
- All fields start as `null` — instances claim phases via `session-startup.md` Step 2
- See `phase-ownership.md` for full claim lifecycle and schemas

## Step 10: Report to User

```
Decomposition Complete: CAB-XXXX — <Feature Name>
══════════════════════════════════════════════════

Created N sub-issues:

| # | Ticket | Component | Phase | Points | Parallel? |
|---|--------|-----------|-------|--------|-----------|
| 1 | CAB-AAAA | [cp-api] | 1 | 8 | Yes |
| 2 | CAB-BBBB | [gateway] | 1 | 5 | Yes |
| 3 | CAB-CCCC | [docs] | 1 | 3 | Yes |
| 4 | CAB-DDDD | [portal] | 2 | 8 | After CAB-AAAA |
| 5 | CAB-EEEE | [cp-ui] | 2 | 8 | After CAB-AAAA |
| 6 | CAB-FFFF | [e2e] | 3 | 3 | After CAB-DDDD, CAB-EEEE |

Speedup: 2x (3 phases instead of 6 sequential sessions)
Max concurrent agents: 3

Parent ticket CAB-XXXX updated with decomposition comment.
Claim file: `.claude/claims/CAB-XXXX.json` — ready for multi-instance coordination.

Next steps:
  1. "go phase 1" → start all Phase 1 sub-issues
  2. Pick a specific sub-issue: "go CAB-AAAA"
  3. Open N terminals → each claims a different phase automatically (see phase-ownership.md)
  4. Adjust: "move [docs] to Phase 2" or "merge [portal] and [cp-ui]"
```

## Rules

- **Never create sub-issues for single-component features** — if only 1 component is affected, don't decompose
- **Minimum 2 components** to justify decomposition (otherwise it's overhead)
- **Maximum 8 sub-issues** per decomposition (more = over-engineering the split)
- **Each sub-issue MUST be independently deployable** — no broken intermediate state
- **Each sub-issue < 300 LOC** — if a component slice is larger, split further
- **API always Phase 1** — UI components never start before their API dependency is merged
- **E2E always last phase** — integration tests need all components running
- **docs can always run in parallel** — separate repo, zero code coupling
- **shared/ directory is a coupling signal** — if both cp-ui and portal touch `shared/`, they must be sequential
- **Preserve parent estimate** — sum of sub-issue points should equal parent (redistribute, don't inflate)
- **Label with `flow-ready`** — all sub-issues start as flow-ready since they come from a validated MEGA
- **Inherit parent priority** — sub-issues get the same priority as the parent ticket

## Component Label IDs (cached)

| Component | Label ID |
|-----------|----------|
| cp-api | `3d9dcfcc-2578-447f-ab94-0b00b73022f0` |
| cp-ui | `1c4d11ff-da26-466d-a2ac-e49786bac927` |
| portal (ui) | `df33f1d3-bb93-463d-bf60-7d602a6add10` |
| gateway | `b14f839d-cde8-4fee-9f1c-894431143b35` |
| docs | `8a23f909-d1fb-45be-9516-4e33a72998e1` |
| infra | `ad81cb7f-31a7-4b9c-ac1f-fe0827bfea03` |
| flow-ready | `6692a52b-126d-4fce-b480-3fac19751ecb` |
| mega-ticket | `97f7371c-8ac3-44e6-a0a0-412e81bc959e` |
| needs-split | `768f96b2-69f0-4ed3-83de-538f657dd001` |

## Linear IDs (cached)

| Entity | ID |
|--------|----|
| Team (CAB-ING) | `624a9948-a160-4e47-aba5-7f9404d23506` |
| Project (STOA Platform) | `227427af-6844-484d-bb4a-dedeffc68825` |
| Assignee (Christophe) | `0543749d-ecde-4edf-aec1-6f372aafafce` |
