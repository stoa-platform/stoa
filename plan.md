# STOA Platform — Plan

> Last updated: 2026-02-08 22:30 CET
> Sprint goal: Revenue-ready demo by Feb 24, 2026

---

## Active — In Progress

### CAB-1112 — Kyverno: Switch Audit → Enforce (5 ClusterPolicies)

**Status**: TODO | **Points**: 2 | **Labels**: mvp-critical | **Cycle**: 6
**Parent**: CAB-1106

**Prérequis**:
- [x] CAB-1106 déployé
- [ ] Minimum 3-5 jours en mode Audit sans faux positifs dans les PolicyReports

**5 ClusterPolicies à basculer**:
1. `disallow-latest-tag`
2. `require-requests-limits`
3. `disallow-privilege-escalation`
4. `require-non-root`
5. `restrict-image-registries`

**DoD**:
- [ ] 5/5 ClusterPolicies en mode `Enforce`
- [ ] Aucun pod légitime bloqué
- [ ] PolicyReports propres (0 FAIL sur resources STOA)

**Exécution recommandée**: Claude CLI (ops sensible, feedback live kubectl)

---

## Completed — Cycle 6

### CAB-1119 — Brand Unification: Logo S Émeraude + Design Tokens + Portal Menu Cleanup ✅

**Status**: DONE | **PR**: #194 (phases 1-3) + #198 (phases 4-5) | **Points**: 13 | **Cycle**: 6

| Phase | Sujet | Status | Result |
|-------|-------|--------|--------|
| Phase 1 | Design Tokens + Favicon Recolor | DONE | Emerald palette, 14 SVG recolors, 3 Keycloak theme files, CSS cleanup |
| Phase 2 | StoaLogo Component + UI Integration | DONE | Inline SVG component, Console sidebar + Portal header/loading/login |
| Phase 3 | Portal Menu Restructure | DONE | 3 sections (Discover/Workspace/Account), tabbed WorkspacePage, redirects |
| Phase 4 | Console Sidebar Restructuration | DONE | 5 sections (Overview/Catalog/⚡Gateway/Insights/Governance), STOA badges, "Control Plane" subtitle |
| Phase 5 | Dark/Light Mode Complet | DONE | Console sidebar light mode, Portal dashboard dark mode (6 components) |

All tests pass (257 console, 236 portal). Both apps build clean. Prettier + ESLint green.

---

### BDD Steps + Clippy Fixes ✅

**Status**: DONE | **PRs**: #191, #192, #196 | **Cycle**: 6

- **PR #191**: Removed 6 duplicate steps from `console-admin.steps.ts` + clippy errors + helm-lint notify
- **PR #192**: Fix clippy `collapsible_if` in `watcher.rs` (clippy 1.93)
- **PR #196**: Removed 12 more duplicate steps from `admin-rbac.steps.ts` (3) + `consumer-flow.steps.ts` (9)

Root cause: PR #184 (CAB-1103) added new step files duplicating existing step definitions. `bddgen` now clean.

---

### AI Factory Enhancement — CI-awareness, Secrets, Rust Gotchas ✅

**Status**: DONE | **PRs**: #195 + #199 (merged) | **Cycle**: 6

| Action | File | Description |
|--------|------|-------------|
| CREATE | `.claude/rules/ci-quality-gates.md` | Exact CI thresholds (Python 53%/40%, ESLint 93/20, Rust zero), 10 failure patterns, pre-commit checklists |
| CREATE | `.claude/rules/secrets-management.md` | Vault/ESO/AWS SM architecture, paths, agent checklist, 6 anti-patterns, rotation |
| UPDATE | `.claude/rules/code-style-rust.md` | 31→128 lines: CI commands, system deps, 7 clippy gotchas, SAST rules |
| UPDATE | `.claude/agents/test-writer.md` | Real CI thresholds, ESLint ratchet, CI exact commands, 5 gotchas |
| UPDATE | `.claude/agents/security-reviewer.md` | Vault/ESO compliance checks, authorized paths, anti-patterns |
| UPDATE | `.claude/agents/k8s-ops.md` | ArgoCD section, ESO diagnostics, Helm nil pointer gotcha |
| UPDATE | `.claude/rules/ai-factory.md` | Pattern 5 (CI-first development), cross-refs to new rules |

13 rules total (11 original + 2 new). Goal: CI-green at first push for all agents.

---

### CAB-1109 — GitOps Pipeline: Manifests, Helm, Policies-as-Code, Shadow→Git MR Loop ✅

