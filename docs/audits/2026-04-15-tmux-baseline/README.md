# Baseline tmux workflow — CAB-2065 Phase 0

**Date**: 2026-04-15
**Author**: Claude (Opus 4.6) + Christophe
**Ticket**: CAB-2065 Phase 0
**Purpose**: Indicatif baseline (pas contrôlé) avant migration Agent Teams natif (Phase 1)

## Scope

Extraire cycle-time des 3 derniers MEGAs exécutés via le workflow tmux actuel (7 panes, dispatch manuel, branches manuelles, file-based claims in `.claude/claims/`).

**Limite méthodologique**: Linear n'expose pas de timestamps granulaires par phase (Audit/Council/Plan/Merge). On utilise `createdAt → completedAt` comme proxy. N=3 (statistiquement faible, acceptable solo founder).

## 3 MEGAs mesurés

| Ticket | Title | Pts | Created | Completed | Duration | Cycle |
|--------|-------|-----|---------|-----------|----------|-------|
| CAB-1869 | Call Flow Dashboard | 21 | 2026-03-17 06:30 | 2026-04-11 22:17 | **~25.7 days** | C14→C15 |
| CAB-2027 | Observability RBAC | 21 | 2026-04-09 11:16 | 2026-04-09 14:29 | **~3h13m** | C15 |
| CAB-1952 | Keycloak scalability | 21 | 2026-04-03 12:42 | 2026-04-03 18:28 | **~5h46m** | C14 |

**Moyenne**: très haute variance (3h → 25 jours). CAB-1869 est un outlier (cross-cycle, multi-PR). CAB-2027/CAB-1952 représentent mieux la vélocité réelle single-session MEGA.

**Médiane utile**: ~5h (single-session MEGA, 21pts, exécution dense)

## Friction points tmux actuels

Observés sur les 3 MEGAs + expérience des 8 dernières semaines:

### 1. File locking artisanal (`mkdir` atomic)
- `.claude/claims/<ID>.json` + `.claude/claims/<ID>-phase-<N>.lock` via `mkdir`
- Marche, mais cleanup stale locks (30s mtime) manuel en cas de crash mid-claim
- Pas de notification cross-pane quand un claim est libéré

### 2. Peer messaging absent
- Les 7 panes ne communiquent pas entre elles
- ORCHESTRE (pane 0) dispatche via `stoa-dispatch` (API Linear) — pas de canal inter-instance
- Un worker bloqué sur dep externe (ex: API down) doit attendre ORCHESTRE qui lit `operations.log`

### 3. Task sync manuel
- `plan.md` est la task list partagée, mais mise à jour manuelle par chaque instance
- `/sync-plan` réconcilie Linear ↔ plan.md mais introduit de la latence (plan.md drift < session)
- Pas de "live task board" visible par toutes les instances

### 4. Branches + worktrees manuels
- `stoa-parallel` crée 5 worktrees (`~/hlfh-repos/stoa-{backend,frontend,auth,mcp,qa}`)
- Chaque instance crée sa branche (`git checkout -b feat/CAB-XXXX-...`) manuellement
- Risque de collision si 2 instances tentent la même branche (git refuse, pas fatal)
- Lifecycle manuel: `stoa-parallel --kill` pour cleanup, `--keep-worktrees` pour debug

### 5. Context reload entre sessions
- Chaque nouvelle session = full reload (memory.md, plan.md, CLAUDE.md via globs)
- Avec 8-persona Council + Hegemon foundation = ~40k tokens de context statique
- Pas de cache cross-session (sauf prompt cache Anthropic 5min TTL)

### 6. Cross-instance reviews
- Un seul reviewer actif (ORCHESTRE) qui appelle subagents séquentiellement
- Pas de parallel lenses réelles (security + tests + perf en //)
- Pattern 1 (sequential) et Pattern 2 (parallel inline via `/parallel-review`) existent mais déclenchés manuellement

## Métriques cibles Phase 1 (kill-criteria)

Rappel du DoD CAB-2065 Phase 1:

| Condition | Seuil rollback |
|-----------|---------------|
| Cycle-time dégradé | > baseline +25% sur 2 MEGAs consécutifs |
| Corruption worktree | 1 occurrence |
| Merge KO imputable Agent Teams | 1 occurrence |
| Fenêtre d'évaluation | 2 semaines max |

**Baseline retenue (médiane utile)**: ~5h pour un MEGA 21pts single-session.
**Seuil +25%**: ~6h15 → si 2 MEGAs consécutifs dépassent, rollback tmux.

## Métrique succès (Council S2 OSS Killer)

> Phase 1 acceptée si **cycle-time -10% OU parité + zéro rollback** sur 2 MEGAs consécutifs.

- Cible "win": < 4h30 sur MEGA 21pts single-session
- Cible "parité acceptable": ≤ 5h avec zero corruption/rollback

## Next

Phase 1 commence après ce baseline:
1. Activer `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`
2. Choisir 1 MEGA simple (21pts, single-component de préférence) comme canary
3. Lead Opus + 3 teammates Sonnet (backend, frontend, test)
4. Valider worktrees natifs (`claude --worktree`)
5. Mapper labels `instance:*` → teammate assignments
6. Mesurer cycle-time vs baseline
7. Documenter deltas dans CLAUDE.md

## Notes

- Format **indicatif**, pas baseline contrôlé (pas de A/B possible en solo founder)
- Variance Linear timestamps incluent les pauses humaines (review, meetings, context switches)
- Les MEGAs single-session (CAB-2027, CAB-1952) sont les plus représentatifs pour comparer Agent Teams
