---
name: verify-mega
description: Verify MEGA ticket close gates — ensures all sub-tickets Done, PRs merged, live verification passed.
argument-hint: "CAB-XXXX | --all-done-7d"
---

# Verify MEGA — $ARGUMENTS

## Overview

Run all 5 MEGA Close Gates on a ticket (or audit all recently-closed MEGAs).
Prevents false Dones on multi-phase tickets.

## Mode Detection

- If `$ARGUMENTS` is `--all-done-7d`: **Audit mode** — scan all MEGAs marked Done in last 7 days
- If `$ARGUMENTS` is `CAB-XXXX`: **Single mode** — verify one MEGA ticket

## Step 1: Fetch MEGA Data

### Single Mode

```
linear.get_issue("CAB-XXXX", includeRelations=true)
```

Extract:
- `title` — verify contains `[MEGA]` or has children
- `children.nodes[]` — list of sub-tickets with `id`, `identifier`, `state.name`, `estimate`
- `estimate` — total points

If no children → report: "CAB-XXXX is not a MEGA (no children). Use standard close flow."

### Audit Mode

```
linear.list_issues(
  teamId: "624a9948-a160-4e47-aba5-7f9404d23506",
  filter: { state: { name: { eq: "Done" } }, updatedAt: { gte: "<7 days ago>" } }
)
```

Filter results to only MEGAs (title contains `[MEGA]` or has children).
Run gates on each.

## Step 2: Gate 0 — Decomposition Invariant

- Check: `children.nodes.length > 0`
- **Pass**: MEGA has sub-tickets
- **Fail**: "MEGA has no sub-tickets. Run `/decompose CAB-XXXX` first."

## Step 3: Gate 1 — Per-Phase PR Evidence

For each child ticket in Done state:
```
linear.list_comments(issueId: "<child_id>")
```

Check that at least one comment contains `PR #` or `PR [#`.

- **Pass**: All Done children have PR evidence
- **Fail**: List children missing PR references: "CAB-XXXX: no PR evidence found"

## Step 4: Gate 2 — All Sub-Tickets Done

Check each child's `state.name`:
- **Pass**: ALL children have `state.name == "Done"` or `state.name == "Canceled"`
- **Fail**: List non-Done children with their current state:
  ```
  CAB-1351: In Progress
  CAB-1352: Todo
  ```

## Step 5: Gate 3 — Live Verification

Based on the MEGA's component scope:
- **API changes**: `curl -s https://api.gostoa.dev/health` → expect 200
- **UI/Portal**: `curl -s https://console.gostoa.dev` or `curl -s https://portal.gostoa.dev` → expect 200
- **Gateway**: `curl -s https://mcp.gostoa.dev/health` → expect 200
- **Docs**: `curl -s https://docs.gostoa.dev` → expect 200
- **Cross-component**: verify all affected endpoints

If automated verification is not possible, prompt the user:
"Gate 3 requires manual verification. Please confirm the target is working: [endpoint/site]"

## Step 6: Gate 4 — No Stale Children

Check no child is stuck in non-terminal state:
- **Pass**: Zero children in "In Progress", "Todo", or "Blocked"
- **Fail**: List stale children (these should be either Done or explicitly descoped)

## Step 7: Render Verdict

### Format

```
## MEGA Verification: CAB-XXXX — [Title]

| # | Gate | Status | Detail |
|---|------|--------|--------|
| 0 | Decomposition | ✅/❌ | N sub-tickets |
| 1 | PR Evidence | ✅/❌ | N/M children have PRs |
| 2 | All Done | ✅/❌ | N/M children Done |
| 3 | Live Verification | ✅/❌ | endpoint status |
| 4 | No Stale Children | ✅/❌ | N stale |

**Verdict**: Go / Fix
```

### If Go (all gates pass)

1. Mark parent MEGA as Done on Linear:
   ```
   linear.update_issue(id, state="Done")
   ```
2. Post comprehensive completion comment:
   ```
   linear.create_comment(issueId, body="MEGA completed — all 5 gates passed.\n\nSub-tickets:\n- CAB-1350: Done (PR #578)\n- CAB-1351: Done (PR #582)\n- CAB-1352: Done (PR #590)\n\nLive verification: ✅ [endpoint] responding")
   ```
3. Log: `MEGA-GATE-PASS | task=CAB-XXXX gates=5/5`

### If Fix (any gate fails)

1. Keep parent MEGA In Progress (do NOT mark Done)
2. Post audit comment listing gaps:
   ```
   linear.create_comment(issueId, body="MEGA verification failed — X/5 gates passed.\n\nFailing gates:\n- Gate 1: CAB-1352 missing PR evidence\n- Gate 2: CAB-1352 still In Progress\n\nAction required: complete remaining work before closing.")
   ```
3. Log: `MEGA-GATE-FAIL | task=CAB-XXXX missing=<gate_numbers>`
4. List remediation steps for each failing gate

### Audit Mode Output

```
## Weekly MEGA Audit — [date]

| MEGA | Points | Gates | Verdict | Action |
|------|--------|-------|---------|--------|
| CAB-1470 | 21 pts | 3/5 | Fix | Gate 1,2 failing |
| CAB-1490 | 13 pts | 5/5 | Go | Already correct |

Reopened: CAB-1470 (moved back to In Progress)
```
