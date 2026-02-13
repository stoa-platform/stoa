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
CAB-864: mTLS + OAuth2 Certificate Binding 100+ clients (34 pts) — Todo, due 26/02
- Use case client principal
- F5 → RI SAG → webMethods → Backend

CAB-802: Dry Run + Script + Video Backup (3 pts) — Todo, due 23/02
CAB-550: Error Snapshot Demo Scenario (3 pts) — Todo, due 23/02
CAB-872: mTLS Integration E2E + Script Démo (3 pts) — Todo
CAB-1075: Demo Day Ready — Freeze + Dry Run Témoin + Plan B/C (5 pts) — Backlog

### P0 — Strategy (livrable de la démo, pas prérequis technique)
CAB-1031: Plan d'Action SI Post-Démo — Arbre de Décision (21 pts) — Todo

## 📋 NEXT (post-démo ou si le temps le permet)

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
