---
description: AI-native development workflow, session management, context management, and state files protocol
---

# AI Workflow Rules

## Session Lifecycle
1. Read `memory.md` for current state
2. Read `plan.md` for priorities
3. Work on ONE task per session
4. Update `memory.md` before ending session
5. Commit often with conventional messages

## Feature Development (Ship/Show/Ask — see `git-workflow.md`)
1. **Fresh session** (clean context)
2. **Explore**: "Propose 3 options for `<feature>`, don't code"
3. **Choose** one option -> "Plan in 5 steps max, don't code"
4. **Validate** the plan -> user says "Go"
5. **Execute**: branch → code → micro-commits → local quality gate → push → PR → CI green → merge → verify
6. Claude determines **Ship/Show/Ask** mode based on risk level (see `git-workflow.md`)
7. **Ship/Show**: Claude handles the full lifecycle autonomously — no questions asked
8. **Ask**: Claude stops after PR creation, waits for user to say "merge"

## Review (Important Decisions)

| Session | Role | Objective |
|---------|------|-----------|
| Session 1 | Architect | Produce implementation plan |
| Session 2 (fresh) | Staff Engineer | Critical review of plan |
| Session 3 (fresh, optional) | Security Engineer | Security review |

**Binary verdict**: `Go` / `Fix` / `Redo` — no "maybe".

## Context Management

### Context Window Awareness
- **Monitor context usage** — when conversation grows large, proactively delegate research to subagents
- **Delegate early** — use `Explore` agent for codebase searches that may require multiple rounds
- **Protect main context** — keep implementation work inline, push analysis/exploration to subagents
- **Compress state** — after completing a multi-step task, summarize key findings before moving on

### When to Delegate vs Work Inline
- **Inline**: <5 files, iterative user interaction, shared context between steps
- **Subagent**: broad search, verbose output (logs, reports), self-contained analysis, security/k8s read-only

## State Files Update Protocol

### What Are State Files
- `memory.md` (repo root) — session state, ticket tracker, CI status, decisions, known issues
- `plan.md` (repo root) — sprint scoreboard, remaining tasks, DoD matrix
- `~/.claude/projects/.../memory/MEMORY.md` — private persistent memory across conversations
- `~/.claude/projects/.../memory/operations.log` — append-only session traceability log

### Auto-Update Triggers

Update `memory.md` when:
1. **PR merged** — add ticket to DONE with PR number
2. **Ticket completed** — move from NEXT to DONE
3. **New decision made** — add to "Decisions This Sprint"
4. **CI status changes** — update pipeline status table
5. **New known issue discovered** — add to "Known Issues"
6. **Before session end** — always, even if no trigger above

Update `plan.md` when:
1. **PR merged** — mark as merged in scoreboard
2. **New task added to sprint** — add row to scoreboard
3. **Task blocked/unblocked** — update blocker column

Update private `MEMORY.md` when:
1. **New ticket completed** — add to relevant section
2. **New gotcha discovered** — add to `gotchas.md`
3. **Infra state changes** — update infra sections
4. **CI workaround found** — add to CI Known Issues

### Update Format
- Keep entries **concise** — one line per item, link to PR/commit
- Use **consistent date format**: 2026-MM-DD
- **Never delete DONE items** from memory.md — they serve as audit trail
- **Archive** items older than 2 sprints to reduce noise

### Item State Machine (MANDATORY)

Every trackable item follows this lifecycle — no exceptions, no shortcuts:

```
PENDING ──→ IN_PROGRESS ──→ DONE ──→ ARCHIVED
   │              │
   └── BLOCKED ◄──┘
```

#### Markers by File

| State | plan.md | memory.md text | memory.md section |
|-------|---------|----------------|-------------------|
| PENDING | `[ ]` | No bold marker | `📋 NEXT` |
| IN_PROGRESS | `[~]` | Sub-items may be ✅ but parent has `[ ]` remaining | `🔴 IN PROGRESS` |
| DONE | `[x]` | `— DONE` suffix or all sub-items ✅ | `✅ DONE` |
| BLOCKED | `[!]` | `— BLOCKED` suffix + reason | `🚫 BLOCKED` |

#### Structural Invariants (must be true at ALL times)

These 5 rules are non-negotiable. Violating any one = state file drift.

