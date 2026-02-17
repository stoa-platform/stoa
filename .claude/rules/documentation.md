---
description: Documentation strategy — two-repo split (stoa vs stoa-docs), routing rules, ADR numbering, anti-duplication
globs: "docs/**,**/*.md"
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
- Current range: ADR-001 through ADR-047. **Next available: ADR-048**
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

## Interactive Diagram Strategy (stoa-docs)

### Decision Tree: Which Diagram Type?

| Diagram Type | When to Use | Effort | Example |
|-------------|------------|--------|---------|
| **Inline Mermaid** | Simple flows, sequence diagrams, ER diagrams | Low (~10 LOC) | ADR-001, concept pages |
| **Interactive JSX** | Multi-tab content, clickable elements, data-rich | High (~500-700 LOC) | ADR-040, ADR-043, ADR-024, ADR-034 |
| **ASCII art** | Never for new content | N/A | Legacy only — convert on touch |

### When Interactive JSX > Mermaid

Use interactive JSX (React component in `src/components/`) when:
1. Content has **3+ logical sections** that benefit from tabs (architecture + details + roadmap)
2. Diagram needs **clickable/interactive** elements (mode selector, phase picker)
3. Content includes **data tables + visual layout** combined (topic lists, competitive grids)
4. The page is **showcase-worthy** (customer-facing ADRs, core architecture)

### Interactive JSX Component Pattern

Components live in `stoa-docs/src/components/<Name>/index.tsx`. Key patterns:

- **Theme-aware**: use `useColorMode()` from `@docusaurus/theme-common`, two color palettes
- **CSS Grid overlay for tabs**: render ALL tabs simultaneously, `visibility: hidden` on inactive — zero layout shift
- **Docusaurus fonts**: `var(--ifm-font-family-base)`, `var(--ifm-font-family-monospace)` — no external fonts
- **No viewport styles**: no `minHeight: 100vh`, no body background
- **Import in MDX**: `import Component from '@site/src/components/<Name>';` after frontmatter

### Existing Interactive Components

| Component | ADR | Tabs | Description |
|-----------|-----|------|-------------|
| `KafkaMCPArchitecture` | ADR-043 | Architecture, Kafka Topics, Roadmap, Use Cases | Kafka → MCP Event Bridge |
| `GatewayModesArchitecture` | ADR-024 | Architecture, Mode Details, Migration, Roadmap | 4 gateway deployment modes |
| `GitOpsArchitecture` | ADR-040 | Architecture, Promotion, Multi-Tenant, Roadmap | Born GitOps multi-env |
| `MigrationArchitecture` | ADR-034 | Timeline, Shadow Validation, Feature Parity | Python → Rust migration |

### Mermaid Conversions (Batch 1 — PR #57, Batch 2 — PR #58)

| ADR | Diagram Type | PR |
|-----|-------------|-----|
| ADR-001 | 3 flowcharts (architecture, facade, dependencies) | #57 |
| ADR-039 | Middleware pipeline flow (6 stages, color-coded) | #58 |
| ADR-004 | Adapter pattern architecture (registry → adapters → gateways) | #58 |
| ADR-006 | Mixin composition graph (8 modules, semantic colors) | #58 |

**ADR-003** (Monorepo): Skipped — directory trees are optimal as code blocks.

### Remaining Candidates

ADRs with notable ASCII diagrams not yet converted:
- ADR-027 (X509 Headers) — auth flow
- ADR-028 (RFC 8705 Binding) — fingerprint normalization flow
- ADR-012 (MCP RBAC) — policy evaluation chain

## Anti-Duplication Checklist

Before creating any `.md` file in the stoa monorepo:
1. Is this topic already covered in stoa-docs? → **Don't create, link instead**
2. Is this user-facing? → **Goes to stoa-docs, not here**
3. Is this a guide/tutorial? → **stoa-docs/docs/guides/**
4. Is this an architecture decision? → **stoa-docs ADR**
5. Is this ops-only (runbook, secrets, incident)? → **OK in stoa/docs/**
