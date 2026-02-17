# STOA Memory

> Dernière MAJ: 2026-02-17 (session 20 — CAB-1359 Arena Perf Phase 3 — PR #632)

## ✅ DONE

### Docs v1.0 — COMPLET 107/107 pts
- CAB-1139: MCP Documentation Complete (13 pts) — stoa-docs PR #36
- CAB-1140: Developer Guides (21 pts) — stoa-docs PR #37
- CAB-1141: API & Security References (19 pts) — stoa-docs PR #37
- CAB-1142: Admin Guide Phase 1 (13 pts) — stoa-docs PR #39
- CAB-1143: Multi-Gateway Orchestration & Modes (13 pts) — stoa-docs PR #39
- CAB-1144: P2 Bundle (28 pts) — stoa-docs PR #40

### Code & Infra (semaines précédentes)
- CAB-1099: Rust Gateway World-Class MCP (50 pts)
- CAB-1105: Kill Python Dependency (34 pts)
- CAB-1106: CD Enterprise ArgoCD + AWX + Kyverno (34 pts)
- CAB-1086: Observability Full LGTM Stack (26 pts)
- CAB-1116: Test Automation Strategy (21 pts)
- CAB-1114: OpenSearch Multi-Tenant RGPD (21 pts)
- CAB-1122: Zero 404/500 Audit & Fix (13 pts)
- CAB-1115: Console UI Perf < 1s LCP (13 pts)
- CAB-1113: Responsivité TTI < 1.5s (13 pts)
- CAB-1108: Console Branding Unification (8 pts)
- CAB-1117: Sidecar Deployment VM Docker Compose (8 pts)
- CAB-1074: Demo Script 5 min (8 pts)
- CAB-1073: Demo Flow Bulletproof Portal→Subscribe→Call (8 pts)

### Démo Sprint (semaines 7-8)
- CAB-1121: Consumer Onboarding & Token Exchange (35 pts) — PR #423 + E2E PR #450
- CAB-1137: OpenAPI → MCP Auto-Bridge (8 pts) — stoactl PR #6, stoa PR #436
- CAB-864: mTLS + OAuth2 Certificate Binding (34 pts) — PRs #425-#429, #453
- CAB-550: Error Snapshot Demo (3 pts) — PR #448
- CAB-872: mTLS Integration E2E (3 pts) — PR #453
- CAB-1031: Plan d'Action SI Post-Démo (21 pts) — stoa-strategy (private)
- Personal Tenant Auto-Provisioning — PR #451
- stoa-web PR #6: CTA → portal.gostoa.dev

### Post-démo (terminés)
- CAB-1133: Portal Functional Test Suite (34 pts) — PR #461, 505 tests
- CAB-1134: ADR-040 Born GitOps Multi-Env (5 pts) — stoa-docs PR #17
- CAB-1138: GitOps Operator P1-P5 (21 pts) — PRs #415-#446, #454, deployed 0.3.0
- CAB-1066: Landing + Pricing (34 pts) — stoa-web PRs #5, #6, #7
- Portal mTLS Self-Service — PRs #426-#429
- Arena k6 Migration L1+L2+L3 — PRs #438, #444, #447, #449, #480 (ramp-up + CI95 bars)
- SEO Batch 6: 5 articles (O2, A2, D1, O4, M6) — stoa-docs PR #41, 32 total published
- CAB-1138 Phase 6: Console drift UI — PR #472 (654 LOC, 13 tests)
- CAB-1169: AI Factory v2 — PRs #474, #476 (stop hook, /ci-fix skill, metrics.log, Council 8.00/10)
- CAB-1030: Admin Guide & Onboarding Ops Ready (13 pts) — stoa PR #475, stoa-strategy PR #1
  - Secrets docs rewritten for Infisical (0 Vault refs), 3 Vault runbooks archived
  - ArgoCD + Operator runbooks created, onboarding kit (5 files) for Cédric
- CAB-353: Go/No-Go Checklist 3 Months — PR #482 (9.00/10 → GO verdict)
- CAB-1035: Persona Alex DX Test (2 pts) — PR #488 (NO-GO, TTFTC=infinite, 4 tickets created)
- CAB-1148: AI Guardrails + Fallback Chain (13 pts) — PR #495 (Council 8.25/10, 2 phases, ~485 LOC)
  - CAB-707: PII detection + prompt injection guardrails (regex, URL/UUID allowlist, redact/reject)
  - CAB-708: Multi-provider fallback chain (JSON config, circuit breaker integration, per-provider timeout)
- CAB-1146: Baseline PROD — 16-section snapshot before freeze — PR #484
- CAB-1145: Smoke test PROD — 23/23 GO, Prometheus 21/23 UP — PR #486
- CAB-1147: Benchmarks Freeze — VPS 97.25 vs Kong 94.41, K8s latency tables — PR #491
- CAB-1150: Demo Narrative + Speaker Notes (8 pts) — PR #501 (6-act timing, 10 FAQ, benchmarks, slides outline)
- CAB-1129: Demo Script — Design Partner Pitch 5min (5 pts) — PR #506 (word-for-word, 10 objections, 3 client profiles)
- CAB-1175: Status Page MVP Upptime (8 pts) — stoa-platform/status repo, 7/7 monitors UP, status.gostoa.dev live
- ADR-043: Kafka → MCP Event Bridge Architecture — stoa-docs PRs #42, #43 (CAB-1176)
  - PR #42: initial publication (263 LOC), fixed ADR-007 collision, Related ADRs (005/024/041), compliance
  - PR #43: Value Proposition section (gateway cost reduction via Kafka fan-out, onboarding 5→1 steps), Phase 1 fix 5→8 topic families. Council 8.50/10
  - Linear audit: 7 anomalies fixed on CAB-1176→1181 (labels, descriptions, relations)
- CAB-1075: Demo Day Ready — Freeze + Plan B/C (5 pts) — PR #513
- CAB-1130: Demo Slides — Design Partner Presentation (8 pts) — PR #509
- CAB-1152: Community Infrastructure EPIC (8 pts) — PR #525 (Discussions, FUNDING, badges, 10 good-first-issues)
- CAB-1182: CONTRIBUTING + templates (3 pts) — PR #525 (pre-existing, URLs fixed, legacy .md removed)
- CAB-1172: Auto-approve free-tier subscriptions (3 pts) — PR #534 (Council 8.50/10)
- Security: Password Rotation P0+P1 — PRs #533, #536, #543
  - KC password policy (NIST 800-63B + DORA) applied to staging + prod
  - KC brute-force hardened (5 attempts, 15 min lockout)
  - KC admin rotated (staging + prod), stored in Infisical
  - 7 E2E persona passwords rotated (KC + Infisical + GitHub Secrets)
  - OIDC client secrets: 3 already non-default, 1 public client (no-op)
  - OpenSearch admin rotated (securityadmin.sh + Infisical)
  - Arena VPS token rotated (SSH + Infisical `prod/gateway/arena/ADMIN_API_TOKEN`)
  - `rotate-secrets.sh` fixed for self-hosted Infisical (CLI-first)

### Cycle 8 (Feb 16-22)
- CAB-1185: Portal Try-It Schema Validation (3 pts) — PRs #557+#554 (Council 8.25/10, ajv + per-field errors)
- CAB-1186: E2E Demo Showcase unskip (3 pts) — PR #553 (7 feature files with full step coverage)
- CAB-1171: Quick Start rewrite — single golden path (3 pts) — stoa-docs PR #46
- CAB-1173: MCP guide zero kubectl (3 pts) — stoa-docs PR #46 (Claude.ai, Python, TS)
- CAB-1249: BackendApi + SaasApiKey models+CRUD (13 pts) — PR #545 (encryption, Alembic 025)
- CAB-1250: Gateway BYOK credential proxy (8 pts) — PR #549 (tenant-scoped tools, admin CRUD)
- CAB-1251: Console SaaS Backend APIs + API Keys (10 pts) — PR #550 (30 tests, 4-persona RBAC)
- CAB-1252: E2E SaaS BDD tests (3 pts) — PR #551 (9 scenarios, @wip tagged)
- CAB-1183: Sidecar Mode P1 ext_authz (8 pts) — PR #555 (rate limiter + scope enforcement)
- CAB-1184: Apigee Adapter P1 (5 pts) — PR #556 (8 methods, Google Cloud CRUD, 25 tests)
- CAB-362: Circuit Breaker Retry (5 pts) — PR #558 (retry for 502/503, idempotent methods)
- CAB-1149: Staging Freerun V1++ (13 pts) — meta-ticket, closed (5 sub-PRs merged)
- CAB-1297: DX Developer Experience MEGA (13 pts) — PR #577 (5 READMEs, 4 .env.example, DEVELOPMENT.md, Makefile, Helm chart README)
- CAB-1321: Portal ToS link fix + viewer fallback (3 pts) — PR #561 + stoa-docs PR #47 (Council 7.50/10)
  - Created `docs/legal/terms.md` (Early Access ToS, Apache 2.0, French law)
  - Added Legal sidebar category in stoa-docs
  - Self-registered users default to `viewer` role (Portal + API fallback)
  - Keycloak `default-roles-stoa` updated: `viewer` added to composites
- CAB-1162: SEO Tracking (3 pts) — PR #564 (sitemap verified, 32/32 meta descriptions compliant, SEO-TRACKING.md)
- CAB-1187: Blog Batch 7 (8 pts) — stoa-docs PR #48 (5 articles: A3 MCP tools, O8 circuit breaker, D2 stoactl, A5 rate limiting, D3 Docker Compose)
- CAB-1289: Gateway Test Coverage & Quality (34 pts) — PR #566 (106 new tests, -620 LOC dead code, 12 #[allow] removed, 754 total gateway tests)
- CAB-1181: Interactive Mermaid Diagrams (5 pts) — stoa-docs PRs #52-#55, #57, #58
  - PR #52: 5 ASCII→Mermaid in concept pages (gateway, mcp-gateway, uac, gitops)
  - PR #53: KafkaMCPArchitecture JSX component for ADR-043 (interactive tabs, theme-aware)
  - PR #54: height fix attempt (minHeight — didn't work)
  - PR #55: CSS Grid overlay fix + GatewayModesArchitecture JSX component for ADR-024
  - PR #57: GitOpsArchitecture (ADR-040, 4 tabs) + MigrationArchitecture (ADR-034, 3 tabs) + ADR-001 Mermaid
  - PR #58: ADR-039 (mTLS pipeline), ADR-004 (adapter pattern), ADR-006 (mixin composition) — all Mermaid
  - Total: 4 JSX components + 7 Mermaid conversions across 10 ADRs + 4 concept pages
- CAB-1154: Algolia DocSearch LIVE (1 pt) — stoa-docs PR #49 (`Stoa Blog` index, 7274 entries)
- CAB-1291: API Test Coverage & Quality (34 pts) — PR #576 (142 tests across 14 modules)
- CAB-374: Deployment Lifecycle MEGA (34 pts) — 3 phases across 3 repos
  - CAB-1353: Deployment Lifecycle API (8 pts) — PR #570 (model+repo+service+router+Alembic 026+26 tests)
  - CAB-1354: Deploy Event Notifications (5 pts) — PR #570 (Kafka events + webhook dispatch)
  - CAB-1352: ADR-045 Deployment Lifecycle Architecture (5 pts) — stoa-docs PR #56
  - CAB-1355: Console UI Deployment Dashboard (8 pts) — PR #573 (history table, filters, rollback, RBAC)
  - CAB-1356: stoactl deploy commands (5 pts) — stoactl PR #7 (deploy+rollback+promote+list+events)
  - CAB-1357: E2E BDD Deployment Lifecycle (3 pts) — PR #574 (5 scenarios, @wip tagged)
- CAB-1297: DX Developer Experience — READMEs, .env.example, Onboarding (13 pts) — PR #577 (5 READMEs, 4 .env.examples, DEVELOPMENT.md, Makefile dev targets)
- CAB-1295: Console Test Coverage (21 pts) — PR #590 + PR #592 (24 test files, 959 total tests, ESLint override for test `as any`)
- CAB-1290: Gateway Live-Code Feature Completion (13 pts) — PR #585 (9 TODOs: uptime, resource listing, health checks, stoa_create_api, traceparent)
- CAB-1299: UAC Spec + Protocol Binders + E2E (34 pts) — PRs #581-#591, #595 (7 micro-PRs: schema, admin API, REST binder, MCP binder, OPA, transformer, E2E tests)
- CAB-1291 Phase 2: API Test Coverage (34 pts total) — PR #582 (+386 tests, 59%→72%, threshold 70%)
- CAB-1358: AI Factory H24 Autonomous Activation (8 pts) — PR #589 (7 workflows hardened: kill-switches, continue-on-error, Ask mode for rules, fallback issue creation)
- CAB-1292: API Auth Completion — IAM Sync, Security Fix, RBAC Tests (21 pts) — PRs #594 + #596
  - Phase 2: PR #594 — 20 RBAC tests, 9 JWT tests, legacy audience deprecation warning, 2 pre-existing test fixes
  - Phase 1: PR #596 — 3 KC helpers (remove_user_from_group, delete_tenant_group, get_user_roles), 3 IAM sync TODOs resolved, 20 new tests
  - Coverage: 71.88% (above 70% threshold), 130 auth-related tests total
- CAB-1300: API Runtime Completion — 7 runtime TODOs + MCP visibility RBAC (13 pts) — PR #599
- CAB-1177: Kafka CNS Topic Naming + PII Masking (8 pts) — PR #601
- CAB-1293: K8s Production Hardening — SecurityContext, NetworkPolicy, Rollout (13 pts) — PR #600
- CAB-1359: Arena Performance Optimization — Close the Kong Gap (13 pts) — PRs #626 + #632
  - Phase 1+2: PR #626 — thread-local PRNG, pre-computed security headers, conditional mTLS, TCP backlog 1024, SO_REUSEPORT, connection pre-warming
  - Phase 3: PR #632 — reqwest 0.11→0.12 (hyper 1.0 lock-free pool), socket2 0.5→0.6, type unification (-20 LOC)
  - 826 tests pass, zero clippy warnings. Phase 4: await Arena benchmark results (target ≥85/100)

## 🔴 IN PROGRESS

CAB-802: Dry Run + Script + Video Backup (3 pts)
- ✅ demo-dry-run.sh: 8 acts, 23 checks, GO/NO-GO (PRs #456, #463, #469)
- ✅ Production validated: 23/23 PASS, GO in 5s
- [ ] Répétition #1 (mercredi 19) — timer 5 min
- [ ] Répétition #2 (vendredi 21) — avec Cédric comme témoin
- [ ] Video backup filmée
- Known: API creation requires GitLab → use Console UI; rate limiting not configured; httpbin flaky

## 📋 NEXT — Cycle 8 (Feb 16-22) — 5 Tracks, 339 pts scoped | Done: 423 pts (48 issues)

### Track 1 — Demo Finale (6 pts)
- CAB-1151: Dress Rehearsal (3 pts, P0)
- ~~CAB-710~~ ✅ (C7, PR #517)

### Track 2 — Community Infrastructure (11 pts, P0) — DONE ✅
- ~~CAB-1152~~ + ~~CAB-1182~~ — PR #525 merged
- ~~CAB-1154~~ ✅ Algolia DocSearch LIVE (stoa-docs PR #49), Announcement bar (separate repo)

### Track 3 — DX Remediation (14 pts, fixes CAB-1035) ✅ — ALL DONE
- ~~CAB-1170~~ ✅ (PRs #529+#530), ~~CAB-1172~~ ✅ (PR #534)
- ~~CAB-1171~~ ✅ (stoa-docs PR #46), ~~CAB-1173~~ ✅ (stoa-docs PR #46)

### Track 4 — Staging V1++ (39 pts) ✅ — 24 pts delivered (CAB-709 deferred)
- ~~CAB-1186~~ ✅ (PR #553), ~~CAB-1185~~ ✅ (PRs #557+#554)
- ~~CAB-1183~~ ✅ (PR #555), ~~CAB-1184~~ ✅ (PR #556)
- ~~CAB-362~~ ✅ (PR #558), ~~CAB-1149~~ ✅ (meta-ticket, closed)
- CAB-709: UAC for LLM (5 pts) — DEFERRED (archived, no impl target)

### Track 5 — SEO + Content (16 pts) ✅ — ALL DONE (16/16 pts)
- ~~CAB-1187~~ ✅ (stoa-docs PR #48), ~~CAB-1162~~ ✅ (PR #564)
- ~~CAB-1181~~ ✅ (stoa-docs PRs #52-#58) — 4 JSX components + 7 Mermaid conversions across 10 ADRs

## 🚫 BLOCKED

(rien)

## 📝 NOTES
- Demo MVP: mardi 24 février 2026
- Présentation "ESB is Dead" même jour
- docs.gostoa.dev = 37 articles, 0 "Coming Soon"
- ADR numbering: stoa-docs owns numbers (001-045). Next: **ADR-046**
- Velocity C7: 436 pts / 32 issues / 22 PRs en 7 jours = 62 pts/jour
- Velocity C8 target: 160 pts (5 tracks parallèles, AI Factory optimized)
- Portal 2FA for cert upload: user requirement from Council — use Keycloak TOTP step-up
- New Linear tickets: CAB-1182 → CAB-1187 (6 tickets created for C8)
