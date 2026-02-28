---
globs: ".claude/hooks/**,hegemon/tools/state/**"
---

# Crash Recovery Protocol

> **HEGEMON Foundation**: Universal crash recovery protocol lives in `hegemon/rules/crash-recovery.md`.
> This file contains STOA-specific extensions (checkpoint schema, detailed recovery table, log rotation).
> When hegemon is loaded as additional working dir, both rule sets apply.

## Overview

File-only traceability system for AI Factory sessions. No external server required.
Three levels: operation log (L1), step tracking (L2), pre-merge checkpoints (L3).

## Detection — How to Identify a Crash

A crashed session is identified by a `SESSION-START` entry in `operations.log` that has **no matching `SESSION-END`**.

### Detection Steps

1. Read the last 50 lines of `~/.claude/projects/.../memory/operations.log`
2. Find the most recent `SESSION-START` entry
3. Check if a `SESSION-END` with the same `task=` value exists after it
4. If no matching `SESSION-END` → **crashed session detected**

### False Positives

- If `operations.log` is empty or only has headers → no crash (first session)
- If last entry is `SESSION-END` → no crash (clean shutdown)
- If last `SESSION-START` has a `SESSION-END` after it → no crash

## Recovery Steps

### Step 1 — Assess

Gather crash context:
```
1. Read the crashed SESSION-START entry → extract task, branch, timestamp
2. Check checkpoints/ for files matching the task name
3. Run `git status` and `git log --oneline -5` to see code state
4. Check `memory.md` and `plan.md` for last known state
```

### Step 2 — Report to User

Present findings:
```
Previous session crashed:
- Task: <TASK>
- Branch: <BRANCH>
- Last step: <STEP> (from operations.log or checkpoint)
- Steps completed: [list]
- Steps remaining: [list]
- Time since crash: <DURATION>

Options:
1. Resume — continue from last completed step
2. Abandon — discard work, start fresh
3. Review — show me the changes first
```

### Step 2b — Check Active Claims

If the crashed session had an active claim (checkpoint contains `claimed_phase` or `CLAIM` log with no matching `RELEASE`):

1. Read the claim file at `claimed_phase.claim_file`
2. If **Resume**:
   - Verify claim is still valid (owner matches crashed instance ID)
   - If valid → keep claim, continue phase work
   - If stolen (another instance claimed it) → notify user, pick different work
3. If **Abandon**:
   - Release claim: clear `owner`, `claimed_at`, `pid` in claim file
   - Log: `RELEASE | task=<MEGA-ID> phase=<N> instance=<ID> reason=abandoned`
   - The phase becomes available for other instances

### Step 3 — Resume or Abandon

**Resume**:
1. Log `RECOVERY | task=<TASK> action=resume from_step=<STEP>`
2. Verify branch still exists: `git branch --list <BRANCH>`
3. Checkout the branch if not already on it
4. Continue from the next uncompleted step
5. The resumed session gets a new `SESSION-START` with `recovered_from=<TASK>`

**Abandon**:
1. Log `RECOVERY | task=<TASK> action=abandon reason=<USER_REASON>`
2. Clean up: delete checkpoint files for this task
3. Optionally: `git checkout main` and delete the stale branch
4. Start fresh with a new `SESSION-START`

### Step 4 — Prevent

After recovery, log `SESSION-END` for the crashed session:
```
SESSION-END | task=<TASK> status=crashed recovered_by=<NEW_SESSION>
```

## Checkpoint Format

Checkpoint files are JSON, stored in `~/.claude/projects/.../memory/checkpoints/`.

### Filename Convention

```
<ISO-timestamp>-<task-slug>.json
```

Example: `2026-02-12T14-30-task-traceability.json`

### Schema

```json
{
  "task": "traceability-system",
  "timestamp": "2026-02-12T14:30:00",
  "branch": "feat/ai-factory-traceability",
  "git_sha": "abc1234",
  "pr_number": 367,
  "steps_completed": ["branch", "code", "quality-gate", "pr", "ci"],
  "steps_remaining": ["merge", "verify-cd", "cleanup"],
  "context": {
    "component": "rules",
    "files_modified": [".claude/rules/ai-workflow.md", ".claude/rules/session-startup.md"],
    "notes": "CI green, ready to merge"
  },
  "progress": {
    "files_completed": ["src/models/consumer.py", "src/schemas/consumer.py"],
    "files_remaining": ["src/repositories/consumer.py", "tests/test_consumer.py"],
    "last_commit_message": "feat(api): add consumer model + schema (CAB-XXXX)",
    "decisions_made": ["Chose SQLAlchemy hybrid_property over computed column", "UUID7 for IDs"],
    "blockers": []
  },
  "claimed_phase": {
    "mega_id": "CAB-1290",
    "phase_id": 1,
    "claim_file": ".claude/claims/CAB-1290.json"
  }
}
```

