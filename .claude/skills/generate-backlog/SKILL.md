---
name: generate-backlog
description: "Scan codebase to generate MEGA backlog tickets (20-40 pts each). Maintains 400+ pts stock on Linear."
argument-hint: "[--scan | --create | --theme <name> | empty for --scan]"
---

# Generate Backlog — MEGA Ticket Pipeline

Scan the codebase and roadmap files, GROUP findings by component/theme into MEGA tickets
(20-40 pts each, with phases and binary DoD), deduplicate against Linear, and optionally
batch-create to maintain a 400+ pt backlog stock.

**Philosophy**: 10 MEGA tickets at 30 pts > 100 micro-tickets at 3 pts.
Each ticket = a meaningful feature or improvement arc, not a single file fix.

Target: $ARGUMENTS

## Linear IDs (cached)

| Entity | ID |
|--------|----|
| Team (CAB-ING) | `624a9948-a160-4e47-aba5-7f9404d23506` |
| Project (STOA Platform) | `227427af-6844-484d-bb4a-dedeffc68825` |
| Assignee (Christophe) | `0543749d-ecde-4edf-aec1-6f372aafafce` |

### Label IDs

| Label | ID |
|-------|-----|
| `roadmap` (parent — NOT assignable) | `922e1f2d-c839-4b8b-9eba-6c2ba4365a8c` |
| `roadmap:gateway` | `82e07bcd-69fa-4fc5-a2e1-d4d7fa0fad70` |
| `roadmap:dx` | `9f4356e1-f3bc-49a5-b28a-fa1077a6e326` |
| `roadmap:platform` | `c819ff92-c9cf-453d-a0f9-451840f6f8cc` |
| `roadmap:community` | `2de713f1-47a9-49a0-9e84-a7bd947eb707` |
| `roadmap:observability` | `d4ce6487-92fe-4f12-a5f3-8d682e03623f` |

## Step 0: Determine Mode

| Argument | Mode | Description |
|----------|------|-------------|
| (empty) / `--scan` | **Scan** | Read-only report, 0 Linear writes |
| `--create` | **Create** | Batch-create MEGA tickets on Linear (8-15 writes) |
| `--theme <name>` | **Themed scan** | Filter candidates by roadmap theme |

Default is `--scan` (safe, CI-compatible).

## Step 1: Inventory — Current Backlog Depth

Fetch all backlog issues (no cycle) from Linear:

```
linear.list_issues(
  team: "624a9948-a160-4e47-aba5-7f9404d23506",
  first: 100
)
```

Filter for issues where:
- `cycle` is null (not in any cycle)
- `state` is "Backlog" or "Todo"

Compute:
- `backlog_count` = number of backlog issues
- `backlog_pts` = sum of estimates (count unpointed separately)
- `backlog_unpointed` = count of issues with no estimate

Report: "Current backlog: X issues, Y pts pointed, Z unpointed"

## Step 2: Scan 6 Sources (Raw Findings)

Run all 6 scanners to collect raw findings. These are NOT tickets yet — they are
raw material that will be GROUPED into MEGAs in Step 3.

### Scanner 1: TODO/FIXME/HACK in Code

Search for actionable code annotations:

```
grep -rn "TODO\|FIXME\|HACK" \
  --include="*.py" --include="*.ts" --include="*.tsx" --include="*.rs" \
  control-plane-api/ control-plane-ui/ portal/ stoa-gateway/ cli/ e2e/
```

Exclude: `archive/`, `node_modules/`, `target/`, `dist/`, `*.test.*`, `*.spec.*`

Tag each finding with its component (`api`, `gateway`, `portal`, `ui`, `cli`, `e2e`).

### Scanner 2: Test Coverage Gaps

Identify untested modules by comparing source files to test files:

**Python (control-plane-api)**:
- Source routers: `control-plane-api/src/routers/*.py` vs `tests/test_*.py`
- Source services: `control-plane-api/src/services/*.py` vs `tests/test_*.py`

**TypeScript (control-plane-ui / portal)**:
- Source pages/components vs matching `*.test.tsx`

