# AGENTS.md — STOA Platform

This repo uses `CLAUDE.md` as the canonical AI agent contract. `AGENTS.md` exists
as the cross-agent entry point for any AI coding assistant (Claude Code, Codex,
Cursor, Aider, etc.).

## Contract

AI agents working in this repository must:

1. Read `CLAUDE.md` at the repo root for project rules, architecture, runtime
   versions, workflow, and GO/NOGO gates. It is the single source of truth —
   this file does not duplicate its content to avoid drift.
2. Read the component-scoped `CLAUDE.md` inside the directory you are editing
   (e.g. `stoa-gateway/CLAUDE.md`, `control-plane-api/CLAUDE.md`,
   `control-plane-ui/CLAUDE.md`) when touching that service.
3. Load `.claude/docs/<topic>.md` on demand when a rule in `CLAUDE.md`
   references it. These docs are protocols, examples, and gotcha tables —
   never auto-loaded, only pulled in when the topic is in scope.
4. Follow the same rules regardless of the tool brand. The `.claude/` storage
   path is a naming convention, not a tool lock-in; any AI agent is expected
   to honor the rules defined there.

## Architecture (quick reference)

```
CONTROL PLANE (Cloud)                    DATA PLANE (On-Premise)
┌────────────────────────────┐           ┌──────────────────────┐
│ Portal  Console  API  Auth │  ←sync→   │ STOA GW webMethods   │
│ (React) (React) (Py) (KC) │           │ (Rust)  Kong/Envoy   │
└────────────────────────────┘           └──────────────────────┘
```

For component paths, runtime versions, RBAC roles, rules, skills, and repo
map, see `CLAUDE.md`.

## Historical note

The Python `mcp-gateway/` service was retired in Feb 2026 and superseded by
`stoa-gateway/` (Rust). Any reference to `mcp-gateway` in older docs or
comments is historical.
