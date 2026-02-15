# Sprint Plan — STOA Platform

> Auto-synced with Linear via `/sync-plan`. Source of truth: Linear cycles.
> Last sync: 2026-02-15

## Cycle 7 (Feb 9–15) — CURRENT

**Scope**: 445 pts | **Done**: 330+ pts | **Velocity**: ~28 issues closed
**Theme**: Code critique + Polish + AI Factory v2

### In Progress

- [~] CAB-802: Dry Run + Script + Video (3 pts, P1)
  - ✅ demo-dry-run.sh rewritten: 8 acts, 23 checks, GO/NO-GO (PR #456)
  - ✅ 7 production fixes: 23/23 PASS, GO in 3.5s (PR #463)
  - ✅ Credential fixes (PR #469)
  - [ ] Repetition #1 (mercredi 19) — timer 5 min
  - [ ] Repetition #2 (vendredi 21) — avec Cedric comme temoin
  - [ ] Video backup filmee

### Todo

- [ ] CAB-1075: Demo Day Ready — Freeze + Dry Run Temoin + Plan B/C (5 pts, P1)
- [ ] CAB-1145: Smoke test complet parcours demo PROD (3 pts, P1)
- [ ] CAB-1146: Baseline PROD — Documenter etat de reference avant freeze (2 pts, P1)
- [ ] CAB-1147: Benchmarks Freeze — Capturer resultats STOA vs Kong vs Gravitee (2 pts, P2)
- [ ] CAB-1129: Demo Script — Design Partner Pitch 5min (P2)
- [ ] CAB-1128: Design Partner Communication — Client A Beta Access (P2)
- [ ] CAB-1130: Demo Slides — Design Partner Presentation (P2)
- [ ] CAB-1035: Persona Alex — Test manuel onboarding MCP Gateway (2 pts, P2)
- [ ] CAB-362: GW2-10 Circuit Breaker + Session Management (5 pts, P2) — deferred post-demo

### Done (24+ issues)

- [x] CAB-1121: Consumer Onboarding & Token Exchange (35 pts) — PR #423 + E2E PR #450
- [x] CAB-1137: OpenAPI → MCP Auto-Bridge (8 pts) — stoactl PR #6, stoa PR #436
- [x] CAB-864: mTLS + OAuth2 Certificate Binding (34 pts) — PRs #425-#429, #453
- [x] CAB-1031: Plan d'Action SI Post-Demo (21 pts) — stoa-strategy
- [x] CAB-550: Error Snapshot Scenario (3 pts) — PR #448
- [x] CAB-872: mTLS Integration E2E (3 pts) — PR #453
- [x] CAB-1066: Landing + Pricing refonte (21 pts) — stoa-web PRs #5, #6, #7
- [x] CAB-1133: Portal Test Suite (34 pts) — PR #461, 505 tests
- [x] CAB-1134: ADR-040 Born GitOps (5 pts) — stoa-docs PR #17
- [x] CAB-1138: GitOps Operator P1-P6 (21 pts) — PRs #415-#472, deployed 0.3.0
- [x] CAB-1030: Admin Guide & Onboarding Ops Ready (13 pts) — PR #475
- [x] CAB-1169: AI Factory v2 (13 pts) — PRs #474, #476
- [x] CAB-1135: AWS Decommissioning (P2) — OVH+Hetzner live, 92% cost reduction
- [x] CAB-1166: 4-Persona Test Parity (29 pts) — PRs #467, #468
- [x] Arena k6 Migration L1+L2+L3 — PRs #438, #444, #447, #449, #480 (ramp-up + CI95 bars)

---

## Cycle 8 (Feb 15–22) — NEXT

**Theme**: Demo prep, staging freerun, narrative

### Todo

- [ ] CAB-1150: Preparation Demo 24/02 — narrative + speaker notes (P1)
- [ ] CAB-1151: Dress Rehearsal — Smoke test final PROD (P1)
- [ ] CAB-1148: Staging Freerun — Features V1++ lundi (P3)
- [ ] CAB-1149: Staging Freerun — V1++ suite mardi-mercredi (P3)
- [ ] CAB-1162: SEO Tracking — Looker Studio + Search Console archive (3 pts, P3)

### Backlog (parked in cycle, not committed)

- CAB-601: Status Page (P2)
- CAB-571: Error Snapshot Network/TLS (P2)
- CAB-252: Gateway v2 Linux Native
- CAB-392: Community Contrib Value Program
- _+ 8 Duplicate/Canceled items (old UAC/AWX tickets)_

---

## Milestones

| Date | Event | Gate |
|------|-------|------|
| Dim 15 fev | Cycle 7 ends, PROD freeze | CAB-1145 + CAB-1146 |
| Lun-Mer 16-19 | Staging freerun V1++ | CAB-1148 + CAB-1149 |
| Jeu-Sam 20-22 | Off — narrative prep | CAB-1150 |
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
