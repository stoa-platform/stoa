---
mega_id: CAB-XXXX
title: <one-line title matching Linear>
owner: <@github-handle>
state: draft            # draft | council-validated | in_progress | shipped | abandoned
impact_level: LOW       # LOW | MEDIUM | HIGH | CRITICAL (from build-context.sh)
council_score: null     # set after Council S1/S2 (>= 8.0/10)
adrs: []                # e.g., [ADR-057]
created_at: YYYY-MM-DD
shipped_at: null
---
# <Title>

## Problem

One or two paragraphs. Who is hurting, why now, what does "fixed" look like.
Link the original Linear ticket and any incident or user report.

## Out of scope

Bullet list. Things that might be confused with this scope and are explicitly
deferred. Link follow-up tickets if they exist.

## Architecture touchpoints

List the components involved (use IDs from `stoa-impact.db` via the
`stoa-impact` MCP server):

- `<component-id>` — why it changes
- `<component-id>` — why it changes

Link the impact query output if it's large:

```
# example
python3 -c "…"  # or: docs/scripts/impact-check.sh <component>
```

## Acceptance criteria (binary DoD)

Every criterion must be a single checkable fact. No "improve", "refactor",
"clean up" without a metric.

- [ ] `<command or URL>` → `<expected output>`
- [ ] `<metric>` at `<threshold>` on `<dashboard>`
- [ ] PR `<link>` merged and post-merge verification `/deploy-check` green

## Tasks

See `tasks/`. Each task is one PR. Order is the dependency order.

## References

- Linear: <url>
- ADR: <url>
- Council decision: <url or PR>
- Related MEGAs: <IDs>