**Status**: DONE | **PR**: #188 (merged) + stoa-infra | **Cycle**: 6 | **DoD**: 8/8

| Phase | Sujet | Status | Description |
|-------|-------|--------|-------------|
| 1 | Rego Policies as ConfigMap + SIGHUP | DONE | ConfigMap from `.Files.Glob`, Stakater Reloader, SIGHUP handler in main.rs |
| 2 | Helm Chart Enhancement | DONE | Kyverno `privileged: false`, RBAC CRD watcher, Ingress, nil-safe conditionals, all env vars |
| 3 | Tool/ToolSet CRD Manifests | DONE | `tools.gostoa.dev` + `toolsets.gostoa.dev` CRDs matching Rust structs + examples |
| 4 | Gateway Config Values | DONE | `values-dev.yaml` (1 replica, debug), `values-staging.yaml` (2 replicas, kafka), `values-prod.yaml` (3 replicas, kafka, otel, ingress) |
| 5 | Shadow → Git MR Loop | DONE | `POST /shadow/submit-uac` → GitClient → branch + commit + MR with review checklist |

**stoa-infra — 9 fichiers (7 créés, 2 modifiés):**
- `values.yaml` + `deployment.yaml` modifiés (securityContext, probes, env vars, volumes)
- Créés : `policy-configmap.yaml`, `default.rego`, `rbac.yaml`, `servicemonitor.yaml`, `externalsecret.yaml`, `argocd-application.yaml`, `argocd-crds-application.yaml`

**stoa — 1 fichier modifié:**
- `.github/workflows/stoa-gateway-ci.yml` → supprimé `apply-manifest`, remplacé par `rollout restart`

267 Rust tests pass, clippy clean, fmt clean. Helm lint: 4 variantes pass.

**Prochaine étape opérationnelle (hors ticket):**
1. `kubectl delete deployment stoa-gateway -n stoa-system` (selectors immutables)
2. `kubectl apply -f charts/stoa-gateway/argocd-application.yaml`
3. `kubectl apply -f charts/stoa-platform/argocd-crds-application.yaml`

---

## Completed — Earlier Cycles

### CAB-1116 — Test Automation Strategy (21 SP, 5 phases) ✅

| Phase | Sujet | Status | PR | Result |
|-------|-------|--------|-----|--------|
| Phase 1 | Console UI unit tests (MSW) | DONE | #168 | 25 files, 249 tests, 50.98% coverage |
| Phase 2A | Portal unit tests | DONE | #169 | 20 files, 219 tests, 70% coverage |
| Phase 2B | API unit tests | DONE | #171 | 6 routers, 103 tests, 48%->53% coverage |
| Phase 3A | OpenAPI contract tests | DONE | #172 | 40 tests (6 pytest + 17 console-ui + 17 portal) |
| Phase 3B | Integration tests | DONE | #173 | 20 tests with PostgreSQL 16 in CI |
| Phase 4 | E2E completeness | DONE | #175 | 52->81 scenarios, 100% route coverage |
| Phase 5 | Quality gates | DONE | #176 | CI coverage, pre-commit hooks, formatting |
| Hotfix | Docker build (tsconfig.app.json) | DONE | #177 | Exclude test files from tsc build |
| Hotfix | bddgen @wip tag | DONE | #178 | Skip unimplemented demo-showcase.feature |

#### CI Pipeline Status (2026-02-08)

| Component | CI | Docker | Deploy | Notes |
|-----------|-----|--------|--------|-------|
| control-plane-ui | GREEN | GREEN | GREEN | Coverage + formatting enforced |
| portal | GREEN | GREEN | GREEN | Coverage + formatting enforced |
| control-plane-api | GREEN | — | — | Coverage 53%, ruff lint |
| stoa-gateway | GREEN | — | — | Rust cargo test |

---

### CAB-1103 — Control Plane Agnostique (Phases 1-7) ✅

| Phase | Sujet | Status | PR | Description |
|-------|-------|--------|-----|-------------|
| Phase 1-5 | Core implementation | DONE | — | Models, adapters, sync engine |
| Phase 6 | Operational Readiness | DONE | #184 | CI hardening, monitoring OIDC, E2E expansion, test loop |
| Phase 7 | Gateway Auto-Registration | DONE | #121, #122 | ADR-036 merged |

#### Phase 6 — Operational Readiness (4 sub-phases)

