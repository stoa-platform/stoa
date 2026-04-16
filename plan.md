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

### 🚨 FREEZE Active — Council 8.0/10 Go
- [~] **CAB-2053** Feature freeze + CLI-first stabilization (21 pts P1) — Phase 0-2 done
  - Phase 3 stoactl completeness 100%
  - Phase 4 Schema registry `gostoa.dev/v1beta1`
  - Phase 5 Context pack CLI-first (< 40% context usage)
  - Phase 6 Close gate: 7j CI green + feature sans `src/`
  - Phase 7 ADR-061 controller framework
  - Shadow metric via CAB-2051 REWORK rate < 50% baseline
  - Exceptions: CAB-2049/2050 (Council S3 infra) + hotfixes P0

### Suspendus jusqu'à fin CAB-2053
- CAB-1887 Gateway Dashboard Inconsistencies (21 pts P1-Urgent)
- CAB-1917 Fix API creation + deploy pipeline (21 pts)
- CAB-1930 Deploy Single Path SSE (21 pts)
- CAB-1867 Bus Factor Mitigation (13 pts)
- CAB-1855 Constant real data in prod (21 pts)
- CAB-1795 Unified Secrets Vault (21 pts)
- CAB-1977 Unified observability (21 pts) — 4 subs In Review
- CAB-1989 AI-Verified UI Testing (21 pts) — 6 subs In Review
- CAB-2019 stoactl CLI-First Operations (21 pts) — 3/6 done

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
5. Freeze active: seul CAB-2053 + exceptions.
