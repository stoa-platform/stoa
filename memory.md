# STOA Memory

> Last updated: 2026-02-08 (Session 18 — CAB-1116 Phase 5 Quality Gates + Hotfixes)

## Active Sprint
- **Goal**: Revenue-ready demo by Feb 24, 2026
- **Branch**: main
- **Focus**: CAB-1116 Test Automation complete (all 5 phases + 2 hotfixes). Shift to demo readiness.

## Session State

| Status | Ticket | Description | Evidence |
|--------|--------|-------------|----------|
| DONE | CAB-1044 | API Search HTTP 500 fix | commit 2c5672d8 |
| DONE | CAB-1040 | Gateway Routes HTTP 404 fix | commit 0c33e21d |
| DONE | CAB-1042 | Vault sealed fix | commit 8bbf71b9 |
| DONE | CAB-1041 | E2E BDD auth fix | commit 248f9d29 |
| DONE | — | CLI stoa v0.1.0 (5 commands, 55 tests, 84% coverage) | Session 2 |
| DONE | — | E2E tests 24/24 pass | Session 3 |
| DONE | CAB-1061 | Demo data seed script | Session 4 |
| DONE | CAB-1060 | Docs 20 pages (Docusaurus) | Session 5 |
| DONE | CAB-1062 | Docker image + CI deploy | PR #74, Session 6 |
| DONE | ADR-030 | AI context management architecture | Session 7 |
| DONE | — | Context refactor: CLAUDE.md 11KB→3KB + 8 rules + 8 component docs + 8 skills + hooks | Session 7 |
| DONE | CAB-CD-001 | Enterprise CD Architecture deployed on EKS | Session 8, commit 46401a3b |
| DONE | CAB-1113 | Performance Phase 5: SQL filtering + DTOs (portal.py) | Session 9 |
| DONE | CAB-1113 | Performance Phase 6: Cache + Keycloak Boot + Web Vitals | PR #139, Session 10 |
| DONE | CAB-1114 | OpenSearch Phase 1: Deploy + Dashboards + Ingestion | commit 03665d57, e6e72a52 |
| DONE | CAB-1114 | OpenSearch Phase 2: RGPD redaction pipeline (7 PII patterns) | commit 35fa3943, Session 11 |
| DONE | CAB-1114 | OpenSearch Phase 3: Multi-Tenant OIDC Security | Session 12+13, 6/6 tests |
| DONE | CAB-1114 | OpenSearch Phase 4: Console Integration (SSO iframe) | Session 14, LogsEmbed.tsx |
| DONE | CAB-1115 | Console UI Performance Optimization | PR #148, Hotfix PR #150 |
| DONE | CAB-1108 | Iframe Embed Fix — Logs + Grafana (nginx reverse proxy) | PRs #153, #155, #164-167 |
| DONE | — | EKS Deploy Fixes — All 4 components running | PRs #149, #152, #154, #157 |
| DONE | — | AI Factory Setup (4 agents, 2 skills, 1 rule) | Session 16 |
| DONE | CAB-1116 | Phase 1: Console UI unit tests (MSW) | PR #168 — 25 files, 232 tests, 50.98% coverage |
| DONE | CAB-1116 | Phase 2A: Portal unit tests | PR #169 — 20 files, 219 tests, 70% coverage |
| DONE | CAB-1116 | Phase 2B: API unit tests | PR #171 — 6 routers, 103 tests, 48%→53% coverage |
| DONE | CAB-1116 | Phase 3A: OpenAPI contract tests | PR #172 — 40 tests (6 pytest + 17 console-ui + 17 portal) |
| DONE | CAB-1116 | Phase 3B: Integration tests (PostgreSQL 16 in CI) | PR #173 — 20 tests |
| DONE | CAB-1116 | Phase 4: E2E completeness 52→81 scenarios | PR #175 — 100% route coverage |
| DONE | CAB-1116 | Phase 5: Quality gates (coverage, format, hooks) | PR #176 — CI enforcement |
| DONE | CAB-1116 | Hotfix: Docker build (tsconfig.app.json) | PR #177 — exclude test files from tsc |
| DONE | CAB-1116 | Hotfix: bddgen @wip tag | PR #178 — skip demo-showcase.feature |
| NEXT | CAB-1066 | Landing gostoa.dev + Stripe | — |
| NEXT | — | Browser-based demo walkthrough | — |
| NEXT | — | Record video backup for demo | — |
| NEXT | — | Kyverno policies: Audit → Enforce | — |

## CI Pipeline Status (2026-02-08) — ALL GREEN THROUGH DEPLOY

| Component | CI | Docker | Apply | Deploy | Notes |
|-----------|-----|--------|-------|--------|-------|
| control-plane-ui | GREEN | GREEN | GREEN | GREEN | Coverage + formatting enforced |
| portal | GREEN | GREEN | GREEN | GREEN | Coverage + formatting enforced |
| control-plane-api | GREEN | — | — | — | Coverage 53%, ruff lint |
| stoa-gateway | GREEN | — | — | — | Rust cargo test |

## Quality Gates (CAB-1116 Phase 5)
- **Coverage enforced in CI** via `run-coverage: true` in reusable workflow
- **Pre-commit hooks**: lint-staged (eslint + prettier + ruff) via husky
- **Prettier**: installed on console-ui (was missing), blocking in CI via `--if-present`
- **ESLint ratchet**: console-ui max-warnings=93 (down from 100)
- **Python fail_under**: aligned to 53 in pyproject.toml (was 70, CI was 53)
- **commitlint**: added `e2e` scope

## Decisions This Sprint
- 2026-02-04: Use column refs in SQLAlchemy upsert (not string keys)
- 2026-02-04: E2E auth requires dual OIDC client tokens (portal + console)
- 2026-02-05: ADRs live in stoa-docs, not stoa (ADR-030)
- 2026-02-05: Retire .stoa-ai/ — migrate to native Claude Code features
- 2026-02-05: CLAUDE.md hierarchy: root (compact) + .claude/rules/ (modular)
- 2026-02-06: Kyverno policies in Audit mode first, Enforce after validation
- 2026-02-06: ArgoCD ApplicationSet uses goTemplate mode for multi-env
- 2026-02-07: Custom nginx envsubst script (not built-in) — see `.claude/rules/k8s-deploy.md`
- 2026-02-07: `tsconfig.app.json` pattern to exclude test files from Docker builds
- 2026-02-08: ESLint ratchet (93 warnings) instead of strict 0 — blocks new warnings, allows gradual cleanup
- 2026-02-08: lint-staged without `--max-warnings` — CI enforces the ratchet, pre-commit only checks syntax
- 2026-02-08: `@wip` tag + `tags: 'not @wip'` in defineBddConfig to skip unimplemented features

## Known Issues
- E2E smoke tests fail on live infra (timeouts, missing UI elements) — not a CI config issue
- Dependency Review fails: GitHub Advanced Security not enabled on stoa repo
- Container Scan / CodeQL: intermittent failures, not blocking
- DCO Check: fails on squash-merged commits (expected, non-blocking)

## Notes
- Demo: mardi 24 fevrier 2026
- Presentation "ESB is Dead" same day
- 2 design partners to close
- Stack = Python (not Node)
- Console tenants: "oasis", "oasis-gunters"
- Portal OIDC client: stoa-portal; Console OIDC client: control-plane-ui
- Demo seed: `make seed-demo` or `ANORAK_PASSWORD=xxx python3 scripts/seed-demo-data.py`
- Docs site: stoa-docs/ (Docusaurus 3.9), 20 pages
