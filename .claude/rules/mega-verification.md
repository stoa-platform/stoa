---
description: MEGA ticket close gate enforcement — prevents false Dones on multi-phase tickets
globs: ".claude/rules/workflow-essentials.md,.claude/rules/instance-dispatch.md,.claude/rules/session-startup.md,.github/workflows/linear-close-on-merge.yml,.github/workflows/claude-linear-dispatch.yml"
---

# MEGA Verification — Close Gate Enforcement

## Overview

MEGA tickets (>= 13 pts, multi-phase) MUST pass all 5 gates before being marked Done.
This rule is enforced at every pipeline exit point: manual sessions, `linear-close-on-merge.yml`, and `claude-linear-dispatch.yml`.

## 5 Gates

| # | Gate | Verification | Fail Action |
|---|------|-------------|-------------|
| 0 | **Decomposition Invariant** | `linear.get_issue(id)` → `children.nodes.length > 0` | BLOCK dispatch, run `/decompose` first |
| 1 | **Per-Phase PR Evidence** | Every Done sub-ticket has a Linear comment containing `PR #` | List missing PRs, keep parent In Progress |
| 2 | **All Sub-Tickets Done** | ALL `children.nodes` have `state.name == "Done"` | List incomplete children, keep parent In Progress |
| 3 | **Live Verification** | Target endpoint/site confirmed working (curl, build, or screenshot) | Prompt for manual verification |
| 4 | **Sub-tickets closed on Linear** | No child in "In Progress", "Todo", or "Blocked" state | List stale children |

## Detection: Is This a MEGA?

A ticket is a MEGA if ANY of these are true:
- Title contains `[MEGA]`
- Has child issues on Linear (`children.nodes.length > 0`)
- Estimate >= 13 points

## Enforcement Points

### 1. Manual Sessions (session-startup.md Step 5)

When closing a ticket in Step 5 — Linear MCP sync:
- **Standalone ticket** (no parent, no children): mark Done as before
- **Sub-ticket of MEGA** (has parent): mark sub-ticket Done, then check siblings. If ALL siblings Done → run `/verify-mega` on parent
- **MEGA parent** (has children): NEVER mark Done directly — always use `/verify-mega`

### 2. linear-close-on-merge.yml (CI)

After extracting `TICKET_ID`, check if ticket is a MEGA (has children).
- **MEGA**: skip Done mutation, post comment: "Sub-ticket work merged in PR #N. Parent MEGA stays In Progress."
- **Standalone**: proceed with existing Done mutation

### 3. claude-linear-dispatch.yml (L3 Pipeline)

In the close-loop step, before the Done mutation:
- Check if `TICKET_ID` is a MEGA (query Linear for children)
- If MEGA → skip Done mutation, post progress comment
- If standalone → existing close logic

## Weekly Audit

ORCHESTRE runs `/verify-mega --all-done-7d` every Monday:
1. Query Linear for all MEGAs marked Done in the last 7 days
2. Run all 5 gates on each
3. Report: list of MEGAs with gate failures
4. Reopen any MEGA that fails gates (move back to In Progress)

## Anti-Patterns

| Pattern | Why It's Wrong | Correct |
|---------|---------------|---------|
| Marking MEGA Done when 1 PR merges | Only one phase completed | Keep In Progress until all children Done |
| Closing MEGA without `/verify-mega` | Skips gate checks | Always use `/verify-mega` |
| Auto-closing MEGA in CI workflow | CI sees merged PR, closes parent | CI must detect MEGA and skip |
| Marking MEGA Done with blocked children | Incomplete scope | Unblock or descope children first |

## Integration

| File | Reference |
|------|-----------|
| `workflow-essentials.md` | MEGA Close Gate table (gates 1-4) + Invariant #6 |
| `session-startup.md` | Step 5 — differentiate standalone vs sub-ticket vs MEGA |
| `instance-dispatch.md` | ORCHESTRE Rules — `/verify-mega` before closing MEGAs |
| `linear-close-on-merge.yml` | MEGA bypass in Done mutation |
| `claude-linear-dispatch.yml` | MEGA bypass in close-loop |
| `/verify-mega` skill | Automated gate runner |
