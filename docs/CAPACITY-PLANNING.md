# STOA Platform — Roadmap v2

> Auto-synced via `/roadmap --update`. Source of truth: Linear labels `roadmap:*`
> Last sync: 2026-02-27
>
> Replaces the original 14-phase capacity plan (Jan 2026). See "Legacy Phases" below.

## Milestones

| Date | Milestone | Status | Notes |
|------|-----------|--------|-------|
| 2026-02-17 | Demo MVP Ready | Done | Core features validated |
| 2026-03-17 | Demo Day | Active | Live stakeholder demo |
| 2026-04-30 | Private Beta | Planned | 3 design partners |
| 2026-06-30 | RC1 Public Beta | Planned | Community beta |
| 2026-07-31 | v1.0 GA | Planned | General Availability |

## Theme: Gateway (`roadmap:gateway`)

Rust gateway (replaced Python MCP Gateway Feb 2026). 4 modes (ADR-024).

**Key deliverables**: edge-mcp mode, sidecar mode (Q2), proxy mode (Q3), OAuth 2.1 MCP flow, mTLS, adapter pattern (Kong/Gravitee/webMethods/Apigee/AWS/Azure), Arena benchmarks.

## Theme: Platform (`roadmap:platform`)

Core control plane: FastAPI API, React Console, multi-tenant RBAC, UAC.

**Key deliverables**: consumer model, subscription lifecycle, gateway adapter registry, Alembic migrations, Keycloak integration, ArgoCD GitOps.

## Theme: DX (`roadmap:dx`)

Developer experience: portal, CLI, docs, quickstart.

**Key deliverables**: Developer Portal (React), self-service signup, API catalog, subscription management, Docusaurus docs site, Docker quickstart.

## Theme: Security (`roadmap:security`)

Authentication, authorization, secrets, compliance.

**Key deliverables**: mTLS (Stage 1-3), DPoP tokens, RBAC (4 roles), OPA policy engine, security scanner (Gitleaks/Bandit/Trivy), Infisical secrets management.

## Theme: Community (`roadmap:community`)

Open source, documentation, SEO, community engagement.

**Key deliverables**: Apache 2.0 licensing, 38 blog articles, SEO (llms.txt, JSON-LD, GSC), GitHub Discussions, stoa-docs (101 docs), stoa-web landing page.

## Theme: Observability (`roadmap:observability`)

Monitoring, dashboards, alerts, benchmarks.

**Key deliverables**: Gateway Arena (L0 baseline + L1 enterprise + L2 platform verify), Prometheus + Pushgateway, Grafana dashboards, Healthchecks dead man's switch.

## Velocity

See `velocity.json` for historical cycle data. Current rolling 3-cycle average:
- **99.4 pts/day** | 6.5 issues/day | 100% completion
- Capacity target (7d cycle): 557 pts

## Legacy Phases (archived)

> The original 14-phase plan (Jan 5, 2026) was based on AWS/EKS infrastructure.
> After migration to OVH MKS + Hetzner K3s (Feb 2026), most phases became obsolete.
> Archived below for historical reference.

<details>
<summary>Click to expand legacy phase analysis</summary>

| Phase | Original Scope | Status | Reason |
|-------|---------------|--------|--------|
| 1 | Event-Driven Architecture | **Done** | Redpanda, AWX, FastAPI, React |
| 2 | GitOps + ArgoCD | **Done** | ArgoCD deployed on OVH MKS |
| 2.5 | Validation E2E | **Done** | Playwright BDD framework |
| 2.6 | Cilium Foundation | **Obsolete** | Cilium is AWS/EKS-specific; OVH K3s uses Calico |
| 3 | Vault + Secrets | **Done differently** | Infisical replaces HashiCorp Vault |
| 4 | OpenSearch + Monitoring | **Partially valid** | OpenSearch deployed but not fully integrated |
| 4.5 | Jenkins Orchestration | **Obsolete** | GitHub Actions replaced Jenkins entirely |
| 5 | Multi-environment | **Done differently** | Hetzner staging exists, not AWS-based |
| 6 | Demo Tenant | **Done** | CAB-1304 demo tenant automation |
| 7 | Security Jobs | **Done differently** | GHA security-scan.yml replaces custom jobs |
| 8 | Portal Self-Service | **Done** | Portal fully functional |
| 9 | Ticketing ITSM | **Replaced** | Linear + n8n replaces custom ITSM |
| 9.5 | Production Readiness | **Done** | SLOs, runbooks, load tests |
| 10 | Resource Lifecycle | **Obsolete** | Lambda/EventBridge are AWS-specific |
| 11 | Resource Advanced | **Obsolete** | Lambda-based, AWS-specific |
| 12 | MCP Gateway | **Done** | Rust gateway operational |
| 14 | GTM Strategy | **Partially done** | OSS files, docs, landing done; pricing/beta remain |

**Summary**: 42/105 original issues completed. ~40 issues obsolete (AWS-specific). ~23 issues done differently or replaced by modern alternatives.

</details>
