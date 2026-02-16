---
description: Multi-instance coordination protocol for safe parallel execution on MEGA tickets. Claim files prevent race conditions.
globs:
  - ".claude/**"
  - "plan.md"
  - "memory.md"
---

# Phase Ownership — Multi-Instance Coordination Protocol

## Overview

Multiple Claude Code terminals can race on the same ticket because session-startup has no claiming mechanism. This protocol adds file-based claims so each instance owns an **entire phase** end-to-end.

**Problem solved**: Two terminals pick the same "highest priority unclaimed" ticket, both mark it "In Progress" on Linear, both create branches, both produce conflicting PRs.

**Inspired by**: Devin batch sessions, Cursor root planners, MetaGPT phase agents, Spotify squad ownership, SAFe parallel tracks, Boris Cherny 5-agent workflow.

### 3 Execution Modes

| Mode | When | Instances | Claim Mechanism |
|------|------|-----------|-----------------|
| **Sequential** | Default, single terminal | 1 | Claim one phase, finish it, claim next |
| **Multi-instance** | User opens N terminals | 2-3 | Each terminal claims a different phase |
| **Multi-subagent** | Agent Teams (Pattern 4) | 1 lead + N | Lead claims via TaskUpdate + writes claim file for cross-session visibility |

## Claim File Format

Claims live in `.claude/claims/` (gitignored, machine-local). Two schemas:

### MEGA Claims (decomposed tickets with phases)

Filename: `.claude/claims/<MEGA-ID>.json` (e.g., `CAB-1290.json`)

```json
{
  "mega": "CAB-1290",
  "title": "Gateway Live-Code MEGA",
  "created": "2026-02-16T14:00",
  "phases": [
    {
      "id": 1,
      "name": "API + Gateway (parallel)",
      "tickets": ["CAB-1350", "CAB-1351"],
      "owner": "t4821",
      "claimed_at": "2026-02-16T14:05",
      "branch": "feat/CAB-1350-traceparent-injection",
      "mode": "parallel",
      "deps": [],
      "completed_at": null
    },
    {
      "id": 2,
      "name": "E2E Integration Tests",
      "tickets": ["CAB-1352"],
      "owner": null,
      "claimed_at": null,
      "branch": null,
      "mode": "sequential",
      "deps": [1],
      "completed_at": null
    }
  ]
}
```

### Standalone Claims (single ticket, no phases)

Filename: `.claude/claims/<CAB-XXXX>.json` (e.g., `CAB-1321.json`)

```json
{
  "ticket": "CAB-1321",
  "title": "Portal ToS link fix",
  "owner": "t4821",
  "pid": 12345,
  "claimed_at": "2026-02-16T14:10",
  "branch": "fix/CAB-1321-tos-link",
  "completed_at": null
}
```

### Instance Identity

Each terminal session generates a short instance ID at startup:
- **Format**: `t<N>` where N = epoch seconds mod 10000
- **Generated once** per session, logged in `SESSION-START`
- **Purpose**: distinguish claim owners across terminals

## Claim Lifecycle

### 1. Reserve

```
1. Read .claude/claims/<ID>.json (or check if file exists for standalone)
2. Find first unclaimed phase where: owner == null AND all deps satisfied
3. Write owner + PID + timestamp to claim file
4. Mark all phase tickets "In Progress" on Linear via MCP batch
5. Log: CLAIM | task=<MEGA-ID> phase=<N> instance=<ID> tickets=<list>
```

**Atomicity**: Write claim → sleep 100ms → re-read → verify own PID → proceed or backoff.

### 2. Execute

Work the phase end-to-end using the standard pattern (Pattern 3/5/7):
- Create branch for the phase
- Code, test, commit, push, PR, CI green, merge
- Each phase = 1 PR, <300 LOC (Stripe micro-PR standard)

### 3. Release

```
1. Set completed_at in claim file
2. Clear owner (set to null) — phase is now available for verification
3. Log: RELEASE | task=<MEGA-ID> phase=<N> instance=<ID> reason=done
4. Check for next unclaimed unblocked phase in the same MEGA
5. If found → claim it (go to Reserve step)
6. If none available → session ends or picks another MEGA
```

## Stale Claim Detection

A claim is **stale** if ALL of these are true:
1. `claimed_at` is more than **2 hours** ago
2. No `SESSION-START` with matching instance ID found in operations.log within last 2 hours
3. PID is not alive: `kill -0 $PID` fails (same machine only)

### Auto-Release Protocol

Stale claims are detected during:
- `/sync-plan` execution (Step 4d)
- Session startup (Step 2, when scanning claim files)

