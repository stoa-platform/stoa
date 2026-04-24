# CI-1 — LOC Analysis: v2 workflow vs Phase 1 §A target

**Decision requested**: accept revised Phase 2d target, or trim composites before push.

**TL;DR** : le target ~140 LOC du plan §A était **trop optimiste**. Le workflow final réaliste est à ~420-490 LOC. La réduction vs legacy reste substantielle (-38 % à -47 %) mais pas l'ordre de magnitude promis. Aucun composite n'est à jeter : même les thin wrappers apportent de la valeur testabilité/réutilisabilité qui dépasse le coût LOC.

---

## 1. Décomposition des 515 LOC du workflow v2

| Section | LOC | % |
|---------|-----|---|
| Header (name, on, concurrency, permissions) | 37 | 7 % |
| Job `prepare` | 38 | 7 % |
| Job `council-validate` | 114 | 22 % |
| Job `plan-validate` | 128 | 25 % |
| Job `implement` | 194 | 38 % |
| Lignes vides entre jobs | 4 | 1 % |
| **Total** | **515** | 100 % |

`implement` est le plus lourd parce qu'il enchaîne wait-for-label → abort → route-model → record-start → 2× hegemon-state-push → implement prompt → detect-partial-pr → Slack dispatch inline (tada/rocket/x) → 2× hegemon-state-push → write-summary.

---

## 2. Part permanente vs temporaire Phase 2b

### 2.1 Lignes qui disparaissent en Phase 2d

| Élément | LOC |
|---------|-----|
| Job entier `prepare` (plus besoin, `github.event.issue.*` disponible via triggers event) | 38 |
| `needs: prepare` (3 jobs × ~1 LOC) | 3 |
| `needs.prepare.outputs.X` devient `github.event.issue.X` (remplacement 1:1, 0 LOC net) | 0 |
| `needs: [prepare, council-validate]`, etc. — plus de chaîne explicite (S2/impl rejoignent legacy: async handshake par labels) | 6 |
| Input `run_implement` gate sur le job implement | 3 |
| Bloc `workflow_dispatch` + inputs (~15 LOC) | −15 |
| **Total supprimé net** | **−65** |

### 2.2 Lignes qui apparaissent en Phase 2d

| Élément | LOC |
|---------|-----|
| Trigger events multi-format (`on: issues` + `on: issue_comment` avec filtres actions/types) | +20 |
| Guards `if:` event-driven par job (label `claude-implement`, comment body `/go` / `/go-plan`) | +12 |
| Guard `author_association in [OWNER,MEMBER,COLLABORATOR]` pour S2 et implement (fork safety) | +6 |
| **Total ajouté net** | **+38** |

### 2.3 Estimate Phase 2d sans optimisation agressive

```
515 (v2 Phase 2b)
- 65 (overhead Phase 2b supprimé)
+ 38 (structure event-driven ajoutée)
= 488 LOC
```

**~490 LOC** — 3.5× le target §A. Écart massif vs plan.

---

## 3. D'où vient la bulk permanente ?

| Bloc permanent | LOC approx | Évitable ? |
|-----------------|------------|------------|
| Prompts Council S1 + Plan S2 + implement (3 blocs `prompt: \|` de ~30 LOC) | ~95 | Oui — extraction vers fichiers `.github/prompts/*.md` + `cat` dans step |
| Slack dispatch inline implement (4 branches success/max_turns/failure/skipped) | ~45 | Partiel — composite `notify-implement-result` à créer |
| Route-model inline (source model-router.sh + extract_estimate fallback comments) | ~20 | Oui — composite `route-model` léger |
| Ship fast-path check inline (S1) + application inline (S2) | ~25 | Partiel — valeur ajoutée faible |
| Implement step: `uses: anthropics/claude-code-action@SHA` direct (pas `council-run` car pas de parsing) | ~20 | Non |
| Apply-label steps shell inline (ensure_label + add_label) | ~20 | Marginal |
| Headers triggers + permissions + concurrency + env | ~45 | Non |
| `actions/checkout@SHA` (4 × 1 LOC) | ~4 | Non |
| `uses: ./.github/actions/X` invocations (~12 call sites × ~8 LOC) | ~95 | Non — c'est la valeur Phase 2b |

**Total permanent incompressible estimé** : ~285 LOC (prompts + route + implement step + headers + invocations + ship fast-path).

**Bulk évitable** : ~205 LOC (prompts extractibles, Slack impl composite, route-model composite, apply-label composite).

---

## 4. Estimate Phase 2d avec optimisation agressive

