---
description: Session lifecycle — startup, state files, context management, and end-of-session protocol
globs: "memory.md,plan.md,.claude/hooks/**,.claude/session-brief.json"
---

# Session Lifecycle

> **HEGEMON Foundation**: Universal state files protocol and session lifecycle live in `hegemon/rules/state-files.md` + `hegemon/rules/session-lifecycle.md`.
> This file contains STOA-specific extensions.
> **Shared behavioral rules** (State Machine, Logging, Anti-Drift): see `workflow-essentials.md`.

## Step 0 — Crash Recovery + Session Log

Before reading state files, check for crashed sessions and log this session:

1. Read last 20 lines of `~/.claude/projects/.../memory/operations.log`
2. Look for `SESSION-START` without matching `SESSION-END`
3. If crashed session detected:
   - Check `~/.claude/projects/.../memory/checkpoints/` for latest checkpoint
   - If checkpoint has `pr_number`, run `gh pr view <pr_number> --json state` — if MERGED, auto-close
   - Otherwise report to user: "Previous session crashed mid-task [TASK] at step [STEP]. Resume or abandon?"
   - Follow `crash-recovery.md` protocol
4. **Instance identity**: The SessionStart hook (`session-init.sh`) auto-generates `STOA_INSTANCE_ID` via env file.
   If `$STOA_INSTANCE_ID` is set, use it. Otherwise generate: `t<N>-<R>` (N = epoch mod 100000, R = 4 hex)
5. If no crash → **log this session immediately**:
   `SESSION-START | task=<TASK> branch=<BRANCH> instance=<ID>` — MUST happen before any work.

## Step 1 — Read State

1. **IF** `.claude/session-brief.json` exists AND is < 5 min old:
   - Read the brief (~500 tokens) — skip full `memory.md` + `plan.md` read
2. **ELSE** (fallback):
   - Read `memory.md` (repo root) + `plan.md` (repo root)
3. **IF** task has CAB-XXXX ID → use brief summary or call `linear.get_issue()` for full DoD

Private memory (`~/.claude/projects/.../memory/MEMORY.md`) is auto-loaded by Claude Code.

## Step 2 — Pick Your Phase

Phase-aware task selection. See `phase-ownership.md` for full protocol.

1. If user gives a specific task → use that (skip to step 5)
2. Read `plan.md` → identify current cycle items (In Progress + Todo)
3. **MEGA with phases**: Read `.claude/claims/<MEGA-ID>.json`, find first unclaimed unblocked phase, claim it
4. **Standalone tickets**: Check `.claude/claims/<CAB-XXXX>.json`, claim if available
5. If task has **CAB-XXXX** ID → `linear.get_issue("CAB-XXXX", includeRelations=true)`
6. If no unclaimed work → report available MEGAs

### Effort Level Routing

| Task Mode | Effort | When |
|-----------|--------|------|
| **Ship** (docs, config, style, deps) | `low` | `/effort low` + `/fast` |
| **Show** (refactor, tests, bug fix) | `medium` | Default |
| **Ask** (features, security, MEGAs) | `high` | `/effort high` |

Subagent Explore calls should use `model: haiku` for cost efficiency.

## Step 3 — Context Budget

With 1M context on Opus 4.6:

- **Target**: stay under **80% context**
- **At 60%**: delegate remaining research to subagents
- **At 80%**: use `/compact` to compress conversation
- **At 90%**: wrap up, commit, update state files, fresh session
- **Never** go past 95%

Use `/clear` between unrelated tasks.

### Orchestrator Override (Pane 0)
- Target: **60%** context. `/compact` at 50%, `/clear` at 70%.
- Never open code files — delegate to Explore subagents.

### When to Delegate vs Work Inline
- **Inline**: <5 files, iterative user interaction, shared context
- **Subagent**: broad search, verbose output, self-contained analysis, read-only

## Step 4 — Work

Follow the appropriate pattern from `ai-factory.md` (Pattern 3/5/7 for features, Pattern 1/2 for reviews).

