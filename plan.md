# Sprint Plan — Countdown Démo 24 Février 2026

## 🎯 KPIs Démo
| Métrique | Cible | Status |
|----------|-------|--------|
| Consumer flow E2E | Portal→Subscribe→Token→Call | ✅ CAB-1121 (PR #423 + E2E #450) |
| mTLS use case client | 100+ certs, RFC 8705 | ✅ CAB-864 + CAB-872 (PR #453) |
| OpenAPI→MCP bridge | stoactl bridge demo | ✅ CAB-1137 (stoactl PR #6, stoa PR #436) |
| Error Snapshot | Provoquer + investiguer en live | ✅ CAB-550 (PR #448) |
| Dry run 2x sans bug | 5 min chrono | 🟡 CAB-802 (script done PR #456, rehearsals pending) |
| Plan SI post-démo | Arbre décision + roadmap | ✅ CAB-1031 |
| Docs site | Complet, 0 placeholder | ✅ DONE |

## Semaine 7 (13-16 fév) — CODE CRITIQUE
Focus: Finir les 2 gros MEGAs code

- [x] CAB-1121: Consumer Onboarding & Token Exchange (35 pts) — DONE (PR #423 + E2E PR #450)
- [x] CAB-1137: OpenAPI → MCP Auto-Bridge (8 pts) — DONE (stoactl PR #6, stoa PR #436)

- [~] CAB-864: mTLS + OAuth2 Certificate Binding (34 pts)
  - ✅ Session 1: Certificate management API + Keycloak cert-bound tokens (already implemented)
  - ✅ Session 2: F5/Gateway integration + rotation automatique (already implemented)
  - ✅ Session 3: Demo scenario scripts (generate-mtls-certs.sh, seed-mtls-demo.py, mtls-demo-commands.sh, DEMO-SCRIPT Act 3b, seed-all.sh integration) — Done 13/02
  - ✅ Session 4: Phase 2 Self-Service (13/02) — 4 micro-PRs #426-#429 merged:
    - PR #426: Console Consumers page (table, search, RBAC, mobile)
    - PR #427: Portal CertificateUploader → SubscribeModal wiring
    - PR #428: Gateway mTLS Prometheus metrics (3 counters/gauges)
    - PR #429: Grafana mTLS dashboard (7 panels) + 3 alerting rules
  - [x] Session 5: E2E validation script + @wip tags (→ CAB-872, PR #453)

## Semaine 8 (17-21 fév) — POLISH + DRY RUN
Focus: Intégration, script démo, répétitions

- [x] CAB-1031: Plan d'Action SI Post-Démo (21 pts) — Done 13/02
  - ✅ Arbre de décision (3 gates: J+7 Design Partner, J+30 Community, J+90 Revenue)
  - ✅ 3 scénarios: Go Full (roadmap Q2-Q4), Pivot Lean (3 options), Stop/Park
  - ✅ Budget progressif (3.7K→8.7K→15.7K EUR/mois) + onboarding Cédric
  - ✅ Council 8.5/10 — 3 adjustments applied
  - Document: stoa-strategy/execution/PLAN-ACTION-SI-POST-DEMO.md (private)

- [x] CAB-550: Error Snapshot Scenario (3 pts) — DONE (PR #448)

- [x] CAB-872: mTLS Integration E2E (3 pts) — DONE (PR #453)
  - validate-mtls-flow.sh: automated pre-flight (token + cnf + 3 scenarios)
  - mtls-demo-commands.sh --validate flag
  - DEMO-SCRIPT.md updated with mTLS pre-flight step

- [~] CAB-802: Dry Run + Script + Video (3 pts)
  - ✅ demo-dry-run.sh rewritten: 8 acts, 23 checks, GO/NO-GO (PR #456)
  - ✅ 7 production fixes: 23/23 PASS, GO in 3.5s (PR #463)
  - [ ] Répétition #1 (mercredi 19) — timer 5 min
  - [ ] Répétition #2 (vendredi 21) — avec Cédric comme témoin
  - [ ] Video backup filmée

## Dimanche 23 fév — FREEZE
- [ ] CAB-1075: Demo Day Ready (5 pts)
  - Code freeze 18h
  - Full E2E suite → 100% PASS
  - Infra health check (Vault, Keycloak, DB, Grafana)
  - Plan B (video) et Plan C (slides statiques) prêts

## Mardi 24 fév — DÉMO 🎯
- 5 min démo live
- Présentation "ESB is Dead"
- Plan d'Action SI distribué

## Post-démo (semaine 9+)
- [~] CAB-1066: Landing + Pricing refonte (21 pts) — Phase 1 DONE (stoa-web PR #7: SocialProof, Book a Demo, Privacy Policy)
- [x] CAB-1133: Portal Test Suite (34 pts) — DONE (PR #461, 505 tests, 17 routes × 4 personas)
- [x] CAB-1134: ADR-040 Born GitOps (5 pts) — DONE (stoa-docs PR #17, ADR published)
- [x] CAB-1138: GitOps Operator P1-P5 (21 pts) — DONE (PRs #415, #418, #442-#446, #454, deployed 0.3.0)
- [ ] CAB-1030: Kit onboarding Cédric (privé)
- [ ] CAB-353: Go/No-Go Checklist
- [x] Arena k6 Migration L1+L2 (PRs #438, #444, #447, #449) — DONE
- [ ] Arena k6 Migration L3: ramp-up + CI95 error bars + CPU pinning

## Règles Countdown
1. ZERO nouveau ticket jusqu'au 24/02
2. Si bloqué > 1h → contourner, noter, avancer
3. Priorité absolue: CAB-1121 > CAB-864 > CAB-1031 > reste
4. Code freeze dimanche 23 à 18h — AUCUNE EXCEPTION
5. Chaque session Claude Code = 1 sous-tâche d'1 MEGA, pas plus
