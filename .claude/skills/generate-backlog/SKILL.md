---
name: generate-backlog
description: "Scan 6 code sources to generate pointed backlog tickets. Maintains 400+ pts stock on Linear."
argument-hint: "[--scan | --create | --theme <name> | empty for --scan]"
---

# Generate Backlog — Backlog Stock Pipeline

Scan the codebase and roadmap files to discover ticket candidates, deduplicate against
Linear, estimate points, and optionally batch-create tickets to maintain a 400+ pt backlog stock.

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
| `roadmap` (parent) | `922e1f2d-c839-4b8b-9eba-6c2ba4365a8c` |
| `roadmap:gateway` | `82e07bcd-69fa-4fc5-a2e1-d4d7fa0fad70` |
| `roadmap:dx` | `9f4356e1-f3bc-49a5-b28a-fa1077a6e326` |
| `roadmap:platform` | `c819ff92-c9cf-453d-a0f9-451840f6f8cc` |
| `roadmap:community` | `2de713f1-47a9-49a0-9e84-a7bd947eb707` |
| `roadmap:observability` | `d4ce6487-92fe-4f12-a5f3-8d682e03623f` |

## Step 0: Determine Mode

| Argument | Mode | Description |
|----------|------|-------------|
| (empty) / `--scan` | **Scan** | Read-only report, 0 Linear writes |
| `--create` | **Create** | Batch-create tickets on Linear (20-50 writes) |
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

## Step 2: Scan 6 Sources

### Scanner 1: TODO/FIXME/HACK in Code

Search for actionable code annotations:

```
grep -rn "TODO\|FIXME\|HACK" \
  --include="*.py" --include="*.ts" --include="*.tsx" --include="*.rs" \
  control-plane-api/ control-plane-ui/ portal/ stoa-gateway/ cli/ e2e/
```

Exclude: `archive/`, `node_modules/`, `target/`, `dist/`, `*.test.*`, `*.spec.*`

For each match, extract:
- `file_path:line_number`
- Comment text (the TODO/FIXME/HACK message)
- Component: derive from path (`control-plane-api/` → api, `stoa-gateway/` → gateway, etc.)

**Dedup rule**: group identical TODO text across files (e.g., "TODO: add pagination" in 3 routers = 1 candidate).

### Scanner 2: Test Coverage Gaps

Identify untested modules by comparing source files to test files:

**Python (control-plane-api)**:
- Source routers: `control-plane-api/src/routers/*.py`
- Source services: `control-plane-api/src/services/*.py`
- Tests: `control-plane-api/tests/test_*.py`
- Gap = source file exists but no matching `test_<name>.py`

**TypeScript (control-plane-ui)**:
- Source pages: `control-plane-ui/src/pages/*.tsx`
- Source components: `control-plane-ui/src/components/**/*.tsx`
- Tests: matching `*.test.tsx` in same directory
- Gap = component exists but no matching `.test.tsx`

**TypeScript (portal)**:
- Source: `portal/src/pages/*.tsx`, `portal/src/components/**/*.tsx`
- Tests: matching `*.test.tsx`

**Rust (stoa-gateway)**:
- Source modules: `stoa-gateway/src/**/*.rs`
- Check for `#[cfg(test)]` block presence in each file
- Gap = `.rs` file with no `#[cfg(test)]` section

### Scanner 3: Roadmap Files

Parse 3 local files for backlog items:

**BACKLOG.md** (repo root):
- Parse all `CAB-XXXX` entries from tables and lists
- Extract: ticket ID, title, section name
- Map section to roadmap theme:
  - "MCP Gateway" / "Features Avancees" → `gateway`
  - "Community" → `community`
  - "Observability" / "OpenSearch" → `observability`
  - "Portal & UX" / "DX" → `dx`
  - Everything else → `platform`

**docs/CAPACITY-PLANNING.md**:
- Parse unchecked `[ ]` items from all phases
- Extract: ticket ID (if present), title, phase name, estimate (if present)

**plan.md** (Backlog sections only):
- Parse items from "Backlog" sections of current and next cycle
- Items without checkboxes = parked, not committed

### Scanner 4: DX Gaps

Check for missing developer experience files:

- **Missing READMEs**: check each component dir (`control-plane-api/`, `control-plane-ui/`, `portal/`, `stoa-gateway/`, `cli/`, `e2e/`) for `README.md`
- **Missing .env.example**: check component dirs for `.env.example` or `.env.template`
- **@wip E2E features**: `grep -rn "@wip" e2e/ --include="*.feature"` — count blocked E2E tests
- **K8s gaps**: check `k8s/` and `charts/` dirs for:
  - HPA (HorizontalPodAutoscaler) — any component missing?
  - PDB (PodDisruptionBudget) — any component missing?
  - NetworkPolicy — any namespace missing?

### Scanner 5: Lint Suppressions

Find suppressed lint rules that indicate tech debt:

```
grep -rn "# noqa\|# type: ignore\|eslint-disable\|@ts-ignore\|#\[allow(" \
  --include="*.py" --include="*.ts" --include="*.tsx" --include="*.rs" \
  control-plane-api/ control-plane-ui/ portal/ stoa-gateway/
```

Exclude: `node_modules/`, `target/`, `dist/`

Group by suppression type:
- `# noqa` / `# type: ignore` → Python type safety debt
- `eslint-disable` / `@ts-ignore` → TypeScript lint debt
- `#[allow(...)]` → Rust lint debt

Each cluster of 3+ suppressions of the same rule = 1 candidate ticket.

### Scanner 6: Content Roadmap (conditional)

Only if `stoa-docs` directory exists as sibling or `PLAN-SEO.md` is accessible:

- Parse `PLAN-SEO.md` for unclaimed topics (not marked "Published" or "In Progress")
- Each topic = 1 candidate (type: content-piece)

If not accessible, skip silently and note "Scanner 6 skipped: stoa-docs not available".

## Step 3: Deduplicate Against Linear

For each candidate from Step 2:

1. **Exact match**: if candidate has a `CAB-XXXX` ID, check if it exists in the Linear backlog from Step 1
2. **Fuzzy title match**: tokenize candidate title and each Linear issue title. If token overlap > 70%, flag as duplicate
3. **Mark duplicates**: tag as `[DUP]` and exclude from creation candidates

Report: "X candidates found, Y duplicates removed, Z net new"

## Step 4: Estimate Points

Apply heuristic estimation based on candidate type:

| Type | Base Estimate | Adjustments |
|------|--------------|-------------|
| `untested-router` | 5 pts | +3 if auth-related (users, service_accounts, certificates) |
| `untested-service` | 3 pts | +5 if Keycloak/Kafka integration |
| `untested-component` | 2 pts | +1 if modal/form component |
| `untested-rs-module` | 3 pts | +2 if security/auth module |
| `todo-implementation` | 3 pts | +5 if multi-file or cross-component |
| `fixme-bug` | 3 pts | +2 if in auth/security path |
| `hack-cleanup` | 2 pts | +1 if public API surface |
| `roadmap-item` | existing estimate or 8 pts | EPIC/MEGA keyword → cap at 21 |
| `dx-gap-readme` | 3 pts | — |
| `dx-gap-env` | 2 pts | — |
| `dx-gap-e2e-wip` | 5 pts | +3 if critical path scenario |
| `dx-gap-k8s` | 5 pts | +2 if HPA (scaling) |
| `lint-debt` | 3 pts | per cluster of suppressions |
| `content-piece` | 5 pts | tutorial=8, comparison=5, glossary=13 |

**Cap**: no single auto-generated ticket exceeds 21 pts. Larger items need `/council`.

## Step 5: Score & Rank

Score each candidate for prioritization:

| Factor | Points | Condition |
|--------|--------|-----------|
| Type weight | 3 | `untested-router` or `fixme-bug` (high impact) |
| Type weight | 2 | `todo-implementation`, `dx-gap-k8s`, `content-piece` |
| Type weight | 1 | `lint-debt`, `dx-gap-readme`, `hack-cleanup` |
| Theme bonus | 2 | Matches `--theme` filter (if provided) |
| Size factor | 1 | Estimate <= 5 pts (quick win) |
| Source bonus | 1 | From roadmap files (already validated) |
| Auth/security | 2 | Touches auth, RBAC, secrets, or security code |
| **Max score** | **9** | |

Sort by score descending, then by estimate ascending (prefer quick wins).

## Step 6: Build Plan — Top 50 Candidates

Take top 50 candidates (after dedup), grouped by roadmap theme:

```
Backlog Generation Report
==========================

Current backlog: XX issues, YYY pts | Target: 400 pts
Gap: ZZZ pts needed | Candidates found: NN

By Theme:
---------

gateway (XX pts, N items):
  1. [5 pts] untested-router: stoa-gateway security_headers.rs — no #[cfg(test)]
  2. [3 pts] todo-impl: OTel init in stoa-gateway/src/telemetry.rs:42
  ...

platform (XX pts, N items):
  1. [8 pts] untested-router: applications.py — no test_applications.py
  2. [5 pts] todo-impl: IAM sync in src/services/iam_sync_service.py:87
  ...

dx (XX pts, N items):
  1. [3 pts] dx-gap: Missing README.md in cli/
  2. [5 pts] dx-gap: 4 @wip E2E features blocked
  ...

observability (XX pts, N items):
  ...

community (XX pts, N items):
  ...

Summary:
  Total candidates: NN | Total points: XXX pts
  After creation, backlog would be: YYY pts (target: 400)
  Duplicates removed: DD
  Scanners skipped: [list or "none"]
```

## Step 7: Execute

### Scan mode (`--scan`, default)

Display the report from Step 6. No Linear writes. Exit.

### Create mode (`--create`)

For each candidate (up to 50):

```
linear.create_issue(
  title: "<type>(scope): <description>",
  description: <see template below>,
  team: "624a9948-a160-4e47-aba5-7f9404d23506",
  project: "227427af-6844-484d-bb4a-dedeffc68825",
  assignee: "0543749d-ecde-4edf-aec1-6f372aafafce",
  estimate: <pts from Step 4>,
  priority: 4,
  labels: ["roadmap:<theme>"],
  state: "Backlog"
)
```

**Ticket description template**:

```markdown
## Context
Auto-generated by `/generate-backlog` scanner.
Source: {scanner_name} | File: {file_path}:{line}

## What
{description}

## Estimate Rationale
{type}: {base_pts} pts {adjustments}

## DoD
- [ ] Implementation complete
- [ ] Tests added/updated
- [ ] CI green

---
_Auto-generated by STOA AI Factory `/generate-backlog` — {date}_
```

**Commit title format**: `<conventional_type>(scope): <short description>`
- untested-router → `test(api): add tests for applications router`
- todo-impl → `feat(gateway): implement OTel initialization`
- dx-gap → `chore(dx): add README.md to cli/`
- content-piece → `docs(blog): write MCP protocol deep-dive`

### Themed mode (`--theme <name>`)

Same as `--scan` but filter candidates to only those matching the specified theme
(`gateway`, `dx`, `platform`, `community`, `observability`).

## Step 8: Report & Log

### Final report

```
Backlog Generation Complete
============================
Mode: {scan|create|themed}
Scanners run: 6 (or list skipped)

Candidates:
  Found: XX | Duplicates: YY | Net new: ZZ

{if --create}
Created: NN tickets on Linear (total: XXX pts)
Backlog after: YYY pts (target: 400 pts)
{/if}

{if --scan}
Recommended: run `/generate-backlog --create` to create ZZ tickets (XXX pts)
{/if}

Top 5 by score:
  1. CAB-NEW: <title> (X pts, score: Y)
  2. ...
```

### Operations log (--create mode only)

Append to `~/.claude/projects/-Users-torpedo-hlfh-repos-stoa/memory/operations.log`:

```
STEP-DONE | step=generate-backlog task=backlog-pipeline created=N total_pts=X backlog_depth=Y
```

## MCP Budget

| Call | Purpose | Mode |
|------|---------|------|
| `list_issues(no cycle)` | Inventory current backlog | All |
| `create_issue` x N | Batch create tickets | `--create` only |
| **Total read** | **1 call** | |
| **Total write** | **0 (scan) / 20-50 (create)** | |

## Rules

- **`--scan` is default** — never auto-create without explicit `--create`
- **Cap at 50 tickets per run** — avoid flooding Linear
- **Dedup BEFORE create** — check Linear backlog + fuzzy title match (>70% token overlap)
- **Conservative estimates** — use base heuristics, user adjusts post-creation
- **Theme labels mandatory** — every ticket gets `roadmap:<theme>` label (`roadmap` is a group, cannot be assigned directly)
- **Auto-gen marker** — description includes "Auto-generated by /generate-backlog"
- **Priority 4 (Low) default** — auto-generated tickets are backlog, not urgent
- **State "Backlog"** — never create in "Todo" or "In Progress"
- **No scanner scripts** — this skill is pure SKILL.md (Claude executes the logic inline)
- **Exclude archives** — never scan `archive/`, `node_modules/`, `target/`, `dist/`
- **Group by theme** — report and creation both organized by roadmap theme
- **Log all creates** in operations.log for audit trail