1. **No DONE in active sections** — if an item text contains `**DONE**`, `— DONE`, or has ALL sub-items marked ✅ with zero `[ ]` remaining, it MUST be in `✅ DONE` section. Never leave a completed item in `🔴 IN PROGRESS` or `📋 NEXT`.
2. **Checkbox ↔ section parity** — `[x]` in plan.md = item in `✅ DONE` in memory.md. `[~]` = `🔴 IN PROGRESS`. `[ ]` = `📋 NEXT`. No cross-state mismatches.
3. **Single home rule** — an item appears in exactly ONE section of memory.md. Duplicates across sections are forbidden.
4. **Partial completion** — if a parent task has both ✅ and `[ ]` sub-items, the parent stays `[~]` in `🔴 IN PROGRESS`. Promote to `[x]` + `✅ DONE` only when ALL sub-items are complete.
5. **Strikethrough = moved** — `~~item~~` in a section means it was relocated. Remove the strikethrough entry within 1 session to avoid clutter.

#### Atomic State Transitions

When an item changes state, perform ALL updates in a **single edit pass** — never split across separate tool calls or "I'll do it later":

| Transition | plan.md | memory.md | MEMORY.md (private) |
|------------|---------|-----------|---------------------|
| Start work | `[ ]` → `[~]` | Move from `📋 NEXT` → `🔴 IN PROGRESS` | Update Active Tickets |
| Complete | `[~]` → `[x]` | Add `— DONE (PR #N)` + move from `🔴 IN PROGRESS` → `✅ DONE` | Update Active Tickets |
| Block | `[~]` → `[!]` | Move to `🚫 BLOCKED` + add reason | Update Active Tickets |
| Unblock | `[!]` → `[~]` | Move back to `🔴 IN PROGRESS` | Update Active Tickets |

**Root cause of past drift**: sessions marked items as `**DONE**` in the text but never moved them to the `✅ DONE` section. The text marker and the section move MUST happen together — always.

### Session-End State Lint (MANDATORY before SESSION-END log)

Before logging `SESSION-END`, run these 4 checks mentally. If any fails, fix it before ending.

| # | Check | Scan target | Pass criteria |
|---|-------|-------------|---------------|
| 1 | No DONE in IN_PROGRESS | `🔴 IN PROGRESS` section of memory.md | Zero items with `**DONE**`, `— DONE`, or all-✅ sub-items |
| 2 | No DONE in NEXT | `📋 NEXT` section of memory.md | Zero items with `**DONE**`, `— DONE`, or `~~strikethrough~~` |
| 3 | Stale `[~]` check | plan.md | Every `[~]` item has at least one `[ ]` sub-item remaining |
| 4 | Cross-file parity | plan.md vs memory.md | Each `[x]` in plan.md → matching entry in `✅ DONE`. Each `[~]` → in `🔴 IN PROGRESS` |

**Enforcement**: failing this lint is equivalent to pushing code with broken tests. Fix before SESSION-END — no exceptions.

## Operation Logging (Traceability)

### Log Location
`~/.claude/projects/.../memory/operations.log` — append-only, never edit existing entries.

### Event Types

| Event | Trigger | Required Fields |
|-------|---------|----------------|
| `SESSION-START` | Session begins work on a task | `task`, `branch` |
| `SESSION-END` | Session ends (success, paused, or crash detected) | `task`, `status` |
| `STEP-START` | Major step begins (code, test, pr, merge, cd) | `step`, `task` |
| `STEP-DONE` | Major step completes | `step`, `task` |
| `CHECKPOINT` | Pre-merge/deploy checkpoint created | `task`, `file` |
| `ERROR` | Non-fatal error during execution | `task`, `error` |
| `RECOVERY` | Crash recovery action taken | `task`, `action` |

### Format Rules
- Timestamp: ISO 8601 short (`YYYY-MM-DDTHH:MM`)
- Separator: ` | ` (space-pipe-space)
- Fields: `key=value` pairs, space-separated
- Append-only: never edit or delete existing log entries
- One line per event, no multiline

### Mandatory Events
Every session MUST have at minimum:
1. `SESSION-START` — logged when work begins on a task
2. `SESSION-END` — logged when session ends, even on early exit

Missing `SESSION-END` = crash indicator (see `crash-recovery.md`).

### Checkpoint Directory
`~/.claude/projects/.../memory/checkpoints/` — JSON files created before risky operations.
See `crash-recovery.md` for checkpoint schema and lifecycle.

## Anti-Drift Rules
- **1 thing at a time** — never mix feature + refactor + fix
- **Never code without a validated plan**
- **Red flags** (broken tests, tech debt, security flaw) -> fix before continuing
- **If > 10 min structuring manually** -> STOP, use Claude Code
- **State files are mandatory** — skipping memory.md update is a workflow violation
- **Operation log is mandatory** — every session MUST have SESSION-START and SESSION-END entries
- **Atomic transitions only** — marking an item `**DONE**` without moving it to the `✅ DONE` section is forbidden (see Item State Machine above)
- **Session-End State Lint** — run the 4-check lint before every SESSION-END. Inconsistent state files = workflow violation equivalent to broken tests on main
