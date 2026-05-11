---
id: decision-2026-05-11-guardrails-non-mcp-4b-full
plan_ref: docs/plans/2026-05-11-guardrails-non-mcp-4b-full.md
challenger: "ChatGPT (external, non-Claude — HLFH Decision Gate convention)"
verdict: challenged
verdict_history:
  - 2026-05-11 v1 challenged (12 amendments A1-A12 + 6 Q answers + severity matrix; challenger had F1-F5 summary + canonical sources only, not full plan content)
source_plan_ref: docs/plans/2026-05-09-observability-data-visibility.md
source_decision_ref: docs/decisions/2026-05-09-observability-data-visibility.md
decision_gate_log: "#13 (HLFH Decision Gate)"
---

# Decision — Phase 6 Guardrails Non-MCP + 4B-Full Plan Validation

## Plan reference

`docs/plans/2026-05-11-guardrails-non-mcp-4b-full.md` — initial draft 2026-05-11, F1–F5 Drafter-side polish applied same day.

## Round 1 verdict

**challenged** — pas de transition vers `validated` tant que les amendements A1–A12 ne sont pas intégrés au plan.

### Visibility caveat

Le challenger n'a pas eu accès au fichier plan complet, uniquement au résumé F1–F5 et aux sources canoniques (plan + decision-log 2026-05-09, AR-1 plan 2026-05-07 line 63). Round 2 doit être ré-évalué contre le plan complet (branche `codex/phase6-guardrails-full` poussée 2026-05-11, accessible via GitHub raw URL).

### Strengths retained (non contestés)

1. Phase 6 est bien une MEGA séparée, pas une continuation opportuniste du batch observability précédent. Conforme au plan source qui disait Gap 4A + 4B-full sortaient du batch.
2. Les compteurs `evaluations_total` + `decisions_total` sont le bon pivot. Sans compteur d'évaluation, l'UI ne peut pas distinguer honnêtement "aucune évaluation" de "évaluations avec zéro trip".
3. F1 va dans la bonne direction : verrouiller `evaluation_sample_at`, `decision_sample_at` et `stale_data` évite une UI qui transforme l'absence de delta en vérité métier.
4. F2 est sain : legacy removal hors Phase 6, fenêtre de compatibilité conditionnée à smoke prod + observation. Évite de casser les consommateurs silencieux.
5. F3 est nécessaire : le DAG 6.0 → 6.1 → {6.2, 6.3} → 6.4 → 6.5 → 6.6 évite que Codex livre UI/API/smoke dans le désordre.
6. F4 est important : AR-1 reste canonique. Security Posture et Security & Guardrails doivent rester clarifiés, pas fusionnés (AR-1 ligne 63 plan 2026-05-07).
7. F5 est une bonne réponse au risque multi-composants. Phase 6 touche gateway, cp-api, cp-ui, platform/SRE ; matrice d'ownership par phase réduit le risque de PRs orphelines.

## Amendments required before `validated`

### A1 — Définir formellement "guardrail evaluation"

Sans définition, `stoa_guardrails_evaluations_total` peut être incrémenté au mauvais niveau : une fois par requête, une fois par policy, une fois par payload, une fois par outil MCP, ou une fois par middleware.

**Décision verrouillée** :

> A guardrail evaluation is one execution of one guardrail policy against one request context.

Précisions :

- Une requête avec 3 policies évaluées incrémente `evaluations_total` de 3.
- Une policy disabled n'incrémente pas `evaluations_total`.
- Une policy configured-but-not-applicable peut soit ne pas incrémenter, soit incrémenter avec `outcome="not_applicable"` — choix à verrouiller (challenger recommande hors compteur).
- Une erreur d'évaluation incrémente `evaluations_total` et `decisions_total{decision="error"}` si l'évaluation a effectivement démarré.

Sans ce lock, le compteur devient inutilisable pour distinguer `no_evaluations` de `evaluations_zero_trips`.

### A2 — Fermer la taxonomie `decisions_total`

Le résumé mentionne `decisions_total`, mais pas la taxonomie complète.

**Décision verrouillée challenger** :

> `decision ∈ allow | redact | block | error`

- `not_applicable` reste hors compteur, sauf besoin produit explicite.
- `bypass` est dangereux : peut masquer une absence d'évaluation réelle. Si `bypass` existe, doit être documenté comme décision de policy explicite, pas comme fallback technique.
- `rate_limited` peut être modélisé comme `decision=block` pour le `guardrail=rate_limit` plutôt que comme decision séparée.

