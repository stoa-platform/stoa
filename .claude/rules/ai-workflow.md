---
description: AI-native development workflow and session management rules
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

## Anti-Drift Rules
- **1 thing at a time** — never mix feature + refactor + fix
- **Never code without a validated plan**
- **Red flags** (broken tests, tech debt, security flaw) -> fix before continuing
- **If > 10 min structuring manually** -> STOP, use Claude Code
