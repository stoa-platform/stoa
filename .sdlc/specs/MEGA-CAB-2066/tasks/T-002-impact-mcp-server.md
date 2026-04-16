---
task_id: T-002
mega_id: CAB-2066
title: Build stoa-impact MCP server (read-only stdio, Python stdlib)
owner: "@PotoMitan"
state: done
blocked_by: []
pr: null                  # bundled in CAB-2066 MEGA PR
created_at: 2026-04-16
completed_at: 2026-04-16
---
# Build stoa-impact MCP server

## Goal

Expose `docs/stoa-impact.db` as a local MCP server with read-only tools.
Covers AC #4 and #6 of `requirement.md`.

## Approach

- Pure-Python stdlib (no `mcp` SDK dep).
- JSON-RPC 2.0 over stdio — one message per line.
- SQLite opened via URI `?mode=ro`.
- 8 tools: `list_components`, `get_component`, `get_contracts`,
  `get_impacted_scenarios`, `get_risks`, `get_dependency_matrix`,
  `get_untyped_contracts`, `get_component_risk_score`.
- All inputs parameterized; `additionalProperties: false` on every schema.
- Tests: unit via pytest + self-runner for CI-less smoke.
- Register in `.mcp.json` next to `linear`, `playwright`, `context7`.

## Done when

- [x] `docs/scripts/stoa_impact_mcp.py` created.
- [x] `docs/scripts/test_stoa_impact_mcp.py` — 17/17 green.
- [x] `.mcp.json` entry added.
- [x] Live stdio smoke-test: initialize → tools/list → tools/call returns
      valid JSON.
- [x] Security review verdict GO (see T-003).
