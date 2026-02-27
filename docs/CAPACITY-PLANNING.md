# STOA Platform — Capacity Planning 2026

**Last updated:** 2026-02-27
**Target:** v1.0 GA — September 30, 2026
**Tracking:** [Linear Project](https://linear.app/cab-ing) | Auto-generated view: [ROADMAP.md](/ROADMAP.md)

---

## Milestones

| Milestone | Target | Key Deliverables |
|-----------|--------|-----------------|
| Demo MVP | 2026-03-31 | Gateway MCP + Portal + Console basics |
| Public Beta | 2026-05-31 | CLI + Quickstart + Community launch |
| Enterprise Ready | 2026-07-31 | mTLS + RBAC + Multi-tenant + DORA |
| v1.0 GA | 2026-09-30 | Full platform, production-hardened |
| Community 1K | 2026-12-31 | 1000 GitHub stars, active contributors |

---

## 6 Roadmap Themes

### 1. Gateway & MCP (`roadmap:gateway`)
Rust gateway (axum/tokio), MCP protocol, OAuth 2.1 proxy, mTLS, Arena benchmarks.

| Status | Scope |
|--------|-------|
| Done | MCP core, OAuth 2.1, CRD watcher, 4-mode architecture (ADR-024) |
| In Progress | Streamable HTTP, proxy hardening, circuit breakers |
| Planned | Sidecar mode (Q2), proxy mode (Q3) |

### 2. Developer Experience (`roadmap:dx`)
CLI (stoactl), SDK, quickstart, docs (Docusaurus), tutorials, llms.txt.

| Status | Scope |
|--------|-------|
| Done | Docusaurus site, quickstart Docker Compose, llms.txt |
| In Progress | stoactl Go CLI, interactive tutorials |
| Planned | SDK (Python/JS), Playground UI |

### 3. Platform Core (`roadmap:platform`)
Control Plane API (FastAPI), Console UI (React), Portal, RBAC, multi-tenant, adapters.

| Status | Scope |
|--------|-------|
| Done | API CRUD, Console RBAC, Portal catalog, 7 gateway adapters |
| In Progress | Subscription flow, UAC engine |
| Planned | Multi-tenant isolation, API versioning |

### 4. Community & OSS (`roadmap:community`)
Blog, SEO, contributors, Discord, launch weeks, GitHub presence.

| Status | Scope |
|--------|-------|
| Done | Blog (12 posts), SEO hub & spoke, JSON-LD, llms.txt |
| In Progress | Editorial calendar, contributor guide |
| Planned | Launch Week Q2, Discord community, 1K stars campaign |

### 5. Observability (`roadmap:observability`)
Metrics, Arena (3-layer benchmark), Grafana, alerts, SLOs, Pushgateway.

| Status | Scope |
|--------|-------|
| Done | Arena L0/L1/L2, Pushgateway, Grafana dashboards, Healthchecks |
| In Progress | PrometheusRule alerts, cost observatory |
| Planned | Distributed tracing, tenant-scoped dashboards |

### 6. Security & Compliance
DORA, mTLS, OPA, Keycloak, audit, Infisical, Kyverno, signed commits.

| Status | Scope |
|--------|-------|
| Done | Keycloak RBAC, Infisical secrets, Kyverno policies, security-scan CI |
| In Progress | mTLS Stage 2, DORA compliance docs |
| Planned | SOC 2 preparation, penetration testing automation |

---

## Velocity Reference

| Metric | Value | Source |
|--------|-------|--------|
| AI Factory throughput | ~200 pts/cycle | Linear cycles 7-11 |
| Avg ticket size | 5-8 pts | Linear backlog |
| Proven velocity | 150-200 pts/2-week cycle | Last 5 cycles |
| Autonomous pipeline | 5-12 tickets/day (L1-L3) | AI Factory levels |

---

## Archive

The original capacity plan (v4.0, Jan 5 2026) referenced AWS/EKS, Cilium, Jenkins,
and Lambda — all decommissioned in Feb 2026 during the Hetzner/OVH migration.
Historical phases (1-12, 9.5) are fully completed. See `git log` for the original file.

---

*Run `/roadmap` for a live visual snapshot with theme percentages from Linear.*
