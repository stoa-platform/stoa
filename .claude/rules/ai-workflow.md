---
description: AI-native development workflow, session management, context management, and state files protocol
globs: "memory.md,plan.md,.claude/**"
---

# AI Workflow Rules

> **HEGEMON Foundation**: Universal state files protocol and session lifecycle live in `hegemon/rules/state-files.md` + `hegemon/rules/session-lifecycle.md`.
> This file contains STOA-specific extensions (feature dev patterns, context management, state files protocol).
> **Shared behavioral rules** (State Machine, Logging, Anti-Drift): see `workflow-essentials.md`.

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
6. Claude determines **Ship/Show/Ask** mode based on risk level (see `workflow-essentials.md`)
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
- `plan.md` (repo root) — cycle-driven sprint view (synced from Linear via `/sync-plan`)
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
1. **PR merged** — mark ticket as `[x]` in the correct cycle section
2. **`/sync-plan` run** — cycle-driven sync from Linear
3. **Task blocked/unblocked** — update marker `[~]` ↔ `[!]`
4. **Cycle rollover** — current becomes historical, next becomes current

### plan.md Structure (Cycle-Driven)

plan.md is a **view** of Linear cycles, NOT a manually curated document. Structure:

```
# Sprint Plan — STOA Platform
> Last sync: YYYY-MM-DD

## Cycle N (dates) — CURRENT
### In Progress    → [~] tickets with sub-items
### Todo           → [ ] tickets ordered by priority
### Done (N)       → [x] tickets with PR references

## Cycle N+1 (dates) — NEXT
### Todo           → [ ] planned tickets
### Backlog        → parked items (no checkbox)

## Milestones      → manually maintained
## KPIs Demo       → manually maintained
## Regles          → manually maintained
```

**Key rules**:
- Linear is source of truth; plan.md is a read-only view (except sub-items under `[~]` which are manual)
- `/sync-plan` discovers ALL tickets in a cycle — tickets added in Linear appear automatically
- Milestones, KPIs, Regles sections are preserved across syncs (not from Linear)

### Phase-Enriched MEGAs

Decomposed MEGA tickets in plan.md include phase sub-headers with ownership metadata:

```
- [~] CAB-1290: [MEGA] Gateway Live-Code (13 pts) — 2 phases
  - **Phase 1** (parallel) [owner: t4821]
    - [~] CAB-1350 [gateway] Traceparent injection — PR #578
    - [ ] CAB-1351 [gateway] Resource listing
  - **Phase 2** (after Phase 1) [owner: —]
    - [ ] CAB-1352 [e2e] Integration tests
```

**Phase markers**: `[owner: t4821]` = claimed, `[owner: —]` = available.
Phase dependency: `(parallel)`, `(after Phase 1)`, `(after Phase 1+2)`.

**Rules**: Phase ownership markers are local metadata, NOT from Linear. `/sync-plan` MUST preserve `[owner: X]` markers. See `phase-ownership.md`.

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

### Item State Machine, Session-End Lint, Operation Logging, Anti-Drift

→ See `workflow-essentials.md` for the single source of truth on:
- Item State Machine (PENDING → CLAIMED → IN_PROGRESS → DONE → ARCHIVED)
- Structural Invariants (5 non-negotiable rules)
- Atomic State Transitions
- Session-End State Lint (4 mandatory checks)
- Operation Logging (event types, format, mandatory events)
- Session Metrics (PR-MERGED, CI-FIX, STATE-DRIFT, PHASE-* events)
- Anti-Drift Rules

### Checkpoint Directory
`~/.claude/projects/.../memory/checkpoints/` — JSON files created before risky operations.
See `crash-recovery.md` for checkpoint schema and lifecycle.

### Metrics Log Rotation
- Keep `metrics.log` under **500 lines**
- When over 500 lines: move oldest to `metrics.log.1` (90-day retention)
- Clean up during session-end
