# Sprint Plan — STOA Platform

> Auto-synced with Linear via `/sync-plan`. Source of truth: Linear cycles.
> Last sync: 2026-02-15

## Cycle 7 (Feb 9–15) — CLOSED

**Scope**: 505 pts | **Done**: 505 pts (100%) | **Velocity**: 44 issues closed
**Theme**: Code critique + Polish + AI Factory v2 + Demo Prep + Community Infra

### Done (44 issues)

- [x] CAB-1121: Consumer Onboarding & Token Exchange (35 pts) — PR #423 + E2E PR #450
- [x] CAB-1137: OpenAPI → MCP Auto-Bridge (8 pts) — stoactl PR #6, stoa PR #436
- [x] CAB-864: mTLS + OAuth2 Certificate Binding (34 pts) — PRs #425-#429, #453
- [x] CAB-1031: Plan d'Action SI Post-Demo (21 pts) — stoa-strategy
- [x] CAB-550: Error Snapshot Scenario (3 pts) — PR #448
- [x] CAB-872: mTLS Integration E2E (8 pts) — PR #453
- [x] CAB-1066: Landing + Pricing refonte (21 pts) — stoa-web PRs #5, #6, #7
- [x] CAB-1133: Portal Test Suite (34 pts) — PR #461, 505 tests
- [x] CAB-1134: ADR-040 Born GitOps (5 pts) — stoa-docs PR #17
- [x] CAB-1138: GitOps Operator P1-P6 (21 pts) — PRs #415-#472, deployed 0.3.0
- [x] CAB-1030: Admin Guide & Onboarding Ops Ready (13 pts) — PR #475
- [x] CAB-1169: AI Factory v2 (13 pts) — PRs #474, #476
- [x] CAB-1135: AWS Decommissioning (P2) — OVH+Hetzner live, 92% cost reduction
- [x] CAB-1166: 4-Persona Test Parity (29 pts) — PRs #467, #468
- [x] Arena k6 Migration L1+L2+L3 — PRs #438, #444, #447, #449, #480 (ramp-up + CI95 bars)
- [x] CAB-1035: Persona Alex DX Test (2 pts) — PR #488 (NO-GO, TTFTC=infinite, 4 friction tickets)
- [x] CAB-1174: AI Factory v2 autonomous pipeline (13 pts) — PRs #496-#516
- [x] CAB-1175: Status Page MVP Upptime (8 pts) — stoa-platform/status repo, Council 8.50/10
- [x] CAB-1182: CONTRIBUTING.md + PR/Issue Templates (3 pts) — PR #525
- [x] CAB-1152: Community Infrastructure EPIC (P1) — PR #525
- [x] CAB-710: n8n + STOA AI Gateway Demo "ESB is Dead" (3 pts) — PR #517
- [x] CAB-1150: Preparation Demo 24/02 — narrative + speaker notes (8 pts) — PR #501
- [x] CAB-1129: Demo Script — Design Partner Pitch 5min (5 pts) — PR #506
- [x] CAB-1130: Demo Slides — Design Partner Presentation (8 pts) — PR #509, 10 Marp slides
- [x] CAB-1075: Demo Day Ready — Freeze + Dry Run + Plan B/C (5 pts) — PR #513
- [x] CAB-1148: Staging Freerun — AI Guardrails + Fallback Chain (13 pts) — PR #495
- [x] CAB-707: Guardrails — PII Detection & Prompt Injection (5 pts) — PR #495
- [x] CAB-708: Fallback Chain — Resilience multi-provider (3 pts) — PR #495
- [x] CAB-1145: Smoke test complet parcours demo PROD (P1)
- [x] CAB-1147: Benchmarks Freeze — STOA vs Kong vs Gravitee (P2)
- [x] +14 sub-issues (docs mega PRs, sidebar redesign, kyverno, SEO, sidecar ADR)

---

## Cycle 8 (Feb 16–22) — CURRENT

**Scope**: 86 pts | **Done**: 5 pts (6%) | **Velocity**: 2 issues closed
**Theme**: Demo finale + Staging V1++ + DX Remediation + Community Launch Prep

### Done (2 issues)

- [x] CAB-353: Go/No-Go Checklist 3 Months (5 pts) — PR #482 (9.00/10 → GO)
- [x] CAB-1146: Baseline PROD — Documenter etat de reference avant freeze (P1)

### In Progress

