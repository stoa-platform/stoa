# AI-Factory Migration Pause — CI-1 Phase 2d Switch

**Status**: ACTIVE — DO NOT submit new claude-implement issues
**Started**: 2026-04-25 (PR open)
**Expected end**: T+2-24h depending on §H soak signal

## Why

CI-1 rewrite Phase 2d switch is in progress. The legacy
`.github/workflows/claude-issue-to-pr.yml` is being replaced by the
rewritten workflow (formerly `claude-issue-to-pr-v2.yml`, now restored
to the canonical name). During the switch + soak window, do not:

- Apply the `claude-implement` label to new issues (Council will not
  run on real events until `vars.DISABLE_L1_IMPLEMENT` is flipped to
  `false` after smokes pass).
- Comment `/go` or `/go-plan` on existing in-flight issues — wait for
  the soak window to close.

## What to expect

- Slack notifications may be delayed during smoke runs.
- Linear sync may be skipped on transient errors; check
  `council:ticket-*` / `council:plan-*` labels manually if a CAB
  ticket needs the verdict.
- Issues already in the legacy pipeline at switch time will not
  auto-resume — manual `workflow_dispatch` (with `stage` input) may be
  needed to re-fire a specific stage.

## When unblocked

This file is deleted (or marked `RESOLVED`) once §H validation in
`FIX-PLAN-CI1-PHASE-2D.md` passes (smokes 1-3 + negative + triggers
1-3 green).

## Rollback contact

If smokes fail or the new workflow misfires, see §I of
`FIX-PLAN-CI1-PHASE-2D.md` for the `git revert` procedure. The
revert restores the legacy workflow atomically.
