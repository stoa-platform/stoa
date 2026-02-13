# STOA Memory

> Dernière MAJ: 2026-02-13

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
CAB-1121: Consumer Onboarding & Token Exchange (35 pts) — MEGA, In Progress
- Identity flow Portal → Keycloak → Gateway
- Token Exchange RFC 8693
- C'est LE flow qu'on démo

CAB-1137: OpenAPI → MCP Auto-Bridge stoactl (8 pts) — In Progress
- stoactl bridge openapi.yaml → MCP tools auto-générés
- Différenciateur critique vs Kong/Gravitee

### P0 — Préparation démo (semaine du 17-23 fév)
CAB-864: mTLS + OAuth2 Certificate Binding 100+ clients (34 pts) — In Progress, due 26/02
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
- 🔴 Reste: E2E test against running stack (CAB-872)

CAB-802: Dry Run + Script + Video Backup (3 pts) — Todo, due 23/02
CAB-550: Error Snapshot Demo Scenario (3 pts) — Todo, due 23/02
CAB-872: mTLS Integration E2E + Script Démo (3 pts) — Todo
CAB-1075: Demo Day Ready — Freeze + Dry Run Témoin + Plan B/C (5 pts) — Backlog

### P0 — Strategy (livrable de la démo, pas prérequis technique)
CAB-1031: Plan d'Action SI Post-Démo — Arbre de Décision (21 pts) — **DONE** (13/02)
- ✅ Document: stoa-strategy/execution/PLAN-ACTION-SI-POST-DEMO.md (684 lignes)
- ✅ 8 sections: Executive Summary, Arbre Decision (3 gates), Roadmap Go/Pivot/Stop, Budget, Onboarding Cedric, KPIs
- ✅ Council Review 8.5/10 Go — 3 adjustments applied: Gate 2 controllable triggers, CIR warning on pivot consulting, realistic star KPIs
- ✅ Pushed to stoa-strategy main (private repo)

## 📋 NEXT (post-démo ou si le temps le permet)

~~Portal mTLS Self-Service~~ — **DONE** (13/02, Phase 2 PRs #426-#429):
- ✅ Console Consumers page (PR #426, ~200 LOC) — table, search, status filter, RBAC, mobile cards
- ✅ Portal cert-to-subscription wiring (PR #427, ~80 LOC) — CertificateUploader in SubscribeModal
- ✅ Gateway mTLS Prometheus metrics (PR #428, ~50 LOC Rust) — validations_total, binding_checks_total, certs_expiring_soon
- ✅ Grafana mTLS dashboard + 3 alerts (PR #429, ~120 LOC) — 7 panels, StoaMtlsHighFailureRate/BindingMismatch/CertsExpiringSoon

CAB-1133: Portal Functional Test Suite 17 routes × 4 personas (34 pts) — In Progress
CAB-1134: ADR-040 Born GitOps Multi-Env (5 pts) — In Progress
CAB-1138: GitOps Reconciliation Operator AWX → K8s (21 pts) — Backlog
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
