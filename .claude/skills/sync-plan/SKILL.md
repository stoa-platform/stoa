---
name: sync-plan
description: Bidirectional sync between plan.md and Linear tickets. Detects drift, updates markers, reorders by priority.
argument-hint: "[CAB-XXXX for single ticket, or empty for full sync]"
---

# Plan ↔ Linear Sync

Synchronize plan.md with Linear ticket statuses.

Target: $ARGUMENTS

## Step 1: Parse plan.md

Read `plan.md` and extract all `CAB-XXXX` references with their current markers:

| Marker | Meaning |
|--------|---------|
| `- [x]` | Done locally |
| `- [~]` | Partially done |
| `- [ ]` | Not started or pending |
| `**DONE**` | Completed (in memory.md style) |

Extract ticket IDs using pattern: `CAB-\d{3,4}`

## Step 2: Fetch Linear Statuses

If single ticket ($ARGUMENTS = CAB-XXXX):
```
linear.get_issue("CAB-XXXX") → status, priority, estimate, assignee
```

If full sync (no argument or >5 tickets):
```
linear.list_issues(
  project: "227427af-6844-484d-bb4a-dedeffc68825",
  first: 50
)
```

For <= 5 tickets, use individual `get_issue` calls.

## Step 3: Detect Drift

Compare plan.md markers vs Linear statuses:

| plan.md | Linear | Drift? | Action |
|---------|--------|--------|--------|
| `[x]` | Done | No | Skip |
| `[x]` | In Progress | Yes | **Warning**: plan.md says done but Linear disagrees |
| `[ ]` | Done | Yes | Update plan.md → `[x]` |
| `[ ]` | In Progress | Yes | Update plan.md → `[~]` |
| `[~]` | Done | Yes | Update plan.md → `[x]` |
| `[~]` | Todo | Yes | Update Linear → In Progress |
| Not in plan | Exists in Linear | — | Report: "CAB-XXXX exists in Linear but not in plan.md" |

## Step 4: Apply Updates

### Direction: Linear → plan.md (default)

Update plan.md markers to match Linear reality:
- `Done` in Linear → `[x]` in plan.md
- `In Progress` in Linear → `[~]` in plan.md
- `Canceled` in Linear → strikethrough in plan.md

### Direction: plan.md → Linear (when user says `--push`)

- `[x]` in plan.md → `linear.update_issue(status="Done")`
- `[~]` in plan.md → `linear.update_issue(status="In Progress")`
- `[ ]` with priority change → `linear.update_issue(priority=N)`

## Step 5: Priority Reorder

After sync, reorder plan.md sections by Linear priority:
1. P0 (Urgent) items first
2. P1 (High) second
3. P2 (Normal) third
4. P3 (Low) last

Only reorder within the same section (don't move items between sections).

## Step 6: Report

```
Sync Results:
- Tickets scanned: N
- Updates applied (Linear → plan.md): N
- Updates applied (plan.md → Linear): N
- Drift detected: N items
- New in Linear (not in plan): N items

Changes:
  CAB-XXXX: [ ] → [x] (Linear: Done)
  CAB-YYYY: [~] → [x] (Linear: Done)
  CAB-ZZZZ: Not in plan (Linear: Todo, 8 pts, P2)

plan.md updated. Review changes with `git diff plan.md`.
```

## Rules

- **Never delete lines** from plan.md — only update markers and add new entries
- **Preserve formatting** — keep existing indentation, bullet style, section headers
- **Log sync** in operations.log: `MCP-CALL | service=linear action=sync-plan tickets=N`
- **Conflict resolution**: if plan.md and Linear disagree, **Linear wins** by default
- **Rate limiting**: max 20 `get_issue` calls per sync (use `list_issues` batch for larger sets)
- **No auto-commit** — show diff to user, let them decide whether to commit
- **Cycle awareness**: when listing issues, filter by current cycle if available
