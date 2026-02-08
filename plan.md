# STOA Platform — Plan

> Last updated: 2026-02-08
> Sprint goal: Revenue-ready demo by Feb 24, 2026

## CAB-1116 — Test Automation Strategy (21 SP, 5 phases) — ALL DONE

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

### CI Pipeline Status (2026-02-08)

| Component | CI | Docker | Deploy | Notes |
|-----------|-----|--------|--------|-------|
| control-plane-ui | GREEN | GREEN | GREEN | Coverage + formatting enforced |
| portal | GREEN | GREEN | GREEN | Coverage + formatting enforced |
| control-plane-api | GREEN | — | — | Coverage 53%, ruff lint |
| stoa-gateway | GREEN | — | — | Rust cargo test |

---

## CAB-1103 — Control Plane Agnostique (Phases 1-7 DONE)

| Phase | Sujet | Status | PR | Description |
|-------|-------|--------|-----|-------------|
| Phase 1-5 | Core implementation | DONE | — | Models, adapters, sync engine |
| Phase 6 | Operational Readiness | DONE | #184 | CI hardening, monitoring OIDC, E2E expansion, test loop |
| Phase 7 | Gateway Auto-Registration | DONE | #121, #122 | ADR-036 merged |

### Phase 6 — Operational Readiness (4 sub-phases) — ALL DONE

| Sub-phase | Sujet | Status | PR | Result |
|-----------|-------|--------|-----|--------|
| 6A | CI Hardening | DONE | #184 | 5 `|| true` bugs fixed in 7 workflows, 11 intentional documented |
| 6B | Monitoring OIDC | DONE | #184 | Grafana OIDC, oauth2-proxy, AlertManager routing, setup script |
| 6C | E2E Expansion | DONE | #184 | 22 new BDD scenarios (gateway CRUD, deployment lifecycle, admin RBAC, portal consumer) |
| 6D | Test Loop Automation | DONE | #184 | weekly-audit.yml (6 jobs) + smoke tests in mcp-gateway-ci + stoa-gateway-ci |

#### Files Changed (23 files, +1659 lines)
- **6A**: 7 workflow files patched (security-scan, e2e-audit, platform-config-ci, e2e-tests, keycloak-theme, reusable-k8s-deploy, reusable-notify)
- **6B**: docker-compose.yml, alertmanager.yml, setup-observability-oidc.sh, .env.example, values.yaml
- **6C**: 4 feature files + 4 step definition files (all `@wip` tagged)
- **6D**: weekly-audit.yml (new), mcp-gateway-ci.yml, stoa-gateway-ci.yml

---

## CAB-1105 — Kill Python + Production-Grade MCP Gateway (9 phases) — ALL DONE

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
| P1 | — | Kyverno policies: Audit -> Enforce | NOT STARTED |
| P2 | — | E2E smoke tests on live infra (timeouts) | KNOWN ISSUE |

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
- [ ] Landing page (gostoa.dev) with Stripe
- [ ] Demo walkthrough script
- [ ] Video backup recording
- [ ] Kyverno Enforce mode
