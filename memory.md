# STOA Memory

> Dernière MAJ: 2026-02-15 (session 5 — cycle 7 close)

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

## 🔴 IN PROGRESS

CAB-802: Dry Run + Script + Video Backup (3 pts)
- ✅ demo-dry-run.sh: 8 acts, 23 checks, GO/NO-GO (PRs #456, #463, #469)
- ✅ Production validated: 23/23 PASS, GO in 5s
- [ ] Répétition #1 (mercredi 19) — timer 5 min
- [ ] Répétition #2 (vendredi 21) — avec Cédric comme témoin
- [ ] Video backup filmée
- Known: API creation requires GitLab → use Console UI; rate limiting not configured; httpbin flaky

## 📋 NEXT (post-démo)

- CAB-1075: Demo Day Ready — Freeze + Dry Run Témoin + Plan B/C (5 pts)
- CAB-1170: Enable Keycloak self-registration (CRITICAL, 5 pts)
- CAB-1171: Quick Start rewrite — single golden path (3 pts)
- CAB-1172: Auto-approve free-tier subscriptions (3 pts)
- CAB-1173: MCP guide for devs — zero kubectl (3 pts)
- Arena k6 L3 CPU pinning VPS (deferred post-demo)
- SEO adjustments Council: D1 Early Access disclaimer, relecture humaine, endpoints quickstart

## 🚫 BLOCKED

(rien)

## 📝 NOTES
- Demo MVP: mardi 24 février 2026
- Présentation "ESB is Dead" même jour
- docs.gostoa.dev = 32 articles, 0 "Coming Soon", all 10 PLAN-SEO recommended done
- Velocity avec Claude: estimation ÷10, 107 pts docs en 1 soirée
- Portal 2FA for cert upload: user requirement from Council session — use Keycloak TOTP step-up
