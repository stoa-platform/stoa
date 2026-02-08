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

## Next Up — Demo Readiness (Feb 24)

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
