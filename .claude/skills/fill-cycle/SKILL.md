---
name: fill-cycle
description: "Analyze cycle capacity gap and propose backlog items to fill the sprint to ~80% of proven velocity."
argument-hint: "[--check | --auto | --theme <name> | empty for interactive]"
---

# Fill Cycle — Velocity Pipeline

Load the current Linear cycle, compute the capacity gap against proven velocity,
scan 4 backlog sources, and propose a ranked fill plan.

Target: $ARGUMENTS

## Linear Label IDs (cached)

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
| (empty) | **Interactive** | Show fill plan, ask before promoting |
| `--check` | **Read-only** | Compute capacity report only, no writes (CI-safe) |
| `--auto` | **Auto-promote** | Promote quick wins automatically, suggest council for MEGAs |
| `--theme <name>` | **Themed fill** | Filter candidates by roadmap theme + optional Notion search |

## Step 1: Fetch Current Cycle from Linear

```
linear.list_cycles(teamId: "624a9948-a160-4e47-aba5-7f9404d23506")
```

Identify the **current** cycle (type `"current"` or date range containing today).
Extract: `cycle_id`, `name`, `start`, `end`, `scopeTotal`, `completedTotal`.

Then fetch all issues in the cycle:

```
linear.list_issues(
  team: "624a9948-a160-4e47-aba5-7f9404d23506",
  cycle: "<cycle_id>",
  first: 50
)
```

Compute:
- `cycle_days` = (end - start).days
- `days_remaining` = (end - today).days
- `pts_committed` = sum of all issue estimates in cycle
- `pts_done` = sum of estimates for Done/Canceled issues

## Step 2: Read Velocity Baseline

Read `~/.claude/projects/-Users-torpedo-hlfh-repos-stoa/memory/velocity.json`.

Extract:
- `rolling_avg_pts_per_day` = `rolling_avg_3.pts_per_day`
- `target_utilization` (default 0.80)

Compute capacity gap:
```
capacity = rolling_avg_pts_per_day × cycle_days
target = capacity × target_utilization
gap = target - pts_committed
```

If `gap <= 0`: report "Cycle is fully loaded" and stop (unless `--check` which still reports).

## Step 3: Scan Backlog Sources

Scan 4 sources for candidate items. Each source contributes candidates with metadata.

### Source 1: Linear Backlog (unassigned, no cycle)

```
linear.list_issues(
  team: "624a9948-a160-4e47-aba5-7f9404d23506",
  first: 50
)
```

Filter for issues where:
- `cycle` is null (not in any cycle)
- `status` is "Backlog" or "Todo"
- `assignee` is null or matches current user

Extract: id, identifier, title, priority, estimate, labels.

### Source 2: BACKLOG.md (post-MVP items)

Read `BACKLOG.md` from repo root.

Parse all `CAB-XXXX` entries from tables and lists. Extract:
- Ticket ID, title, section (Post-MVP, Vision, MCP, Community, etc.)
- Map section to roadmap theme:
  - "MCP Gateway" / "Features Avancées" → `gateway`
  - "Community" → `community`
  - "Observability" → `observability`
  - "Portal & UX" → `platform`
  - "Infra & DevOps" → `platform`
  - "Architecture" → `platform`
  - "Vision & Strategy" → `platform`

### Source 3: plan.md (parked backlog sections)

Read `plan.md` from repo root.

Parse entries from:
- "Backlog — Long-term" section (current cycle)
- "Backlog" section of next cycle
- Any item without a checkbox (parked, not committed)

Extract: ticket ID, title, estimate (if present), priority.

### Source 4: CAPACITY-PLANNING.md (phased roadmap)

Read `docs/CAPACITY-PLANNING.md`.

Parse unchecked `[ ]` items from remaining phases:
- Phase 2.6, 4, 5, 6, 7, 8, 9, 10, 11, 14
- Extract: ticket ID, title, phase name

Map phase to roadmap theme:
- Phase 2.6 (Cilium), 5 (Multi-env) → `platform`
- Phase 4 (OpenSearch) → `observability`
- Phase 7 (Security) → `gateway`
- Phase 8 (Portal) → `dx`
- Phase 9 (Ticketing) → `platform`
- Phase 6 (Demo) → `community`
- Phase 10, 11 (Resource Lifecycle) → `platform`
- Phase 14 (GTM) → `community`

### Source 5 (conditional): Notion — only with `--theme`

If `--theme <name>` is provided:

```
notion.notion-search(query: "STOA roadmap <theme>")
```

Extract any actionable items not already in Linear. Flag as "Notion-sourced" in output.

## Step 4: Deduplicate & Score Candidates

