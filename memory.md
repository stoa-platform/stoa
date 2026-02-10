# STOA Memory

> Last updated: 2026-02-10 (Demo Sprint D6-D8 complete — PRs #250, #257, #280)

## Active Sprint
- **Goal**: Revenue-ready demo by Feb 24, 2026
- **Branch**: main
- **Focus**: Demo Sprint "ESB is Dead" (24 fev 2026). D1-D9 complete, D10-D11 pending.

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
| DONE | CAB-1113 | Performance Phase 5+6: SQL filtering + DTOs + Cache + Keycloak Boot + Web Vitals | PRs #139, Session 9-10 |
| DONE | CAB-1114 | OpenSearch all 4 phases: Deploy + RGPD + Multi-Tenant OIDC + Console Integration | Sessions 11-14 |
| DONE | CAB-1115 | Console UI Performance Optimization | PR #148, Hotfix PR #150 |
| DONE | CAB-1108 | Iframe Embed Fix — Logs + Grafana (nginx reverse proxy) | PRs #153, #155, #164-167 |
| DONE | — | EKS Deploy Fixes — All 4 components running | PRs #149, #152, #154, #157 |
| DONE | — | AI Factory Setup (5 agents, 2 skills, 14 rules) | Session 16 |
| DONE | CAB-1116 | Test Automation — all 5 phases (Console 257, Portal 236, API 103, E2E 81) | PRs #168-178 |
| DONE | CAB-1103 | Control Plane Agnostique — all 7 phases | PR #184 |
| DONE | CAB-1105 | Kill Python — all 9 phases (222 tests, clippy clean) | PRs #180, #181 |
| DONE | CAB-1109 | GitOps Pipeline — Helm + ArgoCD + CI migration | PRs #188, #193, stoa-infra PR #7 |
| DONE | CAB-1119 | Brand Unification — all 5 phases (493 tests) | PRs #194, #198 |
| DONE | — | PR cleanup: 39 PRs → 0 open | Session 20 |
| DONE | CAB-1120 | Content Compliance (content-reviewer agent + rule) | PR #203 |
| DONE | CAB-1121 | P1 Data Model + CRUD APIs (17 files, 23 tests) | PR #204 |
| DONE | CAB-1121 | P2 Keycloak Integration | PR #208 |
| DONE | CAB-1121 | P3 Gateway Propagation | PR #211 |
| DONE | CAB-1121 | P5 Portal Consumer UI (16 files, 267 tests) | PR #220 |
| DONE | CAB-1122 | Zero Errors — all 6 phases across all components | PR #215 |
| DONE | CAB-362 | Circuit Breaker + Session Management (8 files) | PR #218 |
| DONE | CAB-864 | P1 mTLS Design Doc + ADR-039 | PR #221 |
| DONE | — | Ship/Show/Ask Git Workflow for AI Factory | PR #222 |
| DONE | — | AI Factory modernization + state files refresh | Session 21 |
| DONE | CAB-864 | P2 mTLS Gateway Module (Rust, 870 lines, 299 tests) | PR #224 |
| DONE | CAB-864 | P3 Bulk Onboarding + Registry (Alembic 020) | PR #230 |
| DONE | CAB-1121 | P4 Quota Enforcement (rate limiting, 27 tests) | PR #229 |
| DONE | CAB-1121 | P6 E2E Tests full flow | PR #233 |
| DONE | — | Console dark mode batch 1-4 | PRs #234, #235, #240, #241, #243 |
| DONE | — | Console dark mode batch 5 (External MCP Servers) | PR #246 |
| DONE | — | Console dark mode batch 6 (APIMonitoring + ErrorSnapshots) | PR #247 |
| DONE | — | Console dark mode COMPLETE — all pages verified | All pages have dark: variants |
| DONE | D1 | Rust GW basic mode (compile fix + docker-compose) | PRs #242, #244 |
| DONE | D2 | Keycloak federation cross-tenant (5 realms, OpenLDAP) | PR #248 |
| DONE | D3 | OpenSearch error snapshots dashboard + seed script | PR #249 |
| DONE | D4 | Gateway metrics dashboard + 9 analytics dashboards | PR #249 |
| DONE | D5 | Master seed orchestration script (seed-all.sh) | PR #249 |
| DONE | D6 | Docker-compose demo final (health checks, nginx routes, check-health.sh) | PR #250 |
| DONE | D7 | Demo script 8-act presentation + pre-flight checklist | PR #257 |
| DONE | D8 | README rewrite for public launch (4100→185 lines) | PR #280 |
| NEXT | CAB-1066 | Landing gostoa.dev + Stripe (stoa-web) | — |
| NEXT | CAB-1035 | Persona Alex Test (manual) | — |

## CI Pipeline Status (2026-02-09) — ALL GREEN THROUGH DEPLOY

| Component | CI | Docker | Apply | Deploy | Notes |
|-----------|-----|--------|-------|--------|-------|
| control-plane-ui | GREEN | GREEN | GREEN | GREEN | Coverage + formatting enforced |
| portal | GREEN | GREEN | GREEN | GREEN | Coverage + formatting enforced |
| control-plane-api | GREEN | GREEN | — | GREEN | Coverage 53%, ruff lint |
| stoa-gateway | GREEN | GREEN | GREEN | GREEN | ArgoCD-managed, 267 tests |

## Quality Gates (CAB-1116 Phase 5)
- **Coverage enforced in CI** via `run-coverage: true` in reusable workflow
- **Pre-commit hooks**: lint-staged (eslint + prettier + ruff) via husky
- **Prettier**: blocking in CI via `--if-present`
- **ESLint ratchet**: console-ui max-warnings=93 (down from 100)
- **Python fail_under**: aligned to 53 in pyproject.toml
- **commitlint**: added `e2e` scope

## Decisions This Sprint
- 2026-02-04: Use column refs in SQLAlchemy upsert (not string keys)
- 2026-02-04: E2E auth requires dual OIDC client tokens (portal + console)
- 2026-02-05: ADRs live in stoa-docs, not stoa (ADR-030)
- 2026-02-05: CLAUDE.md hierarchy: root (compact) + .claude/rules/ (modular)
- 2026-02-06: Kyverno policies in Audit mode first, Enforce after validation
- 2026-02-06: ArgoCD ApplicationSet uses goTemplate mode for multi-env
- 2026-02-07: Custom nginx envsubst script — see `.claude/rules/k8s-deploy.md`
- 2026-02-07: `tsconfig.app.json` pattern to exclude test files from Docker builds
- 2026-02-08: ESLint ratchet (93 warnings) — blocks new warnings, allows gradual cleanup
- 2026-02-08: `@wip` tag + `tags: 'not @wip'` for BDD features without steps
- 2026-02-08: Weekly audit cron + smoke tests as post-deploy jobs
- 2026-02-09: Ship/Show/Ask model for AI Factory (PR #222) — Claude determines review level
- 2026-02-09: AI Factory modernization — state files auto-update protocol in ai-workflow.md

## Known Issues
- E2E smoke tests fail on live infra (timeouts, missing UI elements)
- Dependency Review fails: GitHub Advanced Security not enabled
- Container Scan / CodeQL: intermittent failures, non-blocking
- DCO Check: fails on squash-merged commits (expected, non-blocking)
- `strict: true` branch protection: PR must be up-to-date before merge (see MEMORY.md for workaround)
- control-plane-api still OutOfSync in ArgoCD (drift)
- mcp-gateway Degraded in ArgoCD (residual from selector fix)

## Notes
- Demo: mardi 24 fevrier 2026
- Presentation "ESB is Dead" same day
- 2 design partners to close
- Stack = Python (not Node)
- Console tenants: "oasis", "oasis-gunters"
- Portal OIDC client: stoa-portal; Console OIDC client: control-plane-ui
- Demo seed: `./scripts/demo/seed-all.sh` (master orchestrator) or individual scripts
- Demo sprint: D1-D9 done (PRs #242-#280), D10-D11 pending (21-23 fev)
- Docs site: stoa-docs/ (Docusaurus 3.9), 20 pages
- Vault v1.20.4 running, unsealed. ESO not yet deployed.
