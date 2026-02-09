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

## Anti-Drift Rules
- **1 thing at a time** — never mix feature + refactor + fix
- **Never code without a validated plan**
- **Red flags** (broken tests, tech debt, security flaw) -> fix before continuing
- **If > 10 min structuring manually** -> STOP, use Claude Code
- **State files are mandatory** — skipping memory.md update is a workflow violation