When a stale claim is found:
1. Clear `owner`, `claimed_at`, `pid` fields (set to null)
2. Log: `RELEASE | task=<ID> phase=<N> instance=<old_owner> reason=stale`
3. Report to user: "CAB-XXXX Phase N: STALE CLAIM (claimed by <instance> at <time>, auto-released)"
4. The phase is now available for claiming

### Cross-Machine Limitation

PID checks only work on the same machine. For truly distributed scenarios (multiple machines), rely on the 2-hour timeout + operations.log activity check only.

## Conflict Resolution

**First-claim-wins** with filesystem verification:

```
1. Check claim file → phase unclaimed
2. Write own PID + timestamp as owner
3. Sleep 100ms (filesystem sync window)
4. Re-read claim file
5. If own PID matches → proceed (claim successful)
6. If different PID → backoff:
   a. Log: CONFLICT | task=<ID> phase=<N> winner=<other_PID>
   b. Notify user: "Phase N already claimed by <instance>. Available: Phase M."
   c. Attempt to claim next available phase
```

**Edge case**: If two instances write simultaneously and both see their own PID (filesystem race), the operations.log will show two CLAIM entries. The session-end lint detects this and flags it.

## Phase Structure in plan.md

MEGA entries with phases use this format:

```markdown
- [~] CAB-1290: [MEGA] Gateway Live-Code (13 pts) — 2 phases
  - **Phase 1** (parallel) [owner: t4821]
    - [~] CAB-1350 [gateway] Traceparent injection — PR #578
    - [ ] CAB-1351 [gateway] Resource listing
  - **Phase 2** (after Phase 1) [owner: —]
    - [ ] CAB-1352 [e2e] Integration tests
```

**Markers**:
- `[owner: t4821]` — phase claimed by instance t4821
- `[owner: —]` — phase unclaimed (available)
- Phase header includes dependency info: `(parallel)`, `(after Phase 1)`, `(after Phase 1+2)`

**Rules**:
- Phase ownership markers are NOT derived from Linear — they are local metadata
- `/sync-plan` preserves phase markers during regeneration (never deletes `[owner: X]`)
- When claim file shows phase complete → update plan.md marker to `[x]`

## Claiming Rules

1. **End-to-end ownership**: Instance that claims a phase **finishes it entirely** (no mid-phase handoff)
2. **Crash recovery**: If instance crashes, next session detects stale claim and re-offers the phase (see `crash-recovery.md`)
3. **Non-decomposed tickets**: Claim file is the simple standalone schema (ticket + owner + PID)
4. **Phase chaining**: An instance that finishes a phase checks for the next unclaimed unblocked phase in the same MEGA before exiting
5. **Max 3 instances**: Cost control — more than 3 parallel instances produces diminishing returns
6. **Standalone tickets**: Only one instance can claim a standalone ticket at a time
7. **Release before exit**: Always release claims in session-end (Step 5), even on early exit

## Integration Points

| File | What References Phase Ownership |
|------|-------------------------------|
| `session-startup.md` | Step 0 (instance ID), Step 2 (Pick Your Phase algorithm) |
| `ai-factory.md` | Pattern 9 (Phase Ownership workflow) |
| `ai-workflow.md` | CLAIMED state in Item State Machine, CLAIM/RELEASE events |
| `crash-recovery.md` | `claimed_phase` in checkpoint schema, claim recovery steps |
| `decompose/SKILL.md` | Step 9b (initialize claim file after sub-issue creation) |
| `sync-plan/SKILL.md` | Step 4d (stale claim detection), preservation rules |

## Examples

### Example 1: Two Terminals on a MEGA

```
Terminal 1 starts → reads claims/CAB-1290.json → Phase 1 unclaimed → claims Phase 1
Terminal 2 starts → reads claims/CAB-1290.json → Phase 1 claimed → Phase 2 blocked (deps:[1])
  → No unclaimed unblocked phases → "All phases claimed or blocked"

Terminal 1 finishes Phase 1 → releases → Phase 2 now unblocked
Terminal 2 (next session or retry) → claims Phase 2 → works it
```

### Example 2: Standalone Ticket

```
Terminal 1 starts → no MEGA phases → picks CAB-1321 → creates claims/CAB-1321.json
Terminal 2 starts → sees claims/CAB-1321.json exists, PID alive → skips → picks CAB-1322
```

### Example 3: Crash Recovery

```
Terminal 1 claims Phase 1 of CAB-1290 → crashes mid-work
Terminal 1 (new session) → Step 0 detects crash → checkpoint has claimed_phase
  → Resume: verify claim still valid (PID matches) → continue Phase 1
```