| Sub-phase | Sujet | Status | PR | Result |
|-----------|-------|--------|-----|--------|
| 6A | CI Hardening | DONE | #184 | 5 `|| true` bugs fixed in 7 workflows, 11 intentional documented |
| 6B | Monitoring OIDC | DONE | #184 | Grafana OIDC, oauth2-proxy, AlertManager routing, setup script |
| 6C | E2E Expansion | DONE | #184 | 22 new BDD scenarios (gateway CRUD, deployment lifecycle, admin RBAC, portal consumer) |
| 6D | Test Loop Automation | DONE | #184 | weekly-audit.yml (6 jobs) + smoke tests in mcp-gateway-ci + stoa-gateway-ci |

23 files changed, +1659 lines.

---

### CAB-1105 — Kill Python + Production-Grade MCP Gateway (9 phases) ✅

| Phase | Sujet | Status | PR | Result |
|-------|-------|--------|----|--------|
| Phase 1 | Native Tool Execution | DONE | #180 | JWT auth, native tools, real user context in ToolContext |
| Phase 2 | OPA Policy Engine | DONE | #180 | OPA eval with real JWT claims, ADR-012 role-to-scope |
| Phase 3 | Kafka Metering + Error Snapshots | DONE | #180 | Metering emission, ErrorSnapshot, timing breakdown |
| Phase 4 | Token Optimization Pipeline | DONE | #180 | X-Token-Optimization header, 4-stage pipeline |
| Phase 5 | MCP 2025-03-26 Spec Compliance | DONE | #181 | outputSchema on NativeTool, annotations wired |
| Phase 6 | Circuit Breaker + Cache + Retry | DONE | #181 | Semantic cache in pipeline, CB + retry on CP discovery |
| Phase 7 | K8s CRD + MCP Federation | DONE | #181 | DynamicTool from CRDs, FederatedTool from ToolSets, watcher wired |
| Phase 8 | 4-Mode Architecture | DONE | #181 | Mode-specific router (EdgeMcp/Sidecar/Proxy/Shadow) |
| Phase 9 | Gateway Mode Dashboard | DONE | #181 | Sidebar entry + g+m shortcut |

222 tests pass, clippy clean, fmt clean.

---

## Demo Readiness (Feb 24)

| Priority | Ticket | Description | Status |
|----------|--------|-------------|--------|
| P0 | CAB-1066 | Landing page gostoa.dev + Stripe | NOT STARTED |
| P0 | — | Browser-based demo walkthrough | NOT STARTED |
| P1 | — | Record video backup for demo | NOT STARTED |
| P1 | CAB-1112 | Kyverno policies: Audit → Enforce | NOT STARTED |
| P1 | CAB-1119 | Brand Unification (all 5 phases) | ✅ DONE (#194 + #198) |
| P1 | CAB-1109 | GitOps Pipeline (Helm, CRDs, ArgoCD) | ✅ DONE (#188 + #193) |
| P2 | — | AI Factory CI-awareness + deployment lifecycle | ✅ DONE (#195 + #199) |
| P2 | — | BDD steps + Clippy fixes | ✅ DONE (#191 + #192 + #196) |

### Demo Checklist

- [x] All 4 components deployed on EKS
- [x] CI/CD pipeline green through deploy
- [x] Test coverage enforced in CI
- [x] Pre-commit hooks (lint-staged)
- [x] Prettier formatting (console-ui + portal)
- [x] OpenSearch logs + RGPD + multi-tenant OIDC
- [x] Grafana + Logs iframe embed in console
- [x] Rust gateway production-grade (9 phases, 222 tests)
- [x] CI hardening (`|| true` audit)
- [x] Monitoring OIDC (Grafana + Prometheus + AlertManager)
- [x] E2E expansion (22 new BDD scenarios)
- [x] Weekly audit + smoke tests post-deploy
- [x] Brand Unification phases 1-3 (emerald palette, StoaLogo, Portal menu) — PR #194
- [x] GitOps pipeline (Helm chart, CRDs, ArgoCD sync, CI migration) — PR #188 + stoa-infra
- [x] AI Factory: CI quality gates, secrets mgmt rules, agent enhancements — PR #195
- [x] Brand Unification phases 4-5 (Console sidebar restructure, dark/light mode complet) — PR #198
- [x] Deployment lifecycle rule (PR→CI→Merge→CI→CD→Pod) — PR #199
- [x] BDD duplicate steps + clippy fixes — PRs #191, #192, #196
- [ ] Landing page (gostoa.dev) with Stripe
- [ ] Demo walkthrough script
- [ ] Video backup recording
- [ ] Kyverno Enforce mode