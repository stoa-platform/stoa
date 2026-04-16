---
mega_id: CAB-2066
title: SDD léger Level 1 + stoa-impact.db MCP read-only
owner: "@PotoMitan"
state: in_progress
impact_level: MEDIUM
council_score: 8.00       # inherited from CAB-2059 S1bis split
adrs: [ADR-063]
created_at: 2026-04-15
shipped_at: null
---
# SDD léger Level 1 + stoa-impact.db MCP read-only

## Problem

Two gaps slow MEGA execution today:

1. **No shared spec surface.** MEGAs live in Linear, but the operational
   artifacts (acceptance criteria, sub-tasks, dependency order) are scattered
   across Linear comments, `plan.md`, commit messages, and ad-hoc docs. There
   is no single source of truth a teammate can point at when resuming a MEGA
   mid-flight.
2. **Impact DB is shell-only.** `docs/stoa-impact.db` carries the dependency
   DAG, contracts, scenarios, and risks, but the only way to query it is
   `docs/scripts/*.sh`. Subagents without Bash (security-reviewer,
   docs-writer, content-reviewer) cannot use it, so they fall back to `grep`
   and miss structured relationships.

Split from CAB-2059 after Council S1bis (8.00/10). Gated on CAB-2065 Phase 1
Go — now unblocked (canaries -90% / -78%, 2026-04-16).

## Out of scope

- **SDD Level 2 (spec-anchored checks).** No CI lint against specs. No
  codegen from specs.
- **SDD Level 3 (spec-as-source).** Not on the roadmap.
- **Write access to the impact DB from the MCP server.** Read-only only.
  Ingestion stays through `populate-db.py` and `post-change-learn.sh`.
- **Multi-tenant isolation for the MCP server.** The DB has no tenant data;
  this is a dev-time tool only. CAB-2066 ships a single-user local MCP.

## Architecture touchpoints

- `.sdlc/` (new) — spec convention, templates, kill-criteria.
- `docs/scripts/stoa_impact_mcp.py` (new) — stdio JSON-RPC server, pure stdlib.
- `.mcp.json` — registers the server for Claude Code.
- `docs/stoa-impact.db` — consumed read-only, not modified.

Full impact via `stoa-impact` MCP:

```
# after merge, query from any session:
# tools/call list_components  → 15 rows
# tools/call get_contracts {component_id: "control-plane-api"}  → 10 rows
```

## Acceptance criteria (binary DoD)

- [x] `.sdlc/` in place with at least one formalized MEGA spec (this file).
- [x] SDD tool choice pinned: **cc-sdd v3.0.2** (templates only, no install).
- [x] Kill-criteria documented: `.sdlc/KILL-CRITERIA.md` with review date
      2026-04-30.
- [x] `stoa-impact` MCP server queryable from Claude Code via `.mcp.json`.
- [x] Security audit verdict GO (findings below CRITICAL/HIGH threshold).
- [x] `python3 -m pytest docs/scripts/test_stoa_impact_mcp.py -q` → 17/17 pass.
- [ ] ADR-063 merged in `stoa-platform/stoa-docs`.
- [ ] This PR merged to `main`, CI green, `/deploy-check` not applicable
      (docs-only + dev tool, no runtime change).

## Tasks

See `tasks/`.

## References

- Linear: https://linear.app/hlfh-workspace/issue/CAB-2066
- Parent MEGA: CAB-2059 (split by Council S1bis)
- Unblocked by: CAB-2065 (Agent Teams canary Go, 2026-04-16)
- Tool refs: https://github.com/github/spec-kit (v0.7.1),
  https://github.com/gotalab/cc-sdd (v3.0.2, picked)
