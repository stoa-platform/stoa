# Archive

Components that have been superseded but are preserved for reference.

## Contents

| Component | Replaced By | Archived |
|-----------|-------------|----------|
| `mcp-gateway/` | `stoa-gateway/` (Rust) | February 2026 |

## mcp-gateway

Python 3.11 / FastAPI implementation of the MCP Gateway. Ran in production from Q3 2025 to
February 2026, handling MCP tool discovery, SSE transport, OPA policy enforcement, and Kafka
metering.

Replaced by the Rust `stoa-gateway` for performance, memory footprint, and unified 4-mode
architecture (ADR-024: edge-mcp, sidecar, proxy, shadow).

### Why archived (not deleted)

- Reference implementation for adapter logic and OPA integration
- Alembic migrations still used by control-plane-api's shared database
- Docker Compose files useful for local development of non-gateway components
- Test fixtures and patterns reusable by the Rust rewrite

### Do not use for

- Production deployments -- use `stoa-gateway/` instead
- New feature development -- all MCP work targets the Rust gateway
- CI pipelines -- mcp-gateway CI was removed in February 2026

## Adding archived components

When retiring a component:

1. Move its directory under `archive/`
2. Remove its CI workflow from `.github/workflows/`
3. Add a row to the table above
4. Keep its `CLAUDE.md` intact for context
