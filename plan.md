# Sprint Plan — STOA Platform

> Source of truth: Linear cycles. Cycles passés + backlog complet → `plan-archive.md`.
> Last sync: 2026-04-15

## Cycle 15 (Apr 6–12) — CURRENT

**Scope**: 894 pts | **Done**: 196 pts (22%) | **In Review**: 392 pts | **Todo**: 192 pts
**Theme**: True GitOps + Observability RBAC + Call-Flow + stoactl CLI

### Done (highlights)
- [x] CAB-2010 True GitOps MEGA (21 pts) — 6 subs
- [x] CAB-2005 AI Factory v4 Phase 1 (21 pts) — PR #2239
- [x] CAB-2009 Observability stack deploy (21 pts)
- [x] CAB-2027 Observability RBAC MEGA (21 pts) — 5 subs
- [x] CAB-2034 Call-Flow pipeline MEGA (21 pts)
- [x] CAB-2020/2021/2022 stoactl Phase 0/1a/1b (18 pts)
- [x] CAB-2017 OpenSearch ArgoCD (5 pts)

### In Review
Voir Linear (queue typiquement ~40 tickets mais drainée à 0 en Phase 1 CAB-2053).

### ✅ Freeze dissous (2026-04-19)
- [x] **CAB-2053** Feature freeze + CLI-first stabilization (21 pts P1) — Phases 0-5 done
  - Phase 6 (close gate 7j CI green) → replanifiée C16 post-démo
  - Phase 7 (ADR-061 controller framework) → replanifiée C16 post-démo
  - Dissolution: freeze non enforcement-able (110 commits hors scope en 8j). Phases restantes dépriorisées vs démo CAB-2088 (28/04) et C15 delivery.

### Priorité active C15 (Apr 13-26)
- Démo wM/Axway 28/04 (ex-CAB-2088, nouveau ticket opé à créer) — bloquant externe
- CAB-2049/2050 (Council S3 infra)
- Hotfixes P0 prod

## Cycle 16 (Apr 13–19) — NEXT

**Theme**: Post-démo — Comité d'archi + Benchmark gateway

- [ ] CAB-2041 Dossier technique instances d'archi (P2)
- [ ] CAB-2042 Présentation comité archi STOA (P2)
- [ ] CAB-2043 Benchmark gateway STOA vs concurrents (P2)
- [~] CAB-2054 Council 8 personas (13 pts) — 3/4 phases merged, P2 ADR-061 stoa-docs PR #151 awaiting review
- [~] CAB-2065 Baseline + Agent Teams canary — Phase 0 done (PR #2362)
- [ ] CAB-2069 Fix TCO fabriqué build-vs-buy article + extend audit script (5 pts, P1) — Council 7.88/10 Fix
- [ ] CAB-2070 Audit SaaS Playbook + migration guides TCO fabrication (13 pts, P2) — Council 7.88/10 Fix, blocked by CAB-2069

## Milestones

| Date | Event |
|------|-------|
| Mar 17 | DEMO DAY ✅ |
| Mi-Mai 2026 | v1.0 GA (CAB-173) |

## Règles

1. Linear is source of truth — plan.md is a view.
2. Si bloqué > 1h → contourner, noter, avancer.
3. 1 sous-tâche par session Claude Code.
4. `/sync-plan` avant et après chaque session.
5. Freeze dissous (2026-04-19) — priorité démo 28/04 + CAB-2049/2050 + hotfixes P0.