Merge all candidates. Deduplicate by `CAB-XXXX` identifier (Linear source wins if conflict).

Score each candidate (higher = better fit):

| Factor | Points | Condition |
|--------|--------|-----------|
| Priority | 3 × (5 - priority_value) | P1=12, P2=9, P3=6, P4=3 |
| Has estimate | 2 | `estimate` is not null |
| Already in Linear | 1 | Source is Linear backlog |
| Theme match | 2 | Matches `--theme` filter (if provided) |
| **Max score** | **17** | |

Sort by score descending.

## Step 5: Classify into 3 Buckets

### Bucket 1: Quick Wins (promote now)
- Estimate <= 8 pts
- Already in Linear (has issue ID)
- Not an EPIC or MEGA (no `[MEGA]` or `[EPIC]` in title)

### Bucket 2: MEGAs (need council + decompose)
- Estimate > 13 pts OR title contains `[MEGA]` / `[EPIC]`
- Suggest: run `/council CAB-XXXX` then `/decompose CAB-XXXX`

### Bucket 3: Unpointed (flag for estimation)
- No estimate value
- Action: "Estimate before promoting"

## Step 6: Build Fill Plan

Cap at **top 15 candidates** total across all buckets.

Within the gap budget:
1. Fill with Quick Wins first (sum estimates, stop when gap reached)
2. If gap remains > 13 pts: suggest 1 MEGA
3. List remaining Unpointed items as "estimate to unlock"

Group MEGAs by roadmap theme for readability.

## Step 7: Execute (mode-dependent)

### Interactive mode (default)
Display the fill plan. For each Quick Win, ask: "Promote Y/N?"
On Y: `linear.update_issue(id, cycleId: "<current_cycle_id>")`

### Auto mode (`--auto`)
Promote all Quick Wins automatically:
```
linear.update_issue(id: "<issue_id>", cycleId: "<current_cycle_id>")
```
Log each promotion in operations.log.

### Check mode (`--check`)
Display the capacity report only. No Linear writes. Exit.

### Themed mode (`--theme <name>`)
Same as interactive but filtered by theme. Includes Notion results if available.

## Step 8: Update State Files

After any promotions:
1. Run `/sync-plan` to refresh plan.md with newly promoted issues
2. Append to operations.log:
   ```
   STEP-DONE | step=fill-cycle task=velocity-pipeline promoted=N gap_before=X gap_after=Y
   ```

## Step 9: Report

```
Capacity Report — Cycle N (dates)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Velocity baseline (rolling 3-cycle avg):
  Avg: XX.X pts/day | Target utilization: 80%

Current cycle:
  Committed: XXX pts | Done: YYY pts (ZZ%)
  Capacity: AAA pts | Target: BBB pts (80%)
  Gap: CCC pts (DD% under-loaded)

Fill Plan:
━━━━━━━━━
Quick Wins (promote now):                    Σ XX pts
  1. CAB-XXXX: Title (N pts, P2) ............. [score: 14]
  2. CAB-YYYY: Title (N pts, P1) ............. [score: 17]

MEGAs (→ /council + /decompose):             Σ XX pts
  [gateway] CAB-ZZZZ: Title (21 pts, P2)
  [platform] CAB-WWWW: Title (34 pts, P3)

Unpointed (estimate to unlock):
  CAB-VVVV: Title (no estimate, P2)

Summary:
  Promotable: XX pts | After fill: YYY/ZZZ pts (WW%)
  MEGAs needing council: N
  Unpointed needing estimate: M
```

## MCP Budget

| Call | Purpose | Mode |
|------|---------|------|
| `list_cycles` | Get current cycle | All |
| `list_issues(cycle=X)` | Get cycle issues | All |
| `list_issues(no cycle)` | Get backlog issues | All |
| `notion-search` | Themed search | `--theme` only |
| `update_issue` × N | Promote quick wins | Interactive/Auto only |
| **Total read** | **3-4 calls** | |
| **Total write** | **0-15 calls** | |

## Rules

- **velocity.json is the single source of truth** for capacity baseline
- **80% target utilization** leaves 20% for unplanned work (configurable in velocity.json)
- **Cap proposals at 15** — avoid overwhelming fill plans
- **MCP budget: 3-4 read calls** per run — batch, don't poll
- **BACKLOG.md items stay unpointed** until promoted (estimation happens at promotion time)
- **No auto-promote in `--check` mode** — always read-only (CI-safe)
- **No Notion call without `--theme`** — avoid unnecessary MCP latency
- **Quick Wins first** — fill with small items before suggesting MEGAs
- **Never promote without estimate** — Unpointed items must be estimated first
- **Log all promotions** in operations.log for audit trail
