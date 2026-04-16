# Architecture context — STOA Platform

Pointer file. The source of truth is in `stoa-docs` and in the impact DB.

## Top-level shape

See `CLAUDE.md` (repo root) for the control-plane / data-plane split and the
component table. Do not duplicate it here.

## Authoritative sources

- **Decisions**: `docs/architecture/adr/` in
  [stoa-platform/stoa-docs](https://github.com/stoa-platform/stoa-docs). ADRs
  are numbered sequentially; next number is recorded in `MEMORY.md`.
- **Dependency DAG**: `docs/stoa-impact.db` (SQLite). Query via the
  `stoa-impact` MCP server (registered in `.mcp.json`) or
  `docs/scripts/impact-check.sh <component>`.
- **Runtime versions**: `CLAUDE.md` → "Runtime Versions" table.
- **RBAC roles**: `CLAUDE.md` → "RBAC Roles" table.

## How a spec should reference architecture

In `requirement.md`, link to:

1. The relevant ADR(s) — full URL on `docs.gostoa.dev` or the repo path.
2. The `stoa-impact` query that enumerates blast radius (component list +
   impacted scenarios).
3. Any CRD or Helm value schema being modified (path in
   `charts/stoa-platform/` or `stoa-infra`).

Do **not** copy ADR text, architecture diagrams, or component tables into the
spec. Link and move on — duplicated artifacts rot first.
