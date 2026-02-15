---
name: sync-plan
description: "Cycle-aware bidirectional sync between plan.md and Linear. Discovers all cycle tickets, detects drift, updates markers."
argument-hint: "[CAB-XXXX | --push | --cycles | empty for full sync]"
---

# Plan ↔ Linear Sync (Cycle-Aware)

Synchronize plan.md with Linear ticket statuses using cycle-driven discovery.

Target: $ARGUMENTS

## Step 0: Determine Sync Mode

| Argument | Mode | Description |
|----------|------|-------------|
| (empty) | **Full sync** | Fetch current + next cycle, detect all drift |
| `CAB-XXXX` | **Single ticket** | Fetch one ticket, update plan.md marker |
| `--push` | **Push to Linear** | Push plan.md markers → Linear statuses |
| `--cycles` | **Cycle discovery** | Show current + next cycle summary only |

## Step 1: Fetch Linear Cycles

Always start by discovering the active cycles:

```
linear.list_cycles(teamId: "624a9948-a160-4e47-aba5-7f9404d23506")
```

Identify:
- **Current cycle**: `type: "current"` or dates containing today
- **Next cycle**: `type: "upcoming"` or starts after current ends

Extract: cycle ID, name, start date, end date, scope (total issues), completed count.

## Step 2: Fetch Cycle Issues

For each active cycle (current + next):

```
linear.list_issues(
  team: "624a9948-a160-4e47-aba5-7f9404d23506",
  cycle: "<cycle_id>",
  first: 50
)
```

For each issue, extract: `identifier`, `title`, `status`, `priority` (value + name), `estimate` (value), `cycleId`, `completedAt`.

**Important**: The `status` field is a string ("Done", "In Progress", "Todo", "Backlog", "Canceled", "Duplicate"), NOT a nested object.

**Priority mapping**: `priority` is `{value: N, name: "..."}` where 1=Urgent, 2=High, 3=Normal, 4=Low.

**Estimate mapping**: `estimate` is `{value: N, name: "..."}` where N is fibonacci points (1,2,3,5,8,13,21,34,55).

## Step 3: Parse plan.md

Read `plan.md` and extract all `CAB-XXXX` references with their current markers:

| Marker | Meaning |
|--------|---------|
| `- [x]` | Done locally |
| `- [~]` | Partially done |
| `- [ ]` | Not started or pending |

Extract ticket IDs using pattern: `CAB-\d{3,4}`

Also identify which **cycle section** each ticket is in (e.g., "Cycle 7 — CURRENT" vs "Cycle 8 — NEXT").

## Step 4: Detect Drift (3 categories)

### 4a. Marker Drift (ticket in both plan.md and Linear)

| plan.md | Linear | Drift? | Action |
|---------|--------|--------|--------|
| `[x]` | Done | No | Skip |
| `[x]` | In Progress | Yes | **Warning**: plan.md says done but Linear disagrees |
| `[ ]` | Done | Yes | Update plan.md → `[x]` |
| `[ ]` | In Progress | Yes | Update plan.md → `[~]` |
| `[~]` | Done | Yes | Update plan.md → `[x]` |
| `[~]` | Todo | Yes | Update Linear → In Progress |
| any | Canceled/Duplicate | Yes | Strikethrough in plan.md |

### 4b. Missing from plan.md (ticket in Linear cycle but NOT in plan.md)

This is the **most critical** category — the root cause of past drift.

For each issue in the cycle that has NO matching `CAB-XXXX` in plan.md:
- Report: `CAB-XXXX: NOT IN PLAN (Linear: <status>, <points> pts, <priority>)`
- Propose: add to the appropriate cycle section in plan.md

### 4c. Orphan in plan.md (ticket in plan.md but NOT in any active cycle)

For each `CAB-XXXX` in plan.md that isn't in current or next cycle:
- If status is Done → keep in Done section (historical)
- If status is Todo/In Progress → **Warning**: ticket not assigned to any cycle

## Step 5: Apply Updates

### Direction: Linear → plan.md (default)