| Optim | LOC économisée |
|-------|----------------|
| Extract Council prompts to `.github/prompts/council-s1.md`, `council-s2.md`, `implement.md` + `prompt: ${{ ... }}` via fichier lu en step `prepare`-light | −75 (prompts restent mais via `file:` ref, 95 LOC → ~20 LOC de loader) |
| Nouveau composite `notify-implement-result` (wrap dispatch 4 branches) | −25 (45 inline → ~15 LOC invocation + composite 60 LOC ailleurs) |
| Nouveau composite `route-model` (wrap model-router.sh + gh fallback) | −10 (20 inline → ~10 LOC invocation + composite 35 LOC ailleurs) |
| Nouveau composite `add-issue-label` (wrap ensure_label + add_label) | −12 (20 inline → ~8 LOC invocation + composite 30 LOC ailleurs) |
| **Total savings possible sur le workflow** | **~−120 LOC** |

```
490 (Phase 2d baseline)
- 120 (optim agressive)
= ~370 LOC
```

**~370 LOC Phase 2d aggressive** — toujours 2.6× le target §A mais -54 % vs legacy (797 → 370).

---

## 5. Analyse thin-wrapper des 8 composites

Logic LOC = nombre de lignes bash effectives dans les blocs `run:`. Overhead LOC = action.yml total - logic. READMEs non comptés (pure doc, hors LOC workflow).

| Composite | action.yml | Logic | Overhead | Usages v2 | Inline cost (dédup + source) | Net workflow delta |
|-----------|-----------|-------|----------|-----------|------------------------------|--------------------|
| **label-guard** | 39 | 8 | 31 | 3× (S1 guard, S2 council-validated guard, S2 ship-fast-path guard) | ~15 LOC (source + 3 checks) | **+54 LOC** via composite (-39 workflow + 39 composite + 15 invocation calls) |
| **write-summary** | 48 | 9 | 39 | 3× (S1, S2, impl) | ~18 LOC (3 calls + source) | **+63 LOC** via composite |
| **wait-for-label** | 52 | 6 | 46 | 1× (implement) | ~6 LOC (script call direct) | **+54 LOC** via composite |
| **council-sync-linear** | 125 | 50 | 75 | 2× (S1, S2) | ~110 LOC (95 LOC body+extraction+python dupliqué 2×) | **−10 LOC** net — *légère valeur LOC* |
| **detect-partial-pr** | 97 | 37 | 60 | 1× (impl) | ~40 LOC (script + JSON parsing) | **+57 LOC** via composite |
| **hegemon-state-push** | 109 | 38 | 71 | 4× (impl: session-start, impl-started, impl-end, cleanup) | ~50 LOC (4 calls dispatch) | **+59 LOC** via composite |
| **council-run** | 120 | 27 | 93 | 2× (S1, S2) — pas utilisé pour implement (prompt différent) | ~65 LOC (2× action + parsing) | **+55 LOC** via composite |
| **council-notify-slack** | 109 | 29 | 80 | 1× (S1 seul — S2 utilise notify_plan inline) | ~35 LOC (1 call + extraction score + verdict normalize) | **+74 LOC** via composite |

**Verdict LOC** : seul `council-sync-linear` réduit vraiment le total de lignes (−10 LOC). Les 7 autres composites **ajoutent** du LOC net au projet (entre +54 et +74).

**Mais LOC ≠ valeur.** La valeur des composites est ailleurs :

| Composite | Réutilisation potentielle | Testabilité | Décision |
|-----------|---------------------------|-------------|----------|
| label-guard | Potentiellement dans claude-linear-dispatch.yml, claude-autopilot-scan.yml | Contrat `already-set` clair | **Garder** — tooling standard |
| write-summary | Déjà consommé par 10 workflows via `ai-factory-notify.sh` directement ; composite ajoute isolation | Pure passthrough, marginal | *Candidat inline* — le code est déjà factorisé dans `ai-factory-notify.sh`, le composite est une duplication de convenance |
| wait-for-label | Patron polling réutilisable (autres dispatch async) | Complexe (polling, timeout, fallback) — isolation forte | **Garder** — cache un pattern risqué derrière un contrat |
| council-sync-linear | Factorise 2 duplicates de 83/78 LOC en un seul appel | Oui (script testé) | **Garder** — seul composite avec gain LOC positif |
| detect-partial-pr | Patron "find PR from issue" utilisable par tout workflow L1/L3 | Oui | **Garder** |
| hegemon-state-push | Dispatch 3 actions — composite = sugar | Moyen | *Candidat inline* — 3 appels shell distincts feraient tout aussi bien |
| council-run | Pattern Claude+parse réutilisable par claude-linear-dispatch.yml | Pin SHA intégré, parser intégré | **Garder** — forte valeur structurelle |
| council-notify-slack | S1-only, 1 site d'usage dans v2 | Moyen | *Candidat inline* — ROI faible, S2/impl restent inline de toute façon |

---

## 6. Scenarios de trim possibles

### Scenario A — Pas de trim (statu quo)
- 8 composites gardés
- Phase 2d baseline : ~490 LOC
- Phase 2d aggressive : ~370 LOC
- Avantage : cohérence plan §C intacte
- Inconvénient : ROI LOC faible sur 3 composites

