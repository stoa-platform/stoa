# CLAUDE.md — STOA Platform

## Project
**STOA Platform** — "The European Agent Gateway"
- API Management AI-Native Open Source (Apache 2.0)
- Kill feature: UAC (Universal API Contract) — "Define Once, Expose Everywhere"
- Legacy-to-MCP Bridge: connect traditional APIs to AI agents

## Architecture

```
CONTROL PLANE (Cloud)                    DATA PLANE (On-Premise)
┌────────────────────────────┐           ┌──────────────────────┐
│ Portal  Console  API  Auth │  ←sync→   │ MCP GW  webMethods   │
│ (React) (React) (Py) (KC) │           │ (Py)    Kong/Envoy   │
└────────────────────────────┘           └──────────────────────┘
```

## Components

| Component | Tech | Path |
|-----------|------|------|
| Control Plane API | Python 3.11, FastAPI, SQLAlchemy | `control-plane-api/` |
| Console UI | React 18, TypeScript, Keycloak-js | `control-plane-ui/` |
| Developer Portal | React, Vite, TypeScript | `portal/` |
| MCP Gateway | Python 3.11, FastAPI, OPA | `mcp-gateway/` |
| STOA Gateway | Rust, Tokio, axum | `stoa-gateway/` |
| CLI | Python, Typer, Rich | `cli/` |
| E2E Tests | Playwright, BDD, Gherkin | `e2e/` |
| Helm Chart | Helm 3 | `charts/stoa-platform/` |

Gateway: 4 modes (ADR-024) — edge-mcp (current, Python), sidecar (Q2), proxy (Q3), shadow (deferred). Target: Rust (Q4 2026).

## RBAC Roles
- **cpi-admin**: Full platform (stoa:admin)
- **tenant-admin**: Own tenant (stoa:write, stoa:read)
- **devops**: Deploy/promote (stoa:write, stoa:read)
- **viewer**: Read-only (stoa:read)

## Key URLs
| Service | URL |
|---------|-----|
| Console | https://console.gostoa.dev |
| Portal | https://portal.gostoa.dev |
| API | https://api.gostoa.dev |
| MCP Gateway | https://mcp.gostoa.dev |
| Auth (Keycloak) | https://auth.gostoa.dev |
| Docs | https://docs.gostoa.dev |
| Vault | https://vault.gostoa.dev |

## Runtime Versions

| Tool | Version | Components |
|------|---------|------------|
| Python | 3.11 | control-plane-api, mcp-gateway, cli |
| Python | 3.12 | landing-api |
| Node | 20 | portal, control-plane-ui |
| Rust | stable | stoa-gateway |

## Session Workflow

1. Read `memory.md` for current state
2. Read `plan.md` for priorities
3. **1 thing at a time** — never mix feature + refactor + fix
4. **Never code without a validated plan**
5. Update `memory.md` before ending session
6. Commit often with conventional messages

## AI Factory

### Subagents (`.claude/agents/`)
| Agent | Specialite | Mode |
|-------|-----------|------|
| `security-reviewer` | OWASP, secrets, RBAC, deps vulns | Read-only (plan) |
| `test-writer` | vitest, pytest, Playwright BDD | Full access |
| `k8s-ops` | K8s debug, Helm, nginx, rollout | Read-only (plan) |
| `docs-writer` | ADRs, guides, runbooks, memory | No Bash |

### Skills (`.claude/skills/`)
- 8 legacy: `implement-feature`, `fix-bug`, `review-pr`, `audit-component`, `create-adr`, `e2e-test`, `refactor`, `update-memory`
- 2 modernes: `/ci-debug [PR|run-url]` (fork), `/parallel-review [PR|path]` (inline)

### Agent Teams (experimental)
Prerequis: `brew install tmux` + `export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`

## Repos

| Repo | Stack | URL |
|------|-------|-----|
| stoa | Python + React + Rust | github.com/stoa-platform/stoa |
| stoa-infra | Terraform + Ansible + Helm | github.com/PotoMitan/stoa-infra |
| stoa-docs | Docusaurus | github.com/stoa-platform/stoa-docs |
| stoa-web | Astro | github.com/stoa-platform/stoa-web |
| stoa-quickstart | Docker Compose | github.com/stoa-platform/stoa-quickstart |
| stoactl | Go + Cobra | github.com/stoa-platform/stoactl |