- [~] CAB-802: Dry Run + Script + Video (3 pts, P1)
  - ✅ demo-dry-run.sh rewritten: 8 acts, 23 checks, GO/NO-GO (PR #456)
  - ✅ 7 production fixes: 23/23 PASS, GO in 3.5s (PR #463)
  - ✅ Credential fixes (PR #469)
  - [ ] Repetition #1 (mercredi 19) — timer 5 min
  - [ ] Repetition #2 (vendredi 21) — avec Cedric comme temoin
  - [ ] Video backup filmee

### Todo

- [ ] CAB-1186: [E2E] Unskip Demo Showcase Feature — Automated Demo Validation (3 pts, P1)
- [ ] CAB-1151: Dress Rehearsal — Smoke test final PROD (3 pts, P1)
- [ ] CAB-1183: [Gateway] Sidecar Mode P1 — ext_authz Enforcement Layer (8 pts, P2)
- [ ] CAB-1184: [Adapter] Apigee Gateway Adapter P1 — Google Cloud CRUD (5 pts, P2)
- [ ] CAB-1185: [Portal] Try-It Form Schema Validation (3 pts, P2)
- [ ] CAB-1128: Design Partner Communication — Client A Beta Access (3 pts, P2)
- [ ] CAB-362: GW2-10 Circuit Breaker + Session Management (5 pts, P2)
- [ ] CAB-709: UAC for LLM — Contrats unifies pour backends IA (5 pts, P2)
- [ ] CAB-1149: Staging Freerun — V1++ suite mardi-mercredi (13 pts, P3)
- [ ] CAB-1162: SEO Tracking — Looker Studio + Search Console archive (3 pts, P3)
- [ ] CAB-1187: [SEO] Blog Batch 7 — 5 Articles Week of Feb 17 (8 pts, P3)

### Backlog — DX Remediation (from CAB-1035 friction analysis)

- CAB-1170: [DX] Enable Keycloak self-registration (5 pts, P1) — CRITICAL BLOCKER
- CAB-1171: [DX] Quick Start rewrite — single golden path (3 pts, P2)
- CAB-1172: [DX] Auto-approve free-tier subscriptions (3 pts, P2)
- CAB-1173: [DX] MCP guide for developers — zero kubectl (3 pts, P2)

### Backlog — Community Infrastructure (CAB-1152 sub-tickets)

- CAB-1153: Activer GitHub Discussions (P1)
- CAB-1154: Algolia DocSearch — Soumettre candidature (P1)
- CAB-1156: Labelliser 10 issues "good first issue" (P1)
- CAB-1158: README Badges + Contributors Wall (P1)
- CAB-1155: FUNDING.yml — Activer GitHub Sponsors (P2)
- CAB-1157: Announcement Bar Docusaurus (P2)

### Backlog — Long-term (parked in cycle, not committed)

- CAB-1181: [Docs] Interactive React Diagrams in Docusaurus (5 pts, P2)
- CAB-601: Status Page — superseded by CAB-1175
- CAB-571: Error Snapshot Network/TLS (P2)
- CAB-570: Error Snapshot Backend/NetworkPolicy (P2)
- CAB-392: Community Contrib Value Program (P3)
- CAB-252: STOA Gateway v2 — Linux Native
- CAB-251: Portal Full E2E Testing (P1)
- CAB-153: REST Protocol Binder
- CAB-151: Contract Transformer (OpenAPI/AsyncAPI ↔ UAC)
- CAB-149: Specification UAC v1.0 (R&D)
- CAB-3: Multi-environnement (P1)

---

## Cycle 9 (Feb 23–Mar 1) — NEXT

**Theme**: Post-Demo + Product Roadmap

### Backlog (no committed items yet)

- CAB-572: Portal Workflows — Subscriptions + Certs (P2)
- CAB-435: Owner Role — Strategic Portfolio View (P2)
- CAB-395: Adapter STOA → webMethods — Migration Bridge PoC (P3)
- CAB-158: Documentation R&D CIR

---

## Milestones

| Date | Event | Gate |
|------|-------|------|
| Dim 15 fev | Cycle 7 ends, PROD freeze | CAB-1145 + CAB-1146 ✅ |
| Lun-Mer 16-19 | Staging freerun V1++ | CAB-1149 |
| Jeu-Sam 20-22 | Off — narrative prep + rehearsals | CAB-802 |
| Dim 22 fev | Dress rehearsal | CAB-1151 |
| Mar 24 fev | DEMO DAY | 5 min live + "ESB is Dead" |

## KPIs Demo

| Metrique | Cible | Status |
|----------|-------|--------|
| Consumer flow E2E | Portal→Subscribe→Token→Call | ✅ CAB-1121 |
| mTLS use case client | 100+ certs, RFC 8705 | ✅ CAB-864 + CAB-872 |
| OpenAPI→MCP bridge | stoactl bridge demo | ✅ CAB-1137 |
| Error Snapshot | Provoquer + investiguer en live | ✅ CAB-550 |
| Dry run 2x sans bug | 5 min chrono | 🟡 CAB-802 (script done, rehearsals pending) |
| Plan SI post-demo | Arbre decision + roadmap | ✅ CAB-1031 |
| Docs site | Complet, 0 placeholder | ✅ 107 pts, 6 MEGAs |

## Regles

1. **Linear is source of truth** — plan.md is a view, not the master
2. Si bloque > 1h → contourner, noter, avancer
3. Code freeze PROD dimanche 15 a 18h
4. Staging freerun lundi-mercredi (no PROD changes)
5. Chaque session Claude Code = 1 sous-tache, pas plus
6. `/sync-plan` before and after each session