1. Update markers for existing tickets (4a)
2. **Add missing tickets** from cycle to plan.md (4b) — in the correct cycle section
3. Move tickets between cycle sections if `cycleId` changed
4. Reorder within each section by priority (P1 first, P4 last)

### Direction: plan.md → Linear (when user says `--push`)

- `[x]` in plan.md → `linear.update_issue(status="Done")`
- `[~]` in plan.md → `linear.update_issue(status="In Progress")`
- `[ ]` with priority change → `linear.update_issue(priority=N)`

## Step 6: Regenerate plan.md Structure

plan.md follows this exact structure:

```markdown
# Sprint Plan — STOA Platform

> Auto-synced with Linear via `/sync-plan`. Source of truth: Linear cycles.
> Last sync: YYYY-MM-DD

## Cycle N (dates) — CURRENT

**Scope**: X pts | **Done**: Y pts | **Velocity**: Z issues closed
**Theme**: <from cycle description or memory.md>

### In Progress
- [~] CAB-XXXX: Title (N pts, PN)
  - ✅ completed sub-item
  - [ ] remaining sub-item

### Todo
- [ ] CAB-XXXX: Title (N pts, PN)

### Done (N issues)
- [x] CAB-XXXX: Title (N pts) — PR #N

---

## Cycle N+1 (dates) — NEXT

**Theme**: <description>

### Todo
- [ ] CAB-XXXX: Title (N pts, PN)

### Backlog (parked in cycle, not committed)
- CAB-XXXX: Title (PN)

---

## Milestones
(preserved from existing plan.md)

## KPIs Demo
(preserved from existing plan.md)

## Regles
1. **Linear is source of truth** — plan.md is a view, not the master
2-N. (preserved from existing plan.md)
```

**Preservation rules**:
- NEVER delete sub-items under `[~]` tickets (they contain PR references and manual progress)
- NEVER delete the Milestones, KPIs Demo, or Regles sections
- When adding a new ticket, format: `- [ ] CAB-XXXX: <title> (<estimate> pts, P<priority>)`
- Done tickets with PR references: preserve the `— PR #N` suffix

## Step 7: Compute Metrics

Calculate and display:
- **Scope**: sum of all estimates in current cycle
- **Done**: sum of estimates for Done issues
- **Velocity**: count of Done issues
- **Completion %**: Done / Scope
- **Burn rate**: issues completed per day (based on cycle start date)

## Step 8: Report

```
Sync Results (YYYY-MM-DD):
━━━━━━━━━━━━━━━━━━━━━━━━━

Cycle N (current): X/Y pts done (Z%)
Cycle N+1 (next): A issues planned

Drift detected: N items
  CAB-XXXX: [ ] → [x] (Linear: Done)
  CAB-YYYY: [~] → [x] (Linear: Done)

Missing from plan.md: N items
  CAB-ZZZZ: Added (Linear: Todo, 8 pts, P2)
  CAB-WWWW: Added (Linear: In Progress, 3 pts, P1)

Orphans (in plan, not in cycle): N items
  CAB-VVVV: In Done section (OK — historical)

Updates applied: N (Linear → plan.md)
Updates pushed: N (plan.md → Linear) [only if --push]

plan.md updated. Review changes with `git diff plan.md`.
```

## Rules

- **Never delete lines** from plan.md — only update markers and add new entries
- **Preserve sub-items** — manual progress notes under `[~]` tickets are sacred
- **Preserve sections** — Milestones, KPIs, Regles sections are manually maintained
- **Log sync** in operations.log: `MCP-CALL | service=linear action=sync-plan tickets=N cycles=current+next`
- **Conflict resolution**: Linear wins by default (plan.md is a view)
- **Rate limiting**: max 20 `get_issue` calls per sync (use `list_issues` batch)
- **No auto-commit** — show diff to user, let them decide whether to commit
- **Cycle-first discovery** — always fetch by cycle, not just by project. This ensures tickets added to a cycle in Linear automatically appear in plan.md
- **Backlog/Duplicate/Canceled**: skip these statuses when adding to plan.md Todo section. Only include in Backlog subsection of next cycle (without checkbox).
- **Last sync timestamp**: always update the `> Last sync:` line in plan.md header
