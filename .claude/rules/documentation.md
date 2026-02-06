# Documentation Strategy

## Two-Repo Split

Documentation is split between **stoa** (monorepo) and **stoa-docs** (Docusaurus).

### stoa-docs (Docusaurus) — docs.gostoa.dev
**Source of truth** for all user-facing documentation.

| Content Type | stoa-docs Path | Notes |
|---|---|---|
| ADRs | `docs/architecture/adr/` | **Single source of truth for ADR numbering** |
| Guides | `docs/guides/` | How-to documentation |
| Migration guides | `docs/guides/migration/` | WebMethods, Kong, Apigee, Oracle OAM |
| Technical fiches | `docs/guides/fiches/` | Deep-dive technical documents |
| API Reference | `docs/api/` | Control Plane API, MCP Gateway API |
| CRD Reference | `docs/reference/crds/` | Tool, ToolSet CRDs |
| Concepts | `docs/concepts/` | Architecture, MCP, UAC, multi-tenancy |
| Enterprise | `docs/enterprise/` | Use cases, security, support |
| Deployment | `docs/deployment/` | Hybrid deployment guide |
| Community | `docs/community/` | FAQ, philosophy, rewards |

### stoa (monorepo) — Internal/Operational
**Operational documentation** that stays close to the code.

| Content Type | stoa Path | Reason |
|---|---|---|
| Runbooks | `docs/runbooks/` | Incident response, not user-facing |
| Plans | `docs/*-PLAN.md`, `plan.md` | Project management, ephemeral |
| Demo scripts | `docs/demo/` | Internal demo preparation |
| E2E Testing | `docs/E2E-TESTING.md` | Developer-facing, code-coupled |
| GitOps Setup | `docs/GITOPS-SETUP.md` | Ops-specific, infra-coupled |
| Secrets Rotation | `docs/SECRETS-ROTATION.md` | Ops procedures |
| Archive | `docs/archive/` | Historical, internal |
| Templates | `docs/templates/` | Internal templates |

## ADR Numbering Rules

- **stoa-docs owns ADR numbers** — never create an ADR number in stoa repo
- Next available ADR: check `stoa-docs/docs/architecture/adr/` for highest number
- ADR filename format: `adr-NNN-short-description.md`
- Draft ADRs can live temporarily in stoa repo but MUST be renumbered when moved to stoa-docs
- Current stoa-docs range: ADR-001 through ADR-034

## ADR Number Conflicts (Known)

The stoa repo has 3 ADRs with **conflicting numbers** vs stoa-docs:

| stoa repo # | stoa repo topic | stoa-docs # | stoa-docs topic | Resolution |
|---|---|---|---|---|
| ADR-027 | Gateway Adapter Pattern | ADR-027 | X.509 Header Auth | Renumber to ADR-035 |
| ADR-028 | Gateway Auto-Registration | ADR-028 | RFC8705 Cert Binding | Renumber to ADR-036 |
| ADR-033 | Deployment Modes Sovereign | ADR-033 | Shared UI Components | Renumber to ADR-037 |

## Workflow: New Feature Documentation

1. **Code + tests** in stoa repo (PR to stoa)
2. **Runbook** in `stoa/docs/runbooks/` (same PR or follow-up)
3. **ADR + Guide** in stoa-docs repo (separate PR to stoa-docs)
4. Both PRs reference each other

## Workflow: New ADR

1. Check highest ADR number in `stoa-docs/docs/architecture/adr/`
2. Create ADR with next number in **stoa-docs** directly
3. Reference ADR by URL in stoa code comments: `https://docs.gostoa.dev/architecture/adr/adr-NNN-*`
