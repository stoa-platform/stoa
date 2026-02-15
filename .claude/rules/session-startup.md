---
description: Mandatory startup checklist for every Claude Code session. Read this FIRST before any work.
---

# Session Startup — Single Entry Point

> **This is the FIRST thing to do in every session.** No exceptions.
> Complete all steps before writing any code.

## Step 0 — Crash Recovery + Session Log

Before reading state files, check for crashed sessions and log this session:

1. Read last 20 lines of operations log:
   `~/.claude/projects/.../memory/operations.log`
2. Look for `SESSION-START` without matching `SESSION-END`
3. If crashed session detected:
   - Check `~/.claude/projects/.../memory/checkpoints/` for latest checkpoint
   - If checkpoint has `pr_number`, run `gh pr view <pr_number> --json state` — if MERGED, auto-close (not a real crash)
   - Otherwise report to user: "Previous session crashed mid-task [TASK] at step [STEP]. Resume or abandon?"
   - Follow `.claude/rules/crash-recovery.md` protocol
4. If no crash detected → **log this session immediately**:
   ```
   Append to operations.log: SESSION-START | task=<TASK> branch=<BRANCH>
   ```
   This MUST happen before any other work. It is the anchor for crash recovery.

## Step 1 — Read State Files

Read these 2 files **in this order** to understand current context:

1. **`memory.md`** (repo root) — active sprint, CI status, decisions, known issues
2. **`plan.md`** (repo root) — deliverables, execution phases, task status

Private memory (`~/.claude/projects/.../memory/MEMORY.md`) is auto-loaded by Claude Code.

## Step 2 — Pick Your Task

1. Check **Active Tickets** in `MEMORY.md` → pick highest priority unclaimed task
2. If no active tickets → check `plan.md` for NEXT/PENDING items
3. If user says "what next?" → summarize what's available, recommend highest priority
4. If user gives a specific task → use that (skip queue)
5. If task has **CAB-XXXX** ID → fetch from Linear MCP for full DoD + description:
   ```
   linear.get_issue("CAB-XXXX", includeRelations=true)
   ```
   This replaces manually copying ticket details from the browser.

## Step 3 — Context Budget

Monitor context window usage throughout the session:
- **Target**: stay under **60% context** (Ashley Ha / Boris Cherny pattern)
- **At 50%**: delegate remaining research to subagents, stop exploring inline
- **At 70%**: use `/compact` to compress conversation, keep working
- **At 80%**: wrap up current task, commit, update state files, consider fresh session
- **Never**: keep going past 90% — quality degrades, hallucinations increase

Use `/clear` aggressively between unrelated tasks in the same session.

## Step 4 — Work

Follow the appropriate pattern from `ai-factory.md` (Pattern 3/5/7 for features, Pattern 1/2 for reviews).

## Step 5 — End Session

1. Update `memory.md` with results (PR merged, decisions, issues found)
2. Update `plan.md` if task status changed
3. **State Lint (MANDATORY)** — before logging SESSION-END, verify:
   - No item with `**DONE**` or `— DONE` text sitting in `🔴 IN PROGRESS` or `📋 NEXT` sections of memory.md
   - Every `[~]` in plan.md still has at least one `[ ]` sub-item (otherwise promote to `[x]`)
   - Every `[x]` in plan.md has a matching entry in `✅ DONE` in memory.md
   - If any check fails → fix it NOW, before proceeding to step 4
   See `ai-workflow.md` → "Session-End State Lint" for full protocol.
4. **Linear MCP sync** (if task has CAB-XXXX ID):
   - PR merged → `linear.update_issue(status="Done")` + `linear.create_comment` with PR link
   - Blocked → `linear.update_issue(status="Blocked")` + comment with reason
   - Paused → leave as "In Progress" (no change needed)
5. **Metrics** — if a PR was merged or CI was fixed this session:
   - Append `PR-MERGED | task=<T> pr=<N>` to `~/.claude/projects/.../memory/metrics.log`
   - `/ci-fix` skill auto-appends `CI-FIX` entries (no manual step needed)
   - See `ai-workflow.md` → "Session Metrics" for full event list
6. **Learning loop**: if a CI failure, bug, or gotcha was encountered during this session:
   - Check if it's already in `~/.claude/projects/.../memory/gotchas.md`
   - If not → add it (one-liner: trigger, fix, prevention)
   - If it's a recurring pattern (seen 2+ times) → add to `.claude/rules/` as a permanent rule
7. **Log session end**:
   Append `SESSION-END | task=<TASK> status=<success|paused> pr=<NUMBER>` to operations.log
8. **Clean old checkpoints** (older than 7 days):
   Delete `.json` files in `checkpoints/` with mtime > 7d

## Quick Reference

| When | Do |
|------|----|
| Session start | Step 0 (crash check + log) → Steps 1-2 |
| User says "what next?" | Steps 1-2 → recommend |
| Context at 50% | Delegate research to subagents (Step 3) |
| Context at 70% | `/compact` then continue (Step 3) |
| Context at 80% | Wrap up, commit, fresh session (Step 3) |
| PR merged | Update memory.md + plan.md |
| CI failure / bug found | Add to gotchas.md (Step 5) |
| Before merge/deploy | Create checkpoint (crash-recovery.md) |
| After merge/deploy | Log STEP-DONE, delete checkpoint |
| Session end | Step 5 |
| Session crash | Next session detects in Step 0 |
