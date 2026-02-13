# Sprint Plan — Countdown Démo 24 Février 2026

## 🎯 KPIs Démo
| Métrique | Cible | Status |
|----------|-------|--------|
| Consumer flow E2E | Portal→Subscribe→Token→Call | 🔴 CAB-1121 |
| mTLS use case client | 100+ certs, RFC 8705 | 🔴 CAB-864 |
| OpenAPI→MCP bridge | stoactl bridge demo | 🟡 CAB-1137 |
| Error Snapshot | Provoquer + investiguer en live | 🔴 CAB-550 |
| Dry run 2x sans bug | 5 min chrono | 🔴 CAB-802 |
| Plan SI post-démo | Arbre décision + roadmap | 🔴 CAB-1031 |
| Docs site | Complet, 0 placeholder | ✅ DONE |

## Semaine 7 (13-16 fév) — CODE CRITIQUE
Focus: Finir les 2 gros MEGAs code

- [ ] CAB-1121: Consumer Onboarding & Token Exchange (35 pts)
  - Session 1: Identity model + Keycloak clients + DB schema
  - Session 2: Portal UI consumer registration + approval flow
  - Session 3: Token Exchange endpoint + gateway enforcement
  - Session 4: E2E test Portal→Subscribe→Token→API call
  ⚠️ C'est LE parcours démo. Doit être bulletproof.

- [ ] CAB-1137: OpenAPI → MCP Auto-Bridge (8 pts)
  - Session unique: Parser OpenAPI 3.0/3.1 → génère MCP tool definitions
  - Démo: `stoactl bridge petstore.yaml` → 5 tools créés en 3 secondes

- [ ] CAB-864: mTLS + OAuth2 Certificate Binding (34 pts)
  - Session 1: Certificate management API + Keycloak cert-bound tokens
  - Session 2: F5/Gateway integration + rotation automatique
  - Session 3: Bulk onboarding 100+ consumers script
  - Session 4: E2E test cert→token→API avec mTLS enforced

## Semaine 8 (17-21 fév) — POLISH + DRY RUN
Focus: Intégration, script démo, répétitions

- [ ] CAB-1031: Plan d'Action SI Post-Démo (21 pts)
  - Arbre de décision (3 scénarios: Go/Pivot/Stop)
  - Roadmap conditionnelle Q2-Q4
  - Budget et planning équipe élargie (Cédric + indépendants)

- [ ] CAB-550: Error Snapshot Scenario (3 pts)
  - Setup données démo: 3 erreurs pré-générées
  - Script: provoquer timeout → snapshot → investigation dashboard

- [ ] CAB-872: mTLS Integration E2E (3 pts)
  - Assembler les composants CAB-864
  - Flow complet sans friction

- [ ] CAB-802: Dry Run + Script + Video (3 pts)
  - Répétition #1 (mercredi 19) — timer 5 min
  - Répétition #2 (vendredi 21) — avec Cédric comme témoin
  - Video backup filmée

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
- [ ] CAB-1133: Portal Test Suite (34 pts)
- [ ] CAB-1134: ADR-040 Born GitOps (5 pts)
- [ ] CAB-1138: GitOps Operator (21 pts)
- [ ] CAB-1030: Kit onboarding Cédric (privé)
- [ ] CAB-353: Go/No-Go Checklist

## Règles Countdown
1. ZERO nouveau ticket jusqu'au 24/02
2. Si bloqué > 1h → contourner, noter, avancer
3. Priorité absolue: CAB-1121 > CAB-864 > CAB-1031 > reste
4. Code freeze dimanche 23 à 18h — AUCUNE EXCEPTION
5. Chaque session Claude Code = 1 sous-tâche d'1 MEGA, pas plus
