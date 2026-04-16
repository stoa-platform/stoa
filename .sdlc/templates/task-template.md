---
task_id: T-NNN
mega_id: CAB-XXXX
title: <imperative, concise>
owner: <@github-handle>
state: pending            # pending | in_progress | blocked | done
blocked_by: []            # task IDs or ticket refs
pr: null                  # set to PR URL once opened
created_at: YYYY-MM-DD
completed_at: null
---
# <Imperative Title>

## Goal

One or two sentences. What this task delivers. Reference the requirement
acceptance criterion it unlocks (e.g., "Covers AC #3 of requirement.md").

## Approach

Bullet-level plan. Include:

- Files to touch (absolute or repo-relative paths)
- Commands to run locally before opening the PR
- Tests to add (unit/integration/e2e — pick one, do not skip)

## Done when

- [ ] Code merged to `main` via squash (PR link above)
- [ ] CI green on the PR (no pre-existing flakes attributed)
- [ ] Any evidence archive committed to `docs/audits/<date>-<topic>/` if
      Playwright or manual verification was used

## Notes

Optional. Edge cases discovered during execution, blockers encountered,
reasons to split the task further.
