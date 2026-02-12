# STOA Memory

> Last updated: 2026-02-12 (Gateway Arena deployed on OVH — PR #374, full pipeline live)

## Active Sprint
- **Goal**: Revenue-ready demo by Feb 24, 2026
- **Branch**: main
- **Focus**: Demo prep (dry-runs, email), remaining tickets
- **Latest**: OVH prod LIVE (12/12 HTTPS). Hetzner staging LIVE (6/6 HTTPS). Portal tests: 427 total (PR #308)

## Session State

| Status | Ticket | Description | Evidence |
|--------|--------|-------------|----------|
| DONE | — | Plan restructure: binary DoD + AI Factory execution | commit c8e74a38 |
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
| DONE | — | Dark mode tools components (ToolCard, UsageChart, QuickStartGuide, ToolSchemaViewer) | PR #286 |
| DONE | D1 | Rust GW basic mode (compile fix + docker-compose) | PRs #242, #244 |
| DONE | D2 | Keycloak federation cross-tenant (5 realms, OpenLDAP) | PR #248, #282 (live demo) |
| DONE | D3 | OpenSearch error snapshots dashboard + seed script | PR #249 |
| DONE | D4 | Gateway metrics dashboard + 9 analytics dashboards | PR #249 |
| DONE | D5 | Master seed orchestration script (seed-all.sh) | PR #249 |
| DONE | D6 | Docker-compose demo final (health checks, nginx routes, check-health.sh) | PR #250 |
| DONE | D7 | Demo script 8-act presentation + pre-flight checklist | PR #257 |
| DONE | D8 | README rewrite for public launch (4100→185 lines) | PR #280 |
| DONE | D10 | Dry-run #2 — 7/8 acts PASS, federation fixed, seed fixed | PR #284 |
| DONE | D11 | From-scratch validation — LDAP auto-seed, Keycloak SSL, 7/7+9/9 | PRs #287, #288 |
| DONE | R1 | MCP v1 REST endpoints + API-to-Tool bridge (Act 7) | PR #290 |
| DONE | R1-fix | API bridge: internal endpoint + docker-compose local build | PR #291 |
| DONE | — | OpSec: dual-repo setup (stoa-strategy private), .gitignore enhanced, plan.md sanitized | commit aa629732 |
| DONE | — | Fix /apis crash: CelebrationProvider missing in App.tsx | PR #293 |
| DONE | — | Fix Grafana SSO: add stoa-observability Keycloak client + role mapping | PR #295 |
| DONE | — | Demo Phase 1-2: Email + Script + Slides + Staging + MOU (5 livrables, français, Q1/Q2 resolved) | stoa-strategy 2bf8dbf |
| DONE | — | Native Platform Metrics dashboard (replace Grafana iframe on /observability) | PR #299 |
| DONE | — | Native Request Explorer dashboard (replace OpenSearch iframe on /logs) | PR #300 |
| DONE | — | Docker-compose Console local build + Grafana auto-login + state files | PR #301 |
| DONE | CAB-1133 | Portal Functional Test Suite — 164 tests, 13 pages × 4 personas | PR #308 |
| DONE | — | Email Capture Phase 1 — Portal login redesign + access_requests endpoint + Alembic 023 | PRs #351, #354, #356, #361 |
| DONE | CAB-911 | Admin Prospects Dashboard — conversion cockpit (API + Console UI, 11 tests) | commit f60b79fa |
| DONE | — | Website Analysis + Content Roadmap — 4 docs (1483 lines), 3 segments, 24 content pieces | untracked in docs/ |
| DONE | — | Hardware Requirements + Perf Benchmarks + Blog — hey benchmark script, 2 reference pages, 1 blog post | stoa PR #370, stoa-docs PR #29 |
| DONE | — | Gateway Arena deployed on OVH — ServiceMonitor + deploy script + Grafana dashboard imported | PR #374, CronJob every 30m |
| IN PROGRESS | ADR-040 | Born GitOps: Multi-Environment Promotion Architecture | stoa-docs ADR |
| IN PROGRESS | — | Email Capture Phase 2 — Stripe-inspired conversion funnel (content expansion, pricing, community) | docs/CONTENT-ROADMAP.md |
| NEXT | CAB-1130 | Email Khalil (send 14 fev EOD, wait feedback 15-16 fev) | — |
| NEXT | CAB-1131 | Dry-runs 3x (18-23 fev, chrono < 5min) | — |
| NEXT | CAB-1066 | Landing gostoa.dev + Stripe (stoa-web) | — |
| NEXT | CAB-1035 | Persona Alex Test (manual) | — |

## CI Pipeline Status (2026-02-11) — ALL GREEN THROUGH DEPLOY

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
- 2026-02-10: Replace iframe embeds (Grafana, OpenSearch) with native React dashboards querying Prometheus
- 2026-02-10: Docker-compose Console switched to local build (always latest code)
- 2026-02-11: Portal test helpers pattern — shared `test/helpers.tsx` with persona factories, mock data factories, `renderWithProviders` wrapper
- 2026-02-11: ADR-040 Born GitOps — Console multi-env, Git=Control Plane, UAC as promotion unit, directory-per-env
- 2026-02-11: Email capture Phase 1 — two-panel Portal login (request access + SSO), public endpoint, Alembic 023
- 2026-02-11: Website analysis (4 docs) — 3 audience gaps (freelancers, SMBs, security), 24 content pieces planned, ~€5K budget for €68-150K ROI
- 2026-02-12: Hardware/perf docs OpSec review — no production topology, no exact costs, no provider mapping in public docs (generic profiles only)
- 2026-02-12: Gateway Arena deployed on OVH — CronJob→Pushgateway→Prometheus→Grafana, first leaderboard: STOA 58.45, Kong 56.58, Gravitee 53.05

## Known Issues
- E2E smoke tests fail on live infra (timeouts, missing UI elements)
- Dependency Review fails: GitHub Advanced Security not enabled
- Container Scan / CodeQL: intermittent failures, non-blocking
- DCO Check: fails on squash-merged commits (expected, non-blocking)
- `strict: true` branch protection: PR must be up-to-date before merge (see MEMORY.md for workaround)
- control-plane-api still OutOfSync in ArgoCD (drift)
- mcp-gateway Degraded in ArgoCD (residual from selector fix)

## Security / OpSec (2026-02-10)
- **Dual-repo**: stoa (public) + PotoMitan/stoa-strategy (private, GitHub)
- **Private repo**: client mapping, pricing, legal, demo scripts, sensitive prompts
- **.gitignore**: 72 patterns added (strategy, clients, pricing, slides, legal, prompts/*.txt)
- **plan.md**: sanitized (no client names), full version in stoa-strategy
- **Sensitive prompts**: moved from .claude/prompts/*.txt to stoa-strategy
- **Legal templates**: OK public (use [COMPANY_NAME] placeholders)

## Notes
- Demo: mardi 24 fevrier 2026
- Presentation "ESB is Dead" same day
- Stack = Python (not Node)
- Console tenants: "oasis", "oasis-gunters"
- Portal OIDC client: stoa-portal; Console OIDC client: control-plane-ui
- Demo seed: `./scripts/demo/seed-all.sh` (master orchestrator) or individual scripts
- Demo sprint: D1-D11 COMPLETE (PRs #242-#288), R1: MCP REST endpoints (PRs #290, #291)
- D11 from-scratch: `down -v` → `up -d` → `seed-all.sh` = 7/7 PASS + 9/9 federation
- R1 validated: Act 7 works end-to-end (15 tools: 3 API + 12 native, invoke proxies to httpbin)
- R1: GET /mcp/v1/tools + POST /mcp/v1/tools/invoke + api_bridge catalog discovery
- Fixes: LDAP auto-seed (PR #287), Keycloak SSL auto-disable (PR #288), DEMO-SCRIPT.md updated
- Fix: /apis page crash — CelebrationProvider added to App.tsx (PR #293)
- EKS Console status: /apis ✅, /observability ✅ native (PR #299), /logs ✅ native (PR #300) — no Grafana/OpenSearch needed
- Docker-compose: Console builds from source (PR #301), Prometheus proxy at /prometheus/, Grafana OIDC auto-login
- Prometheus scrape: gateway UP (only stoa_rate_limit_buckets metric), CP API DOWN (no /metrics). HTTP request counters not yet instrumented.
- Act 7 MCP: KNOWN limitation (Rust GW, fallback in demo script)
- Console dark mode: 100% coverage (last 4 tools components fixed in PR #286)
- Docs site: stoa-docs/ (Docusaurus 3.9), 20 pages
- Vault v1.20.4 running, unsealed. ESO not yet deployed.
- Portal test suite: 427 tests (37 files), 164 new in PR #308. 13 pages × 4 personas. Shared helpers at `portal/src/test/helpers.tsx`.
- Not yet tested: APITestingSandbox, ApplicationDetail, Navigation routing (Phase 3 of CAB-1133)