### A3 — Verrouiller le label set et la cardinalité avant 6.1

Le plan source disait déjà que la cardinalité Prometheus doit être validée avant merge de la MEGA. Phase 6 doit être beaucoup plus concret.

**Locks à ajouter avant toute instrumentation gateway** :

```text
Allowed labels:
- mode: bounded enum
- policy: bounded enum
- decision: bounded enum on decisions_total only
- route: normalized route template, never raw path
- tenant: tenant class / hashed tenant / bounded demo tenant — never arbitrary tenant id unless cardinality review accepts
```

Point critique : `route` ne doit pas être un chemin brut avec IDs, query params ou user input. `tenant` est également risqué si beaucoup de tenants ou environnement multi-client.

**DoD Phase 6.0** :

- Cardinality budget documented.
- Maximum series estimate calculated.
- Route normalization rule documented.
- Label enums listed.
- Reviewer can reject any unbounded label.

### A4 — Séparer `sample_at`, `last_evaluation_at` et `scrape_health`

F1 dit : `evaluation_sample_at` / `decision_sample_at` = `max(timestamp WHERE delta>0)`. Utile, mais insuffisant.

Un compteur avec `delta=0` sur une fenêtre peut signifier : aucune évaluation, scrape sain mais pas de trafic, scrape cassé, requête Prometheus mal filtrée, compteur reset, ou compteur existe mais pas pour ce label set.

Le nom `sample_at` est challengé si sa définition est "dernier delta > 0". Ce n'est pas un sample Prometheus ; c'est le dernier changement observé.

**Amendement verrouillé** :

```text
last_evaluation_delta_at = max(timestamp WHERE increase(evaluations_total[step]) > 0)
last_decision_delta_at = max(timestamp WHERE increase(decisions_total[step]) > 0)
scrape_sample_at = timestamp of latest successful Prometheus sample for the series/query
source_healthy = Prometheus query succeeded AND scrape_sample_at within freshness threshold
```

L'UI doit baser `stale_data` sur `scrape_sample_at` / `source_healthy`, pas seulement sur `delta>0`. Sinon une période calme sans trafic devient "stale".

### A5 — Cap stale threshold range-dependent

Le lock F1 propose `stale_data threshold = max(2×scrape, 5min)` (range ≤1h) ou `range/12` floor 5min (>1h). Pour un range long, `range/12` peut devenir trop permissif. Sur 7 jours, cela donne ~14h. Une UI peut alors afficher comme fraîche une source qui n'a rien scrappé depuis une demi-journée.

**Amendement verrouillé** (option recommandée) :

```text
freshness_threshold =
  if range <= 1h: max(2 * scrape_interval, 5min)
  if 1h < range <= 24h: max(2 * scrape_interval, 10min)
  if range > 24h: max(2 * scrape_interval, 30min)
```

Ou bien garder `range/12` mais avec cap :

```text
min(max(range/12, 5min), 60min)
```

Sans cap, F1 reste trop permissif pour les vues 7d.

### A6 — API contract : états UI dérivés, pas recalculés côté UI

Le plan doit empêcher la UI de réinventer les états à partir de compteurs bruts.

**Lock côté cp-api** :

```ts
{
  state:
    | "metrics_unavailable"
    | "no_evaluations"
    | "evaluations_zero_trips"
    | "trips_observed"
    | "stale_data",
  evaluations_count: number | null,
  decisions_count: number | null,
  trips_count: number | null,
  last_evaluation_delta_at: string | null,
  last_decision_delta_at: string | null,
  scrape_sample_at: string | null,
  source_healthy: boolean,
  stale_reason: string | null
}
```

Le frontend peut afficher, mais ne doit pas décider seul si `null` signifie `no_evaluations`, `metrics_unavailable` ou `stale_data`.

### A7 — Compatibility window : `prometheus_engine_queries_total` ne suffit pas seul

F2 dit que la fenêtre ferme après Phase 6.6 smoke prod archivé + 14 jours sans consumer legacy via `prometheus_engine_queries_total`. C'est bon, mais pas suffisant.

`prometheus_engine_queries_total` peut rater : dashboards Grafana externes, scripts ops, consommateurs API utilisant anciens champs cp-api, bookmarks/exports hors moteur mesuré.