### Feature Development (Ship/Show/Ask — see `git-workflow.md`)
1. **Explore**: "Propose 3 options, don't code"
2. **Choose** one → "Plan in 5 steps max, don't code"
3. **Validate** → user says "Go"
4. **Execute**: branch → code → micro-commits → quality gate → push → PR → CI → merge → verify
5. **Ship/Show**: full lifecycle, no questions. **Ask**: stop after PR creation.

### Review (Important Decisions)

| Session | Role | Objective |
|---------|------|-----------|
| Session 1 | Architect | Implementation plan |
| Session 2 (fresh) | Staff Engineer | Critical review |
| Session 3 (optional) | Security Engineer | Security review |

**Binary verdict**: `Go` / `Fix` / `Redo`.

### Inline S2 — Queue-Sourced Tickets (Contabo Workers)

When ticket arrives from dispatch-daemon queue (mode field present):
- IF `mode != 'ship'` AND `estimate > 5`: write plan → self-validate (4 Council personas) → implement if >= 7.0
- ELSE: implement directly

### Phase Chaining (after PR merge, same MEGA)

1. Only chain if context usage < **70%**
2. Release completed phase, scan for next unclaimed unblocked phase
3. If found → claim it, continue. If none → end session.

## Step 5 — End Session

1. Update `memory.md` with results
2. Update `plan.md` if task status changed
3. **State Lint (MANDATORY)** — see `workflow-essentials.md` for 5-check protocol
4. **Linear MCP sync** (if task has CAB-XXXX ID):
   - **Standalone**: PR merged → `linear.update_issue(status="Done")` + comment
   - **Sub-ticket of MEGA**: mark sub-ticket Done, check siblings. If ALL Done → `/verify-mega`
   - **MEGA parent**: NEVER mark Done directly — always `/verify-mega`
   - Blocked → `linear.update_issue(status="Blocked")` + comment
5. **Metrics**: `PR-MERGED | task=<T> pr=<N>` to metrics.log
6. **HEGEMON EXTRACT**: ask "What did I learn that applies beyond this project?" → `/extract` if reusable
7. **Learning loop**: add CI failures/gotchas to `gotchas.md`
8. **Log**: `SESSION-END | task=<TASK> status=<success|paused> pr=<NUMBER>`
9. **Cleanup**: delete checkpoints older than 7 days

## State Files Protocol

### What Are State Files
- `memory.md` — session state, ticket tracker, CI status, decisions
- `plan.md` — cycle-driven sprint view (synced from Linear via `/sync-plan`)
- `~/.claude/projects/.../memory/MEMORY.md` — private persistent memory
- `~/.claude/projects/.../memory/operations.log` — append-only traceability log

### Auto-Update Triggers

Update `memory.md` when: PR merged, ticket completed, new decision, CI status change, new known issue, session end.

Update `plan.md` when: PR merged (`[x]`), `/sync-plan` run, task blocked/unblocked, cycle rollover.

### plan.md Structure (Cycle-Driven)

Linear is source of truth; plan.md is a read-only view. Structure: Current Cycle → Next Cycle → Milestones → KPIs → Regles. Phase markers: `[owner: tN]` = claimed, `[owner: —]` = available. See `phase-ownership.md`.

### Update Format
- Keep entries concise — one line per item, link to PR/commit
- Date format: 2026-MM-DD. Never delete DONE items. Archive > 2 sprints.

### Checkpoint & Metrics
- Checkpoints: `~/.claude/projects/.../memory/checkpoints/` — see `crash-recovery.md`
- Metrics log: keep under 500 lines, rotate to `.log.1` (90-day retention)

## Quick Reference

| When | Do |
|------|----|
| Session start | Step 0 → Steps 1-2 |
| Context at 60% | Delegate to subagents |
| Context at 80% | `/compact` |
| PR merged (same MEGA) | Phase chaining if context < 70% |
| PR merged (standalone) | Update state files + EXTRACT |
| Session end | Step 5 |
