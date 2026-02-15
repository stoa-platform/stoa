# STOA Memory

> Dernière MAJ: 2026-02-15

## ✅ DONE (cette semaine)

### Docs v1.0 — COMPLET 107/107 pts
- CAB-1139: MCP Documentation Complete (13 pts) — PR #36
- CAB-1140: Developer Guides: Subscription, Consumer, Keys, Environments (21 pts) — PR #37
- CAB-1141: API & Security References: RBAC, Gateway Admin, Quotas, OAuth (19 pts) — PR #37
- CAB-1142: Admin Guide Phase 1: Installation, Keycloak, Monitoring (13 pts) — PR #39
- CAB-1143: Multi-Gateway Orchestration & Gateway Modes (13 pts) — PR #39
- CAB-1144: P2 Bundle: Admin Phase 2, OpenAPI Ref, Exit Strategy, Cleanup (28 pts) — PR #40

### Infra & Code (semaines précédentes)
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

## 🔴 IN PROGRESS — Chemin critique démo 24/02

### P0 — Code (doit être fini semaine 7-8)
CAB-1121: Consumer Onboarding & Token Exchange (35 pts) — **DONE** (PR #423)
- ✅ RFC 8693 token exchange: CP API endpoint + Portal UI + 19 tests
- ✅ Demo flow: Register → Credentials → Exchange Token → Call API

CAB-1137: OpenAPI → MCP Auto-Bridge stoactl (8 pts) — **DONE** (stoactl PR #6, stoa PR #436)
- ✅ stoactl bridge --apply + --server-name flag + 4 tests
- ✅ DEMO-SCRIPT.md Act 7.1 (bridge demo)

stoa-web PR #6 — CTA → portal.gostoa.dev — **DONE** (merged 2026-02-15)
- ✅ Header, Hero, Pricing, FinalCTA links updated to portal.gostoa.dev

### P0 — Préparation démo (semaine du 17-23 fév)
CAB-864: mTLS + OAuth2 Certificate Binding 100+ clients (34 pts) — **DONE**
- ✅ Gateway mTLS middleware (mtls.rs) — already implemented
- ✅ Control Plane cert management (certificate_utils.py, consumer model, bulk endpoint) — already implemented
- ✅ Keycloak cnf.x5t#S256 binding — already implemented
- ✅ Demo scenario scripts (2026-02-13): generate-mtls-certs.sh, seed-mtls-demo.py, mtls-demo-commands.sh
- ✅ DEMO-SCRIPT.md updated with Act 3b (3 min mTLS demo)
- ✅ seed-all.sh integrated with --skip-mtls flag
- ✅ Council Review 8.5/10 Go — 3 adjustments applied (13/02):
  - openssl version check in generate-mtls-certs.sh
  - Token lifetime verified: 60 min (3600s) — 20x safety margin for 3 min Act 3b
  - DEMO ONLY headers on all 3 scripts + credentials.json output
- ✅ PR #425 merged (13/02) — 6 files, 866 LOC, Ship mode
- ✅ Phase 2 Self-Service (13/02): 4 micro-PRs #426-#429 merged — Console + Portal + Gateway + Grafana (~450 LOC total)
- ✅ CAB-872 E2E validation: PR #453 merged — validate-mtls-flow.sh + --validate flag + @wip tags

CAB-550: Error Snapshot Demo Scenario (3 pts) — **DONE** (PR #448)
- ✅ 3 hero errors, --validate pre-flight, prod validated (53 docs)

Personal Tenant Auto-Provisioning — **DONE** (PR #451)
- ✅ POST /v1/me/tenant: creates free-{username} tenant, KC group, viewer role (idempotent)
- ✅ Portal AuthContext: auto-triggers on null tenant_id, signinSilent refresh
- ✅ Realm JSON: registrationAllowed=true
- ✅ 6 unit tests (happy path, idempotent, sanitization, collision, KC failure, existing tenant)
- Follow-up: TTL cleanup worker, SMTP email verification, welcome email

CAB-802: Dry Run + Script + Video Backup (3 pts) — **Script DONE** (PRs #456, #463, #469)
- ✅ demo-dry-run.sh: 8 acts, 23 checks, GO/NO-GO verdict
- ✅ PR #463: 7 production fixes (arithmetic, KC path, Grafana URL, consumer, gateway 401, mTLS, MCP auth)
- ✅ PR #469: art3mis password fix (demo→samantha2045) + KC admin creds fix (admin/admin→admin/demo)
- ✅ Full Acts 1-8 rehearsal validated on prod (15/02): all endpoints, federation, mTLS, MCP tools
- ✅ Production validated: **23/23 PASS, GO verdict in 5s**
- ✅ Parzival brute force lock cleared on prod KC
- ✅ Acme Corp tenant created on prod (demo prerequisite)
- Remaining: manual rehearsals (Wed 19, Fri 21) + video backup filming
- Known: API creation requires GitLab (decommissioned) → use Console UI; rate limiting not configured; httpbin flaky
CAB-872: mTLS Integration E2E + Script Démo (3 pts) — **DONE** (PR #452)
- ✅ --validate flag on mtls-demo-commands.sh (6-check automated pre-flight)
- ✅ Wire mTLS binding middleware (Stage 3) into gateway router — was dead code
- ✅ Prod validated: ALL 6 CHECKS PASSED (correct cert→200, wrong cert→403, no cert→401)
CAB-1075: Demo Day Ready — Freeze + Dry Run Témoin + Plan B/C (5 pts) — Backlog

### P0 — Strategy (livrable de la démo, pas prérequis technique)
CAB-1031: Plan d'Action SI Post-Démo — Arbre de Décision (21 pts) — **DONE** (13/02)
- ✅ Document: stoa-strategy/execution/PLAN-ACTION-SI-POST-DEMO.md (684 lignes)
- ✅ 8 sections: Executive Summary, Arbre Decision (3 gates), Roadmap Go/Pivot/Stop, Budget, Onboarding Cedric, KPIs
- ✅ Council Review 8.5/10 Go — 3 adjustments applied: Gate 2 controllable triggers, CIR warning on pivot consulting, realistic star KPIs
- ✅ Pushed to stoa-strategy main (private repo)

### Arena k6 Migration — Level 1+2 DONE ✅
- **PR #438** ✅ k6 benchmark.js + run-arena.sh + Dockerfile + CronJob migration
- **PR #444** ✅ Scorer piping fix (run-arena.py stderr/stdout)
- **PR #447** ✅ Grafana dashboard update (stddev panel, k6 annotation)
- **PR #449** ✅ VPS co-location: Pushgateway ingress (basic auth), deploy.sh, systemd timers
- VPS scores: stoa-vps 97.56, kong-vps 96.46, gravitee-vps 96.39
- Pushgateway: `pushgateway.gostoa.dev` (basic auth, letsencrypt-prod)
- Remaining: L3/PR 5 (ramp-up + CI95 error bars in Grafana) — post-demo

## 📋 NEXT (post-démo ou si le temps le permet)

~~Portal mTLS Self-Service~~ — **DONE** (13/02, Phase 2 PRs #426-#429):
- ✅ Console Consumers page (PR #426, ~200 LOC) — table, search, status filter, RBAC, mobile cards
- ✅ Portal cert-to-subscription wiring (PR #427, ~80 LOC) — CertificateUploader in SubscribeModal
- ✅ Gateway mTLS Prometheus metrics (PR #428, ~50 LOC Rust) — validations_total, binding_checks_total, certs_expiring_soon
- ✅ Grafana mTLS dashboard + 3 alerts (PR #429, ~120 LOC) — 7 panels, StoaMtlsHighFailureRate/BindingMismatch/CertsExpiringSoon

CAB-1133: Portal Functional Test Suite 17 routes × 4 personas (34 pts) — **DONE** (PR #461)
- ✅ 505 tests (+66), 12 files, all 17 routes × 4 personas covered
- ✅ Fix: added stoa:admin to cpi-admin scopes in helpers.tsx
- ✅ 4 new test files + 7 migrated to createAuthMock + 1 helper fix
CAB-1134: ADR-040 Born GitOps Multi-Env (5 pts) — **DONE** (stoa-docs PR #17 merged, ADR-040 published, 5 claims sourced)
CAB-1138: GitOps Reconciliation Operator AWX → K8s (21 pts) — **Phase 5 DONE**
- ✅ P1-P4: AWX cleanup, CRD schemas, kopf scaffold, reconcilers, Prometheus metrics (PRs #415, #418, #442, #443, #445, #446)
- ✅ P5: Drift detection timer — PR #454 merged, deployed to staging + prod (image 0.3.0)
  - `@kopf.on.timer()` for GWI health + GWB sync, auto-remediation, 2 drift metrics
  - 55 tests (72.79% coverage)
CAB-1030: Admin Guide Onboarding Ops Cédric (13 pts) — Todo (docs publiques faites, reste kit privé)
CAB-1035: DX Persona Alex test onboarding MCP (2 pts) — Todo
CAB-353: Go/No-Go Checklist 3 Months — Todo

## 🚫 BLOCKED
(rien)

## 📝 NOTES
- Demo MVP: mardi 24 février 2026
- Présentation "ESB is Dead" même jour
- docs.gostoa.dev = complet, 0 "Coming Soon", build green
- Velocity avec Claude: estimation ÷10, 107 pts docs en 1 soirée
- Chemin critique: CAB-1121 (35pts) + CAB-864 (34pts) = 69 pts code en 10 jours
- CAB-864 demo scripts done (13/02): 6 files created/modified, 100 certs tested OK in ~10s
- CAB-864 Council adjustments applied (13/02): openssl check, token lifetime verified, DEMO ONLY headers
- Portal 2FA for cert upload: user requirement from Council session — use Keycloak TOTP step-up (realm-totp.json exists)