**Field descriptions**:
- `claimed_phase` — optional. Present when working on a phase of a decomposed MEGA ticket. Used during crash recovery to verify and restore claim ownership.
- `progress` — optional but recommended. Enables a recovering session to resume intelligently without re-exploring the codebase:
  - `files_completed`: files already written/modified and committed
  - `files_remaining`: files still needed per the plan
  - `last_commit_message`: the most recent commit (helps orient the recovering session)
  - `decisions_made`: architectural or implementation choices made during the session (prevents re-deliberation)
  - `blockers`: any issues discovered that need resolution before continuing

### When to Create Checkpoints

| Trigger | Why |
|---------|-----|
| Before `gh pr merge` | Most dangerous operation — hard to undo |
| Before `kubectl apply` | Infra change, risk of CrashLoopBackOff |
| Before `terraform apply` | Infra destruction risk |
| Before any destructive git op | `reset`, `rebase`, branch delete |

### When to Delete Checkpoints

- After the risky operation succeeds → delete immediately
- Checkpoints older than 7 days → clean up in session end
- On task abandon → delete all checkpoints for that task

## Recovery Decision Table

| Crash Point | Last Log Entry | Action |
|-------------|---------------|--------|
| During coding | `SESSION-START` only | Resume: `git status` shows uncommitted work |
| After commit, before push | `STEP-DONE step=commit` | Resume: push the committed work |
| After push, before PR | `STEP-DONE step=push` | Resume: create the PR |
| After PR, before CI | `STEP-DONE step=pr-created` | Resume: wait for CI |
| After CI, before merge | `CHECKPOINT` exists | Resume: merge (checkpoint has full context) |
| During merge | `CHECKPOINT` exists | Check: `gh pr view` to see if merge completed |
| After merge, before CD verify | `STEP-DONE step=merged` | Resume: verify CD |
| During CD verify | `STEP-DONE step=merged` | Resume: check pod status |
| After CD verify | `STEP-DONE step=cd-verified` | Resume: update state files + cleanup |
| During phase work (claim active) | `CLAIM` log + no `SESSION-END` | Resume: verify claim still valid (Step 2b), continue phase |
| Phase complete, claim not released | `STEP-DONE step=merged` + `CLAIM` | Release claim, move to next unblocked phase |

## Log Format Reference

All entries in `operations.log` follow: `TIMESTAMP | EVENT | key=value ...`

| Event | Required Fields | Optional Fields | When |
|-------|----------------|-----------------|------|
| `SESSION-START` | `task`, `branch` | `recovered_from` | Session begins |
| `SESSION-END` | `task`, `status` | `pr`, `recovered_by` | Session ends (success/paused/crashed) |
| `STEP-START` | `step`, `task` | `detail` | Major step begins |
| `STEP-DONE` | `step`, `task` | `pr`, `sha`, `component` | Major step completes |
| `CHECKPOINT` | `task`, `file` | — | Pre-merge/deploy checkpoint created |
| `ERROR` | `task`, `error` | `step`, `detail` | Non-fatal error during execution |
| `RECOVERY` | `task`, `action` | `from_step`, `reason` | Crash recovery action taken |
| `CLAIM` | `task`, `phase`, `instance`, `tickets` | — | Phase claimed by instance |
| `RELEASE` | `task`, `phase`, `instance`, `reason` | — | Phase released (done/abandoned/stale) |

### Timestamp Format

ISO 8601 short: `YYYY-MM-DDTHH:MM` (minute precision, no seconds needed).

### Example Log

```
2026-02-12T14:00 | SESSION-START | task=traceability-system branch=feat/ai-factory-traceability
2026-02-12T14:15 | STEP-DONE | step=code task=traceability-system
2026-02-12T14:20 | STEP-DONE | step=pr-created task=traceability-system pr=367
2026-02-12T14:25 | CHECKPOINT | task=traceability-system file=2026-02-12T14-25-traceability-system.json
2026-02-12T14:26 | STEP-DONE | step=merged task=traceability-system pr=367
2026-02-12T14:28 | STEP-DONE | step=cd-verified task=traceability-system component=rules
2026-02-12T14:30 | SESSION-END | task=traceability-system status=success pr=367
```

## Log Rotation

- Keep `operations.log` under 500 lines
- When over 500 lines: move oldest entries to `operations.log.1`
- Keep `operations.log.1` for 90 days, then delete
- Checkpoints older than 7 days: delete during session end cleanup
