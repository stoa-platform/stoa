---
name: SDD Level 1 kill-criteria
tool_pinned: cc-sdd v3.0.2 (templates only, no install)
adopted_at: 2026-04-16
review_at: 2026-04-30
---
# Kill-criteria — SDD Level 1

This convention is on a 2-week trial starting **2026-04-16**.

## Abandon if

Any of the following holds at review on **2026-04-30**:

1. **Zero MEGA formalized** — `.sdlc/specs/` contains no real MEGA entry (dogfood
   CAB-2066 does not count; a second real MEGA must have been formalized).
2. **Specs become stale** — any formalized spec has drifted from the Linear
   ticket or from the shipped code without a reconciling commit.
3. **Duplication complaint** — contributor feedback shows specs duplicate
   information already in Linear, ADRs, or `docs/`. Two distinct complaints
   across two sessions trigger this.
4. **Workflow friction** — MEGA cycle-time (measured by `/roadmap` velocity)
   rises by >10% over the trial window with no other explanation.

## Abandonment procedure

If any of the above triggers:

1. Delete `.sdlc/` in a single commit referencing this file.
2. Update `docs/adr/adr-063-*.md` in `stoa-docs` with a **Superseded / Rejected**
   note and a short post-mortem (what we tried, why it failed, what we kept).
3. Remove mention from `CLAUDE.md` and `MEMORY.md`.

## Keep if

If none of the above holds and at least two real MEGAs have a spec, promote the
convention to "default for MEGAs" (update `CLAUDE.md` rules section).
Level 2 adoption (spec-anchored checks) stays out of scope.