**Rust (stoa-gateway)**:
- Source modules vs `#[cfg(test)]` block presence

Tag each gap with its component.

### Scanner 3: Roadmap Files

Parse `BACKLOG.md`, `docs/CAPACITY-PLANNING.md`, `plan.md` backlog sections.
Extract `CAB-XXXX` IDs, titles, sections. Map to roadmap themes.

### Scanner 4: DX Gaps

Check for missing READMEs, .env.example, @wip E2E features, K8s HPA/PDB/NetworkPolicy gaps.
Tag each gap with its component.

### Scanner 5: Lint Suppressions

Find `# noqa`, `eslint-disable`, `#[allow(` clusters. Tag by component.

### Scanner 6: Content Roadmap (conditional)

Only if `stoa-docs` sibling or `PLAN-SEO.md` accessible. Parse unclaimed topics.
Skip silently if not available.

## Step 3: GROUP into MEGA Tickets (Critical Step)

**This is the key step.** DO NOT create one ticket per finding.
Instead, GROUP all raw findings into 8-15 MEGA tickets by component + theme.

### Grouping Strategy

Group findings into MEGAs using this matrix:

| Component | Theme | MEGA Title Pattern | Target Estimate |
|-----------|-------|--------------------|-----------------|
| `control-plane-api` | `platform` | "API Test Coverage & Quality MEGA" | 21-34 pts |
| `control-plane-api` | `platform` | "API Feature Completion MEGA" (from TODOs) | 21-34 pts |
| `stoa-gateway` | `gateway` | "Gateway Test Coverage & Quality MEGA" | 21-34 pts |
| `stoa-gateway` | `gateway` | "Gateway Feature Completion MEGA" (from TODOs) | 21-34 pts |
| `portal` | `dx` | "Portal Test Coverage & UX Completion MEGA" | 21-34 pts |
| `control-plane-ui` | `dx` | "Console Test Coverage & UX Completion MEGA" | 21-34 pts |
| `e2e` | `dx` | "E2E Test Expansion — Unblock @wip Features MEGA" | 13-21 pts |
| `k8s/charts` | `platform` | "K8s Production Hardening MEGA" (HPA, PDB, NetworkPolicy) | 13-21 pts |
| `all` | `dx` | "Developer Experience MEGA" (READMEs, .env, DX tooling) | 13-21 pts |
| `docs` | `community` | "Documentation & Content MEGA" | 13-21 pts |
| `all` | `platform` | "Tech Debt Cleanup MEGA" (lint suppressions, refactoring) | 13-21 pts |
| roadmap items | varies | "Roadmap: <Phase Name> MEGA" | 21-55 pts |

### Grouping Rules

1. **Minimum 13 pts per MEGA** — anything smaller gets merged into a related MEGA
2. **Maximum 55 pts per MEGA** — anything larger gets split (use `/decompose` later)
3. **Sweet spot: 21-34 pts** — this is the target range for most MEGAs
4. **Same component + same concern = same MEGA** — test gaps for `api` = 1 MEGA, not 29 tickets
5. **Cross-component concerns = themed MEGA** — DX gaps across components = 1 "DX MEGA"
6. **Roadmap items stay as-is** if already > 13 pts in BACKLOG.md/CAPACITY-PLANNING.md
7. **Never create a MEGA with only 1 finding** — merge it into the nearest related MEGA

### MEGA Estimation

Estimate each MEGA based on the aggregate scope of its grouped findings:

| MEGA Type | Base | Per-Finding Adjustment | Range |
|-----------|------|----------------------|-------|
| Test Coverage MEGA | 13 pts | +2 per untested module, +3 if auth-related | 13-34 |
| Feature Completion MEGA | 13 pts | +3 per multi-file TODO, +5 if cross-component | 13-34 |
| DX MEGA | 13 pts | +3 per missing README, +5 per @wip E2E feature | 13-21 |
| K8s Hardening MEGA | 13 pts | +3 per missing HPA, +2 per missing PDB | 13-21 |
| Tech Debt MEGA | 13 pts | +2 per lint cluster | 13-21 |
| Content MEGA | 13 pts | +5 per tutorial, +3 per comparison article | 13-34 |
| Roadmap MEGA | existing estimate | from BACKLOG.md/CAPACITY-PLANNING.md | 21-55 |

