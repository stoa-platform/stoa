# STOA Memory

> Dernière MAJ: 2026-02-15 (session 11 — CAB-1172 Auto-approve free-tier, PR #534)

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

## 🔴 IN PROGRESS

CAB-802: Dry Run + Script + Video Backup (3 pts)
- ✅ demo-dry-run.sh: 8 acts, 23 checks, GO/NO-GO (PRs #456, #463, #469)
- ✅ Production validated: 23/23 PASS, GO in 5s
- [ ] Répétition #1 (mercredi 19) — timer 5 min
- [ ] Répétition #2 (vendredi 21) — avec Cédric comme témoin
- [ ] Video backup filmée
- Known: API creation requires GitLab → use Console UI; rate limiting not configured; httpbin flaky

## 📋 NEXT — Cycle 8 (Feb 16-22) — 5 Tracks, 160 pts scoped

### Track 1 — Demo Finale (6 pts)
- CAB-1151: Dress Rehearsal (3 pts, P0)
- CAB-710: n8n + STOA "ESB is Dead" demo (3 pts, P1)

### Track 2 — Community Infrastructure (11 pts, P0) — DONE ✅
- ~~CAB-1152~~ + ~~CAB-1182~~ — PR #525 merged
- Remaining for stoa-docs: Algolia DocSearch, Announcement bar (separate repo)

### Track 3 — DX Remediation (14 pts, fixes CAB-1035)
- ~~CAB-1170~~ ✅ (PRs #529+#530), ~~CAB-1172~~ ✅ (PR #534)
- CAB-1171: Quick Start rewrite (3 pts)
- CAB-1173: MCP guide zero kubectl (3 pts)

### Track 4 — Staging V1++ (39 pts)
- CAB-1183: Sidecar Mode P1 ext_authz (8 pts, NEW)
- CAB-1184: Apigee Adapter P1 (5 pts, NEW)
- CAB-1185: Portal Try-It validation (3 pts, NEW)
- CAB-1186: E2E Demo Showcase unskip (3 pts, NEW)
- CAB-1149: Staging Freerun V1++ (13 pts)
- CAB-362: Circuit Breaker (5 pts)
- CAB-709: UAC for LLM (5 pts)

### Track 5 — SEO + Content (16 pts)
- CAB-1187: Blog Batch 7 (8 pts, NEW)
- CAB-1181: Interactive Diagrams MDX (5 pts)
- CAB-1162: SEO Tracking (3 pts)

## 🚫 BLOCKED

(rien)

## 📝 NOTES
- Demo MVP: mardi 24 février 2026
- Présentation "ESB is Dead" même jour
- docs.gostoa.dev = 32 articles, 0 "Coming Soon"
- ADR numbering: stoa-docs owns numbers (001-043). Next: **ADR-044**
- Velocity C7: 436 pts / 32 issues / 22 PRs en 7 jours = 62 pts/jour
- Velocity C8 target: 160 pts (5 tracks parallèles, AI Factory optimized)
- Portal 2FA for cert upload: user requirement from Council — use Keycloak TOTP step-up
- New Linear tickets: CAB-1182 → CAB-1187 (6 tickets created for C8)
