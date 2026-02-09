---
description: Documentation strategy — two-repo split (stoa vs stoa-docs), routing rules, ADR numbering, anti-duplication
---

# Documentation Strategy

## Golden Rule: No Duplication

Documentation lives in **exactly one place**. Never create the same content in both repos.

- **stoa-docs** (Docusaurus, docs.gostoa.dev) = user-facing, public, searchable
- **stoa** (monorepo) = internal/operational, code-coupled, ephemeral

## Decision Tree: Where Does This Doc Go?

```
Is it user-facing (customers, developers, partners)?
├── YES → stoa-docs
│   ├── Architecture decision? → docs/architecture/adr/
│   ├── How-to guide? → docs/guides/
│   ├── Migration from competitor? → docs/guides/migration/
│   ├── API reference? → docs/api/
│   ├── CRD reference? → docs/reference/crds/
│   ├── Concept explainer? → docs/concepts/
│   ├── Enterprise use case? → docs/enterprise/
│   ├── Deployment guide? → docs/deployment/
│   └── Blog post? → blog/
│
└── NO → stoa (monorepo)
    ├── Incident response / ops procedure? → docs/runbooks/
    ├── Sprint plan / project management? → plan.md or docs/*-PLAN.md
    ├── Demo preparation? → docs/demo/
    ├── Developer test guide? → docs/E2E-TESTING.md
    ├── Internal ops (GitOps, secrets)? → docs/
    └── Archived / historical? → docs/archive/
```

**If in doubt**: it goes to stoa-docs. The monorepo docs/ is for ops-only content.

## stoa-docs Inventory (docs.gostoa.dev)

| Category | Path | Count | Examples |
|----------|------|-------|---------|
| ADRs | `docs/architecture/adr/` | 39 | ADR-001 through ADR-039 |
| Architecture | `docs/architecture/` | 3 | Overview, mTLS flow |
| Guides | `docs/guides/` | 10 | Quick start, auth, subscriptions, portal, console |
| Migration guides | `docs/guides/migration/` | 5 | webMethods, Kong, Apigee, Oracle OAM |
| Technical fiches | `docs/guides/fiches/` | 4 | OAuth2, MCP protocol, API patterns, GDPR |
| Concepts | `docs/concepts/` | 8 | Architecture, gateway, GitOps, multi-tenant, UAC, MCP |
| API Reference | `docs/api/` | 2 | Control Plane API, MCP Gateway API |
| CRD Reference | `docs/reference/crds/` | 3 | Tool, ToolSet |
| Reference | `docs/reference/` | 5 | Config, CLI, security, troubleshooting |
| Enterprise | `docs/enterprise/` | 3 | Use cases, security compliance, support |
| Deployment | `docs/deployment/` | 1 | Hybrid deployment |
| Governance | `docs/governance/` | 2 | Review loop |
| Community | `docs/community/` | 4 | Philosophy, rewards, FAQ |
| Blog | `blog/` | 12 | AI agents, ESB is dead, migrations, comparisons |
| **Total** | | **~101 docs + 12 blog** | |

**Before creating any doc**: check if it already exists in stoa-docs. Search by topic, not path.

## stoa (monorepo) — Internal/Operational Only

| Content Type | stoa Path | Why Here (Not stoa-docs) |
|---|---|---|
| Runbooks | `docs/runbooks/` | Incident response, contains infra details |
| Plans | `plan.md`, `docs/*-PLAN.md` | Ephemeral, project management |
| Demo scripts | `docs/demo/` | Internal demo preparation |
| E2E Testing | `docs/E2E-TESTING.md` | Code-coupled, changes with tests |
| GitOps Setup | `docs/GITOPS-SETUP.md` | Ops-specific, infra-coupled |
| Secrets Rotation | `docs/SECRETS-ROTATION.md` | Ops procedures, sensitive |
| AI Factory | `.claude/rules/`, `.claude/agents/` | Claude Code config |
| Memory | `memory.md` | Session state, ephemeral |
| Archive | `docs/archive/` | Historical, internal |

## ADR Numbering Rules

- **stoa-docs owns ADR numbers** — never create an ADR number in stoa repo
- Current range: ADR-001 through ADR-039. **Next available: ADR-040**
- Filename format: `adr-NNN-short-description.md`
- Draft ADRs can live temporarily in stoa repo but MUST be renumbered when moved to stoa-docs
- Always check `stoa-docs/docs/architecture/adr/` for the latest number before creating

## Workflow: New Feature Documentation

1. **Code + tests** in stoa repo (PR to stoa)
2. **Runbook** (if ops-relevant) in `stoa/docs/runbooks/` (same PR)
3. **ADR + Guide** in stoa-docs repo (separate PR to stoa-docs)
4. Both PRs reference each other via commit message or PR body
5. **Never duplicate**: don't put a guide in both stoa/docs/ and stoa-docs/docs/

## Workflow: New ADR

1. Check highest ADR number in `stoa-docs/docs/architecture/adr/`
2. Create ADR with next number in **stoa-docs** directly
3. Reference ADR by URL in stoa code: `https://docs.gostoa.dev/architecture/adr/adr-NNN-*`

## Anti-Duplication Checklist

Before creating any `.md` file in the stoa monorepo:
1. Is this topic already covered in stoa-docs? → **Don't create, link instead**
2. Is this user-facing? → **Goes to stoa-docs, not here**
3. Is this a guide/tutorial? → **stoa-docs/docs/guides/**
4. Is this an architecture decision? → **stoa-docs ADR**
5. Is this ops-only (runbook, secrets, incident)? → **OK in stoa/docs/**