**Cap**: 55 pts max per MEGA. Larger = needs `/council` + `/decompose`.

## Step 4: Deduplicate Against Linear

For each MEGA from Step 3:

1. **Exact match**: if MEGA groups `CAB-XXXX` items, check they aren't already active on Linear
2. **Theme overlap**: check if a similar MEGA already exists in backlog (e.g., "API Test Coverage" already exists)
3. **Mark duplicates**: tag as `[DUP]` and exclude

Report: "X MEGAs built, Y duplicates removed, Z net new"

## Step 5: Build Report — Top 15 MEGAs

Present MEGAs grouped by roadmap theme:

```
Backlog Generation Report (MEGA Mode)
=======================================

Current backlog: XX issues, YYY pts | Target: 400 pts
Gap: ZZZ pts needed | MEGAs proposed: NN

By Theme:
---------

gateway (XX pts, N MEGAs):
  1. [34 pts] Gateway Test Coverage & Quality MEGA
     Scope: 27 untested modules (proxy, oauth, guardrails, federation...)
     Phases: P1 core modules (13 pts) → P2 security modules (8 pts) → P3 edge cases (13 pts)

  2. [21 pts] Gateway Feature Completion MEGA
     Scope: 15 TODOs (OTel init, MCP resource listing, shadow capture...)
     Phases: P1 observability (8 pts) → P2 MCP features (8 pts) → P3 cleanup (5 pts)

platform (XX pts, N MEGAs):
  1. [34 pts] API Test Coverage & Quality MEGA
     Scope: 29 untested routers, 23 untested services
     Phases: P1 auth routers (13 pts) → P2 core services (13 pts) → P3 adapters (8 pts)

  2. [21 pts] K8s Production Hardening MEGA
     Scope: missing HPA (5), PDB (5), NetworkPolicy (3)
     Phases: P1 HPA all components (8 pts) → P2 PDB + NetworkPolicy (8 pts) → P3 docs (5 pts)

dx (XX pts, N MEGAs):
  1. [21 pts] Portal Test & UX Completion MEGA
     Scope: 37 untested components, 3 key TODOs
     Phases: P1 auth components (8 pts) → P2 tools components (8 pts) → P3 integration (5 pts)

  2. [13 pts] Developer Experience MEGA
     Scope: 5 missing READMEs, 3 missing .env.example
     Phases: P1 READMEs (5 pts) → P2 .env.example (3 pts) → P3 onboarding guide (5 pts)

observability (XX pts, N MEGAs):
  ...

community (XX pts, N MEGAs):
  ...

Summary:
  Total MEGAs: NN | Total points: XXX pts
  After creation, backlog would be: YYY pts (target: 400)
  Duplicates removed: DD
  Scanners skipped: [list or "none"]
```

## Step 6: Execute

### Scan mode (`--scan`, default)

Display the report from Step 5. No Linear writes. Exit.

### Create mode (`--create`)

For each MEGA (up to 15):

```
linear.create_issue(
  title: "[MEGA] <Theme>: <Description>",
  description: <see template below>,
  team: "624a9948-a160-4e47-aba5-7f9404d23506",
  project: "227427af-6844-484d-bb4a-dedeffc68825",
  assignee: "0543749d-ecde-4edf-aec1-6f372aafafce",
  estimate: <pts from Step 3>,
  priority: 3,
  labels: ["roadmap:<theme>"],
  state: "Backlog"
)
```

**MEGA ticket description template**:

