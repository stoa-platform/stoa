---
task_id: T-003
mega_id: CAB-2066
title: Security audit MCP server (SQL injection, tenant, PII, DoS)
owner: "@PotoMitan"
state: done
blocked_by: [T-002]
pr: null
created_at: 2026-04-16
completed_at: 2026-04-16
---
# Security audit — stoa-impact MCP

## Goal

Validate the server against the DoD security bar. Covers AC #5 of
`requirement.md`.

## Approach

Delegate to `security-reviewer` subagent (read-only). Check list:

1. No SQL injection — all queries parameterized.
2. Read-only SQLite connection enforced.
3. No PII / tenant scope (DB has none, but LIKE inputs validated).
4. No SQL error internals leaked in JSON-RPC error bodies.
5. JSON-RPC framing — parse errors, notifications, unknown methods.
6. DoS surface — line-length, single-request memory.
7. Connection closed on all exit paths.
8. `additionalProperties: false` on every tool schema.
9. `--db` path: symlink / traversal concerns.

## Done when

- [x] Verdict GO or GO-with-fixes.
- [x] Any MEDIUM or higher findings fixed in `stoa_impact_mcp.py`.
- [x] All tests still green after fixes.

## Outcome

GO with two MEDIUM findings (error-message leakage via `sqlite3.Error`
and generic `Exception`). Both fixed inline; server now logs details to
stderr and returns generic messages to the client. Tests remain 17/17.
