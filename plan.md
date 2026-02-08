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

## Free Run Final — CAB-1103 + CAB-1105

> Optimized 3-wave execution. Phase 7 (Auto-Registration) = SKIP (already done, PRs #121/#122).

---

### CAB-1103 — Control Plane Agnostique (Phases 1-5 DONE, Phase 7 DONE)

| Phase | Sujet | Status | Vague | Description |
|-------|-------|--------|-------|-------------|
| Phase 1-5 | Core implementation | DONE | — | Models, adapters, sync engine |
| **Phase 6** | **Operational Readiness** | NOT STARTED | Vague 1 (CS) | CI hardening, monitoring OIDC, E2E expansion, test loop |
| Phase 7 | Gateway Auto-Registration | DONE | — | PRs #121, #122. ADR-036 merged. |

#### Phase 6 — Operational Readiness (4 sub-phases, CS parallel)

| Sub-phase | Sujet | DoD | CS Branch |
|-----------|-------|-----|-----------|
| 6A | CI Hardening | Zero `|| true`, `helm lint` passes, coverage threshold | `feat/cab-1103-6a-ci-hardening` |
| 6B | Monitoring OIDC | Keycloak client `stoa-observability`, Grafana OIDC, AlertManager | `feat/cab-1103-6b-monitoring-oidc` |
| 6C | E2E Expansion | ≥20 new Playwright scenarios (GW CRUD, deploy, RBAC, portal) | `feat/cab-1103-6c-e2e-expansion` |
| 6D | Test Loop Automation | `npm run test:smoke` in CI, weekly audit workflow | `feat/cab-1103-6d-test-loop` |

---

### CAB-1105 — Kill Python + Production-Grade MCP Gateway (9 phases)

| Phase | Sujet | Status | Vague | Description |
|-------|-------|--------|-------|-------------|
| Phase 1 | Native Tool Execution | DONE | PR #180 | JWT auth → native tools, real user context in ToolContext |
| Phase 2 | OPA Policy Engine | DONE | PR #180 | OPA eval with real JWT claims, ADR-012 role-to-scope expansion |
| Phase 3 | Kafka Metering + Error Snapshots | DONE | PR #180 | Metering emission on all outcomes, ErrorSnapshot, timing breakdown |
| Phase 4 | Token Optimization Pipeline | DONE | PR #180 | X-Token-Optimization header, 4-stage pipeline on responses |
| Phase 5 | MCP 2025-03-26 Spec Compliance | DONE | Phases 5-9 PR | outputSchema on NativeTool, annotations wired |
| Phase 6 | Circuit Breaker + Cache + Retry | DONE | Phases 5-9 PR | Semantic cache in pipeline, CB + retry on CP discovery |
| Phase 7 | K8s CRD + MCP Federation | DONE | Phases 5-9 PR | DynamicTool from CRDs, FederatedTool from ToolSets, watcher wired |
| Phase 8 | 4-Mode Architecture | DONE | Phases 5-9 PR | Mode-specific router (EdgeMcp/Sidecar/Proxy/Shadow), closures for state |
| Phase 9 | Gateway Mode Dashboard | DONE | Phases 5-9 PR | Sidebar entry + shortcut g+m, GatewayModesDashboard already existed |

#### Performance Gates (Phase 1-4)

| Metric | Before | Target |
|--------|--------|--------|
| tools/call | ~1038ms | <200ms |
| OPA eval | N/A | <1ms |
| Token optimization | N/A | <5ms |
| Metering overhead | N/A | <2ms |

#### Crates to add

| Crate | Phase | Purpose |
|-------|-------|---------|
| regorus | Phase 2 | OPA policy eval (pure Rust, <1ms) |
| rdkafka | Phase 3 | Kafka producer (fire-and-forget) |
| opentelemetry + otlp | Phase 6 | OTLP traces/metrics/logs |
| moka | Phase 6 | In-memory semantic cache |
| kube + kube-runtime | Phase 7 | K8s CRD watcher |

---

### Execution Plan — 3 Vagues

```
VAGUE 1 (~90 min reel, 2 terminaux paralleles)
├── Terminal 1 — CS: 4 agents Phase 6        ← .github/, keycloak, e2e/
│   ├── Agent 6A: feat/cab-1103-6a-ci-hardening
│   ├── Agent 6B: feat/cab-1103-6b-monitoring-oidc
│   ├── Agent 6C: feat/cab-1103-6c-e2e-expansion
│   └── Agent 6D: feat/cab-1103-6d-test-loop
└── Terminal 2 — CLI: Phases 1→2→3→4         ← stoa-gateway/src/ (pas de conflit)
    └── Branch: feat/cab-1105-kill-python

VAGUE 2 (~60 min, sequentiel)
└── CLI: Phases 5→6→7                        ← stoa-gateway/src/
    └── Branch: feat/cab-1105-kill-python (continue)

VAGUE 3 (~45 min reel, CS parallele)
├── Agent A: Phase 8 (4-Mode Rust)           ← stoa-gateway/src/mode/
│   └── Branch: feat/cab-1105-gateway-modes
└── Agent B: Phase 9 (Dashboard React)       ← control-plane-ui/src/
    └── Branch: feat/cab-1105-mode-dashboard
```

#### Merge Order

```
1. feat/cab-1103-6a-ci-hardening       → main   (workflows)
2. feat/cab-1103-6d-test-loop          → main   (workflows, meme zone que 6A)
3. feat/cab-1103-6b-monitoring-oidc    → main   (config/deploy)
4. feat/cab-1103-6c-e2e-expansion      → main   (e2e/)
5. feat/cab-1105-kill-python           → main   (stoa-gateway/ — gros merge P1-7)
6. feat/cab-1105-gateway-modes         → main   (stoa-gateway/src/mode/)
7. feat/cab-1105-mode-dashboard        → main   (control-plane-ui/)
```

#### Summary

| Vague | Mode | Phases | Duree reelle | Branches |
|-------|------|--------|-------------|----------|
| Vague 1 | CS (4 agents) + CLI en parallele | 6A+6B+6C+6D // P1+P2+P3+P4 | ~90 min | 5 |
| Vague 2 | CLI sequentiel | P5+P6+P7 | ~60 min | 1 |
| Vague 3 | CS (2 agents) parallele | P8 // P9 | ~45 min | 2 |

**Total: ~3h15 reel** (vs ~4h30 sequentiel). 8 branches, 7 PRs.

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
- [ ] Landing page (gostoa.dev) with Stripe
- [ ] Demo walkthrough script
- [ ] Video backup recording
- [ ] Kyverno Enforce mode