```markdown
## Context

Auto-generated by `/generate-backlog` MEGA pipeline.
Theme: {theme} | Component(s): {components}
Findings grouped: {count} items from {scanner_names}

## Scope

{2-3 sentences describing what this MEGA covers and why it matters}

### Included Findings

{Bulleted list of all grouped raw findings with file:line references}

## Implementation Phases

### Phase 1: {name} (~{pts} pts)
- {specific deliverable 1}
- {specific deliverable 2}
- **Verification**: {command that proves Phase 1 is done}

### Phase 2: {name} (~{pts} pts)
- {specific deliverable 1}
- {specific deliverable 2}
- **Verification**: {command that proves Phase 2 is done}

### Phase 3: {name} (~{pts} pts)
- {specific deliverable 1}
- {specific deliverable 2}
- **Verification**: {command that proves Phase 3 is done}

## Binary DoD

- [ ] Phase 1 complete — verification passes
- [ ] Phase 2 complete — verification passes
- [ ] Phase 3 complete — verification passes
- [ ] All modified files have tests
- [ ] CI green (component quality gate)
- [ ] No new lint suppressions introduced
- [ ] State files updated (memory.md, plan.md)

## Estimate Rationale

{MEGA type}: {base} pts + {per-finding adjustments} = {total} pts
Findings: {count} items across {files_count} files in {component}

---
_Auto-generated by STOA AI Factory `/generate-backlog` MEGA pipeline — {date}_
```

### Themed mode (`--theme <name>`)

Same as `--scan` but filter MEGAs to only those matching the specified theme
(`gateway`, `dx`, `platform`, `community`, `observability`).

## Step 7: Report & Log

### Final report

```
Backlog Generation Complete (MEGA Mode)
=========================================
Mode: {scan|create|themed}
Scanners run: 6 (or list skipped)

Raw findings: XXX items across 6 scanners
MEGAs built: NN (grouped from raw findings)
Duplicates removed: DD

{if --create}
Created: NN MEGAs on Linear (total: XXX pts)
Backlog after: YYY pts (target: 400 pts)
{/if}

{if --scan}
Recommended: run `/generate-backlog --create` to create NN MEGAs (XXX pts)
{/if}

Top 5 MEGAs by impact:
  1. [MEGA] Gateway Test Coverage & Quality (34 pts)
  2. [MEGA] API Test Coverage & Quality (34 pts)
  3. ...
```

### Operations log (--create mode only)

Append to `~/.claude/projects/-Users-torpedo-hlfh-repos-stoa/memory/operations.log`:

```
STEP-DONE | step=generate-backlog task=backlog-pipeline megas_created=N total_pts=X backlog_depth=Y
```

## MCP Budget

| Call | Purpose | Mode |
|------|---------|------|
| `list_issues(no cycle)` | Inventory current backlog | All |
| `create_issue` x N | Batch create MEGAs | `--create` only |
| **Total read** | **1 call** | |
| **Total write** | **0 (scan) / 8-15 (create)** | |

## Rules

- **`--scan` is default** — never auto-create without explicit `--create`
- **MEGA only** — NEVER create atomic per-file tickets. Minimum 13 pts per ticket
- **Cap at 15 MEGAs per run** — quality over quantity
- **Sweet spot: 21-34 pts** — most MEGAs should be in this range
- **Group by component + concern** — test gaps for 1 component = 1 MEGA, not N tickets
- **Phases mandatory** — every MEGA has 2-4 implementation phases with verification commands
- **Binary DoD mandatory** — every MEGA has checkboxes that are objectively pass/fail
- **Dedup BEFORE create** — check Linear backlog for similar existing MEGAs
- **Theme labels mandatory** — every MEGA gets `roadmap:<theme>` label
- **[MEGA] prefix in title** — makes them visually distinct in Linear board
- **Auto-gen marker** — description includes "Auto-generated by /generate-backlog"
- **Priority 3 (Normal) default** — MEGAs are substantial work, not throwaway
- **State "Backlog"** — never create in "Todo" or "In Progress"
- **Never assign to a cycle** — MEGAs go to backlog, `/fill-cycle` promotes them
- **No scanner scripts** — skill is pure SKILL.md (Claude executes logic inline)
- **Exclude archives** — never scan `archive/`, `node_modules/`, `target/`, `dist/`
- **Log all creates** in operations.log for audit trail