**Amendement verrouillé** :

```text
Compatibility window closes only when:
1. Phase 6.6 smoke prod archived.
2. 14d without legacy cp-api field consumers.
3. 14d without legacy PromQL consumers observed where observable.
4. Release note / migration note published.
5. Legacy removal plan exists separately and names rollback.
```

Legacy removal reste bien hors Phase 6.

### A8 — DAG : clarifier ce que 6.4 attend exactement

F3 dit : `6.0 → 6.1 → {6.2, 6.3} → 6.4 → 6.5 → 6.6` avec "6.4 attend 6.2 specifically, pas 6.3". Je ne peux pas valider ce point sans voir les titres 6.0–6.6.

**Amendement conditionnel verrouillé** :

> Si 6.4 valide uniquement le backend/API contract, alors 6.4 peut attendre 6.2 sans attendre 6.3.
> Si 6.4 valide le comportement utilisateur, les états UI, ou le smoke visible console, alors 6.4 doit attendre 6.2 ET 6.3.

Le plan doit nommer 6.4 de façon non ambiguë. Sinon Codex peut exécuter un smoke "complet" avant que l'UI existe.

### A9 — Phase Ownership : préciser le protocole claim stale

F5 ajoute `.claude/claims/phase-6-X-...json` et règle stale 2h. Bonne idée, mais il faut éviter qu'un claim expire pendant qu'un agent compile/teste.

**Amendement verrouillé** :

```text
- stale 2h = no heartbeat update for 2h, not wall-clock duration of the task.
- Each active owner must refresh claim heartbeat when continuing work.
- Same-component chaining allowed only if previous PR is merged or explicitly abandoned.
- Cross-component chaining requires operator gate or phase owner approval.
```

Sinon deux agents peuvent travailler sur la même phase parce qu'un test long a rendu le claim "stale".

### A10 — Non-MCP coverage : lister les modes inclus et exclus

Le plan doit refuser une formule vague du type "extend to non-MCP".

**Matrice à ajouter** :

| mode | path | guardrail applicable? | evaluations_total emitted? | decisions_total emitted? | reason if no |
|---|---|---|---|---|---|
| mcp | … | … | … | … | … |
| gateway proxy | … | … | … | … | … |
| sidecar | … | … | … | … | … |
| connect | … | … | … | … | … |
| link | … | … | … | … | … |
| health/readiness | … | … | … | … | not user traffic |
| static admin routes | … | … | … | … | not subject to guardrails |
| internal control-plane calls | … | … | … | … | internal trust boundary |

Pour chaque mode exclu, le plan doit dire pourquoi.

### A11 — AR-1 : ajouter un test anti-régression IA

F4 cite AR-1, mais il faut un DoD concret.

**Amendement verrouillé** :

```text
Phase 6 must not change Security Posture IA.
Security Posture remains compliance findings / score / configuration assessment.
Security & Guardrails remains runtime events / guardrail decisions / PII/prompt/content/rate-limit monitoring.
```

Test UI / snapshot :

- `/security-posture` subtitle unchanged.
- `/observability/security` subtitle remains runtime guardrails wording.

Le risque est que la nouvelle richesse guardrails pousse Codex à "fusionner" les pages, alors qu'AR-1 validé a explicitement retenu la clarification, pas la fusion.

### A12 — Phase 6.6 prod smoke : no PII / no real prompt content

Il faut verrouiller le contenu de la smoke.

**Amendement verrouillé** :

```text
- workflow_dispatch only
- operator opt-in explicit
- tenant/route synthetic dédié
- no real PII
- no real customer prompt
- synthetic payloads deterministic and documented
- cleanup / rollback documented
- smoke output archived with UTC timestamp
```

Tester PII/prompt/content guardrails peut facilement pousser Codex à créer des payloads sensibles. Forcer des fixtures synthétiques non sensibles.

## Answers to Q1–Q6

Le challenger n'avait pas accès au plan complet ; les Q answers ci-dessous sont des locks proposés sur les thèmes attendus, à reconcilier avec les Q1–Q6 actuelles du plan en Round 2.

### Q1 — Quelle sémantique pour `stale_data` ?

**Verrouillé proposé** : `stale_data` dépend de la santé du scrape et du dernier sample Prometheus, pas seulement du dernier delta positif. Ajouter un cap maximum au seuil range-dependent, idéalement 60 minutes. Distinguer `scrape_sample_at`, `last_evaluation_delta_at` et `last_decision_delta_at`. Cf A4 + A5.

