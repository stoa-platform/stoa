# Conventions — STOA

Pointer file. The source of truth is `CLAUDE.md` at the repo root.

## Non-duplication rule

This file lists **only** conventions that are SDD-specific (how to write a
spec, how to split tasks). Coding style, commit format, PR size, test-first
policy, and branch rules live in `CLAUDE.md` and MUST NOT be duplicated here.

## Spec writing

- **One requirement per MEGA.** If you need two requirements, you have two
  MEGAs.
- **Binary DoD.** Every acceptance criterion is checkable with one command or
  one URL. "Improve X" is not acceptable; "X latency p95 < 200ms on
  `/health`" is.
- **Link, don't copy.** ADRs, Linear tickets, impact DB queries — link them.
  Embedded snippets are acceptable only if they are < 5 lines and the source
  is unstable (external RFC, vendor doc).

## Task splitting

- **One PR per task.** Each `tasks/T-*.md` maps to one PR (< 300 LOC per
  `CLAUDE.md` rules).
- **Task state machine** (see `templates/task-template.md` frontmatter):
  `pending → in_progress → done` or `pending → blocked → pending`.
- **Blocking dependencies** go in frontmatter (`blocked_by:`), not prose.

## Commit / PR / Linear

Unchanged from `CLAUDE.md`:
- Conventional commits, squash merge, delete branch.
- Ticket ID on first commit.
- PR < 300 LOC, evidence archive after Playwright.