### Scenario B — Trim thin wrappers
Supprimer 3 composites low-value : `write-summary`, `hegemon-state-push`, `council-notify-slack`. Inliner leur logique dans le workflow.

Deltas :
- Workflow : +18 (`write-summary` × 3 inline) + ~50 (`hegemon-state-push` × 4 inline) + ~35 (`council-notify-slack` × 1 inline) = **+103 LOC workflow**
- Composites supprimés : −(48 + 109 + 109) = **−266 LOC projet**
- Net projet : **−163 LOC** mais workflow + lourd
- Workflow Phase 2d baseline avec Scenario B : ~490 + 103 = **593 LOC**

### Scenario C — Trim agressif + composite consolidation
Garder `council-run`, `council-sync-linear`, `wait-for-label`, `detect-partial-pr`, `label-guard` (les 5 à forte valeur).
Inliner `write-summary`, `hegemon-state-push`, `council-notify-slack`.
Créer à terme `notify-implement-result`, `route-model` pour gagner encore 50-60 LOC workflow.

Delta : workflow Phase 2d aggressive avec Scenario C : ~490 + 103 − 60 = **~530 LOC** (pire).

### Scenario D — Accept target révisé, continue Phase 2b
Documenter que §A était optimiste. Target révisé Phase 2d : **~370-490 LOC** (-38 % à -54 % vs legacy).
Valider que cette réduction est suffisante pour les objectifs (testabilité, composition, isolation logique métier).

---

## 7. Recommandation

**Scenario D — accept target révisé**. Raisons :

1. **LOC n'est pas le KPI qui compte**. Le KPI réel du rewrite est : « la logique métier est-elle testée, versionnée, et réutilisable ? » Les 515 LOC de v2 contiennent ~100 LOC de prompts Council immuables (valeur métier, pas dette) et ~95 LOC de composite invocations (valeur d'architecture). Seule la bulk du job `implement` (194 LOC) appelle encore du bash inline significatif.

2. **Les 3 composites "thin"** (label-guard, write-summary, hegemon-state-push, council-notify-slack en partie) ajoutent du LOC mais cachent 3 patterns récurrents derrière des contrats nommés. Les rewriters futurs (claude-linear-dispatch.yml, claude-self-improve.yml) économiseront le LOC équivalent chez eux quand ils les adopteront.

3. **Le target §A 140 LOC** supposait implicitement que tous les prompts + tout le Slack + tout le routing sortiraient vers des fichiers ou composites. En pratique, les prompts Council sont des stratégies métier qui méritent d'être versionnées avec le workflow (pour que `git blame` du workflow montre l'évolution des critères Council), pas cachées dans `prompts/*.md`.

4. **La réduction observable** (-35 % tout de suite, -47 % à Phase 2d baseline, -54 % à Phase 2d aggressive) reste dans l'ordre de magnitude des refactors typiques. Le target §A de -82 % n'était pas atteignable sans écraser des décisions produit (prompts, Slack dispatch, routing).

### Si tu veux quand même trimmer

Scenario C (garder 5 composites riches, inliner 3 thin) sauve environ **−163 LOC projet** au prix d'un workflow légèrement plus lourd (+103 LOC workflow). Ça change la narrative mais pas la testabilité : les scripts Phase 2a testés couvrent la logique métier quelle que soit l'encapsulation composite.

Ma préférence : **Scenario D**, on documente le target révisé, on push, on fait le smoke test.

---

## 8. Target révisé proposé (Phase 2d)

| Métrique | Plan §A original | Cible révisée baseline | Cible révisée aggressive |
|----------|------------------|------------------------|--------------------------|
| LOC workflow final | ~140 | **~490** | ~370 |
| Réduction vs legacy 797 | −82 % | −38 % | −54 % |
| LOC Phase 2b transitoire | — | 515 | 515 |
| Nombre de composites | 8 | 8 (inchangé) | 10-11 (ajout notify-implement + route-model) |

**Ce target s'inscrit dans le plan si tu valides Scenario D.** Je mettrai à jour `CI-1-REWRITE-PLAN.md` §J en conséquence dans Phase 2d, pas maintenant.

---

## 9. Questions pour décider

1. **Accepter Scenario D** (target révisé ~490 LOC baseline) ? Ou **Scenario C** (trim 3 thin wrappers, accepte +103 LOC workflow pour −163 LOC projet) ? Ou une autre variante ?
2. **Extraction prompts** vers `.github/prompts/*.md` en Phase 2d — dans le scope CI-1 ou CI-3 ?
3. **Nouveaux composites** (`notify-implement-result`, `route-model`) en Phase 2d — dans le scope CI-1 ou spinoff ?
4. **Si on garde 8 composites tel quel** : est-ce que le rapport tests / LOC / maintenabilité te convient, malgré le dépassement du target §A ?