### Q2 — Quand fermer la fenêtre de compatibilité legacy ?

**Verrouillé proposé** : fermer uniquement après Phase 6.6 smoke prod archivé + 14 jours sans consommateurs legacy observés + release note publiée + plan de suppression séparé. La suppression legacy ne fait jamais partie de Phase 6. Cf A7.

### Q3 — Quel DAG de phases ?

**Verrouillé proposé** : le DAG F3 est acceptable si 6.4 est strictement backend/API. Si 6.4 valide l'expérience UI ou un smoke console complet, 6.4 doit attendre 6.2 et 6.3. Cf A8.

### Q4 — Comment préserver AR-1 ?

**Verrouillé proposé** : Security Posture et Security & Guardrails restent séparés. Phase 6 n'a pas le droit de fusionner IA, navigation ou sous-titres. Ajouter un test anti-régression IA. Cf A11.

### Q5 — Comment gérer l'ownership multi-composants ?

**Verrouillé proposé** : garder la matrice F5, mais définir stale 2h comme absence de heartbeat, pas durée maximale de tâche. Cross-component chaining nécessite gate opérateur ou phase owner. Cf A9.

### Q6 — Quel signal autorise prod smoke / validation finale ?

**Verrouillé proposé** : Phase 6.6 uniquement après dev/staging green, cardinality review validée, API/UI states testés, rollback documenté, operator opt-in explicite, et payloads synthetic sans PII réelle. Cf A12.

## Severity adjustments per phase

| Phase | Sévérité challenger | Commentaire |
|---|---|---|
| 6.0 — Contract / cardinality / semantics | High | Phase la plus importante. Si mal verrouillée, toute la MEGA peut mentir avec de beaux compteurs. |
| 6.1 — Gateway instrumentation | High | Risque cardinalité + double-count + faux coverage non-MCP. |
| 6.2 — cp-api contract | High | Doit produire les états dérivés, pas déléguer la vérité au frontend. |
| 6.3 — cp-ui states | Medium-high | Risque UX : retransformer null en "0" ou mélanger stale/no_evaluations. |
| 6.4 — Validation / smoke pré-prod | Medium-high | Dépend du périmètre exact ; peut devenir high si c'est le premier test de bout en bout. |
| 6.5 — Compatibility / observability | Medium | Important pour ne pas casser les consommateurs, mais moins risqué que l'instrumentation. |
| 6.6 — Prod smoke archive | High | Risque d'effet de bord prod et de payloads sensibles ; doit être opérateur-only. |

Note : la numérotation challenger diffère de celle du plan (challenger n'avait pas le plan complet). À reconcilier en Round 2 : plan a Phases 6.0 validation, 6.1 gateway metrics contract, 6.2 MCP coverage, 6.3 non-MCP observe-only, 6.4 cp-api reader, 6.5 cp-ui rendering, 6.6 runtime smoke.

## Path to `validated`

1. ✅ Verdict challenger v1 archivé (ce fichier).
2. ⏳ Application des 12 amendements (A1–A12) dans le plan + transition `validation_status: draft → challenged`.
3. ⏳ Re-soumission au challenger Round 2 avec **accès au fichier plan complet** (branche `codex/phase6-guardrails-full` sur GitHub, ou paste verbatim).
4. ⏳ Round 2 verdict : `validated` (potentiellement avec E1, E2… micro-corrections) ou `challenged` v2 si défauts structurels persistent.

## Operational gates post-validation (anticipated)

Quand `validation_status: validated` atteint, gates suivants verrouillés :

1. **Phase 6.0 d'abord** : contract / cardinality / semantics lockés avant toute instrumentation gateway.
2. **Aucune Phase 6.1 sans 6.0 DoD complet** (cardinality budget documenté).
3. **Aucune Phase 6.5 UI sans 6.4 cp-api shipped** (DAG F3 + A8).
4. **Phase 6.6 prod smoke = operator opt-in only** (A12) — pas de schedule auto.
5. Chaque PR Codex référence ce decision-log + la phase couverte.
6. Claude Code valide la cohérence vs ce plan ; n'écrit pas le code applicatif (HEG-PAT-022 Drafter ≠ Reviewer-code).
7. Tickets Linear créables phase par phase au moment de l'exécution.
