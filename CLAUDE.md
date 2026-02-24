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
| MCP Gateway (archived) | Python 3.11, FastAPI, OPA | `archive/mcp-gateway/` |
| STOA Gateway | Rust, Tokio, axum | `stoa-gateway/` |
| CLI | Python, Typer, Rich | `cli/` |
| E2E Tests | Playwright, BDD, Gherkin | `e2e/` |
| Helm Chart | Helm 3 | `charts/stoa-platform/` |

Gateway: Rust (primary, replaced Python MCP Gateway Feb 2026). 4 modes (ADR-024) — edge-mcp (current), sidecar (Q2), proxy (Q3), shadow (deferred).

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
| `content-reviewer` | Contenu public, concurrents, compliance | Read-only (plan) |
| `verify-app` | Post-deploy SRE verification (9 checks) | Read-only (plan) |
| `competitive-analyst` | AI coding tools competitive intelligence | Read-only (plan) |

### MCP Integrations (Claude.ai Native)
| Service | Use For | Key Actions |
|---------|---------|-------------|
| **Linear** | Ticket lifecycle | `get_issue` (DoD), `update_issue` (Done), `create_comment` (PR link) |
| **Cloudflare** | DNS, Workers, KV | `search_cloudflare_documentation` |
| **Vercel** | stoa-web/docs deploys | `list_deployments`, `get_deployment_build_logs` |
| **Notion** | Knowledge search | `notion-search`, `notion-fetch` |
| **n8n** | Workflow automation | `execute_workflow` |

Full reference: `.claude/rules/mcp-integrations.md`

### Rules (`.claude/rules/`)
Key rules for AI Factory workflow:
- `mcp-integrations.md` — Linear, Cloudflare, Vercel, Notion, n8n MCP usage patterns
- `seo-content.md` — SEO content generation, blog templates, hub & spoke model, editorial calendar integration

### Skills (`.claude/skills/`)
- 8 legacy: `implement-feature`, `fix-bug`, `review-pr`, `audit-component`, `create-adr`, `e2e-test`, `refactor`, `update-memory`
- 2 modernes: `/ci-debug [PR|run-url]` (fork), `/parallel-review [PR|path]` (inline)
- 3 MCP-powered: `/council` (4-persona validation → Linear), `/sync-plan` (plan.md ↔ Linear), `/decompose` (MEGA → component-scoped sub-issues + DAG)
- 5 ops: `/analytics` (5 data sources, 12 queries), `/competitive-watch` (veille L1-L3), `/ci-fix` (auto-fix CI), `/carto` (platform service catalog + drift detection), `/impact` (reverse dependency analysis + blast radius)
- 2 sprint: `/fill-cycle` (capacity gap analysis), `/generate-backlog` (MEGA backlog generation)

### Slash Commands (`.claude/commands/`)
- `/status` — quick project snapshot (git, PRs, CI, pods, tokens)
- `/deploy-check` — post-merge CD verification
- `/token-report` — 7-day token cost analysis
- `/benchmark-competitors` — quarterly competitive benchmark (9-dimension matrix)

### Agent Teams (experimental)
Prerequis: `brew install tmux` + `export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`

### Parallel Sessions (git worktrees)
Named worktrees in `.claude/worktrees/` for concurrent Claude Code sessions:
```bash
za   # analysis worktree (read-only exploration)
zf   # feature session (main repo)
zh   # hotfix worktree (ephemeral, from main)
```

## Repos

| Repo | Stack | URL | Visibility |
|------|-------|-----|------------|
| stoa | Python + React + Rust | github.com/stoa-platform/stoa | Public |
| stoa-strategy | Markdown + Prompts | github.com/PotoMitan/stoa-strategy | **Private** (client data, pricing, GTM) |
| stoa-infra | Terraform + Ansible + Helm | github.com/PotoMitan/stoa-infra | Private |
| stoa-docs | Docusaurus | github.com/stoa-platform/stoa-docs | Public |
| stoa-web | Astro | github.com/stoa-platform/stoa-web | Public |
| stoa-quickstart | Docker Compose | github.com/stoa-platform/stoa-quickstart | Public |
| stoactl | Go + Cobra | github.com/stoa-platform/stoactl | Public |
