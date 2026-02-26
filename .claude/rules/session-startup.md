---
description: Mandatory startup checklist for every Claude Code session. Read this FIRST before any work.
globs: ".claude/**"
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
4. **Instance identity**: The SessionStart hook (`session-init.sh`) auto-generates `STOA_INSTANCE_ID` via env file.
   If `$STOA_INSTANCE_ID` is set, use it. Otherwise generate manually:
   ```
   Instance ID: t<N>-<R> where N = epoch seconds mod 100000, R = 4 hex chars (random)
   ```
5. If no crash detected → **log this session immediately**:
   ```
   Append to operations.log: SESSION-START | task=<TASK> branch=<BRANCH> instance=<ID>
   ```
   This MUST happen before any other work. It is the anchor for crash recovery.

## Step 1 — Read State (Optimized)

The SessionStart hook generates `.claude/session-brief.json` from HEGEMON state store.

1. **IF** `.claude/session-brief.json` exists AND is < 5 min old:
   - Read the brief (~500 tokens) — contains cycle tickets, active claims, recent milestones, active sessions
   - Skip full `memory.md` + `plan.md` read (saves 5-13K tokens)
2. **ELSE** (fallback — state.db absent or brief stale):
   - Read `memory.md` (repo root) — active sprint, CI status, decisions, known issues
   - Read `plan.md` (repo root) — cycle-driven sprint view (synced from Linear via `/sync-plan`)
3. **IF** task has CAB-XXXX ID AND brief has ticket summary:
   - Use summary from brief (~50 tokens vs 800 tokens MCP call)
   - Only call `linear.get_issue()` MCP for full DoD when entering verification phase
4. **ELSE**:
   - Call `linear.get_issue()` as before (backward compatible)

Private memory (`~/.claude/projects/.../memory/MEMORY.md`) is auto-loaded by Claude Code.

## Step 2 — Pick Your Phase

Phase-aware task selection that prevents multi-instance race conditions.
See `phase-ownership.md` for full protocol, claim schemas, and conflict resolution.

1. If user gives a specific task → use that (skip to step 5)
2. Read `plan.md` → identify current cycle items (In Progress + Todo)
3. **For each MEGA with phases**:
   a. Read `.claude/claims/<MEGA-ID>.json`
   b. Find first phase where: `owner == null` AND all deps satisfied (`completed_at != null` for each dep phase)
   c. If found → claim it:
      - Write own instance ID + PID + timestamp to claim file
      - Mark all phase tickets "In Progress" on Linear via MCP batch
      - Log: `CLAIM | task=<MEGA-ID> phase=<N> instance=<ID> tickets=<list>`
   d. If all phases claimed or blocked → skip this MEGA
4. **For standalone tickets** (no phases):
   a. Check `.claude/claims/<CAB-XXXX>.json` exists
   b. If exists AND PID alive (`kill -0 $PID`) → skip (claimed by another instance)
   c. If exists AND PID dead → auto-release stale claim, then claim it
   d. If not exists → create claim file → Linear "In Progress" → log `CLAIM | task=<CAB-XXXX> instance=<ID>`
5. If task has **CAB-XXXX** ID → fetch from Linear MCP for full DoD + description:
   ```
   linear.get_issue("CAB-XXXX", includeRelations=true)
   ```
6. If no unclaimed work available:
   → "All phases/tickets claimed or blocked. Available MEGAs: [list unclaimed MEGAs]"
   → If user says "what next?" → summarize claim status across all MEGAs

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

## Step 4b — Phase Chaining (after PR merge, same MEGA)

After merging a PR for a phase, check if the same MEGA has another unclaimed unblocked phase:

1. **Context budget gate**: Only chain if context usage < **60%**. If over 60%, end session and let a fresh instance pick up the next phase (quality degrades with deep context).
2. Read `.claude/claims/<MEGA-ID>.json` → find the phase you just completed
3. Set `completed_at` on your phase, clear `owner` (release)
4. Log: `RELEASE | task=<MEGA-ID> phase=<N> instance=<ID> reason=done`
5. Scan remaining phases: find first where `owner == null` AND all `deps` phases have `completed_at != null`
6. If found → claim it (follow Reserve protocol from `phase-ownership.md`), continue working in same session
7. If none available → proceed to Step 5 (End Session)

**Why chain?** Avoids the overhead of a full session restart (re-reading state files, crash detection, context loading). A session that just merged a PR already has warm context about the MEGA and its architecture.

**Why gate on 60%?** Phase chaining reuses the existing context window. If context is already heavy, the next phase will suffer from degraded reasoning quality. Better to start fresh.

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
6. **HEGEMON EXTRACT (MANDATORY)** — if this session produced deliverables (PR merged, design decision, or gotcha):
   - Ask: "What did I learn that applies beyond this project?"
   - If a reusable pattern was identified → run `/extract <pattern name>` to capture it in HEGEMON
   - If nothing new → log "No new pattern" (acceptable, but be honest)
   - If a human override occurred → log in `hegemon/metrics/override-log.md`
   - See `hegemon/rules/session-lifecycle.md` for the full EXTRACT protocol
7. **Learning loop**: if a CI failure, bug, or gotcha was encountered during this session:
   - Check if it's already in `~/.claude/projects/.../memory/gotchas.md`
   - If not → add it (one-liner: trigger, fix, prevention)
   - If it's a recurring pattern (seen 2+ times) → add to `.claude/rules/` as a permanent rule
8. **Log session end**:
   Append `SESSION-END | task=<TASK> status=<success|paused> pr=<NUMBER>` to operations.log
9. **Clean old checkpoints** (older than 7 days):
   Delete `.json` files in `checkpoints/` with mtime > 7d

## Quick Reference

| When | Do |
|------|----|
| Session start | Step 0 (crash check + log) → Steps 1-2 |
| User says "what next?" | Steps 1-2 → recommend |
| Context at 50% | Delegate research to subagents (Step 3) |
| Context at 70% | `/compact` then continue (Step 3) |
| Context at 80% | Wrap up, commit, fresh session (Step 3) |
| PR merged (same MEGA) | Step 4b — chain to next phase if context < 60% |
| PR merged (standalone) | Update memory.md + plan.md + EXTRACT |
| CI failure / bug found | Add to gotchas.md + consider EXTRACT (Step 5) |
| Before merge/deploy | Create checkpoint (crash-recovery.md) |
| After merge/deploy | Log STEP-DONE, delete checkpoint |
| Session end | Step 5 |
| Session crash | Next session detects in Step 0 |
