---
id: decision-2026-05-09-observability-data-visibility
plan_ref: docs/plans/2026-05-09-observability-data-visibility.md
challenger: "ChatGPT (external, non-Claude — HLFH Decision Gate convention)"
verdict: validated
verdict_history:
  - 2026-05-09 v1 challenged (9 amendments A1-A9 + 6 Q answers)
  - 2026-05-09 v2 validated (after E1+E2 micro-corrections)
  - 2026-05-09 v3 addendum (Claude Review Contract section 11 added — operator-side guardrail, no plan content change)
audit_ref: docs/audits/2026-05-09-observability-data-visibility/findings.md
prior_verdict_ref: docs/audits/2026-05-09-observability-data-visibility/challenger-verdict.md
decision_gate_log: "#12 (HLFH Decision Gate)"
---

# Decision — Observability Data Visibility Plan Validation

## Plan reference

`docs/plans/2026-05-09-observability-data-visibility.md` — initial draft 2026-05-09.

## Verdict

**challenged** — pas de transition vers `validated` tant que les 9 amendements ci-dessous ne sont pas intégrés au plan.

Les deux corrections les plus importantes avant validation :

1. **Phase 0 / Phase 5** : ne pas dépendre uniquement de `X-Probe-Id` comme attribut de span. La preuve trace doit s'appuyer sur un mécanisme OTel standard (`traceparent`, `trace_id` extrait des logs gateway, ou recherche par fenêtre + route + service.name) avant de conclure `pipeline_absent`.
2. **Phase 2** : verrouiller `details.synthetic=true` (extension JSONB de la colonne existante) + badge UI visible. Pas de migration de schéma `audit_events` avant ADR Gap 2.

## Strengths retained (not contested)

1. **Le plan respecte le verdict initial archivé** — Gap 3 d'abord, fixtures Phase 2 ne prouvent pas le pipeline, wording 4B-minimal seul, ADR avant migration Gap 2, probe Phase 5 hors seeder, MEGA Phase 6 séparée.
2. **Phase 0 sans code, Phase 1 décision courte** — bonne séparation diag/décision/exécution.
3. **DoD binaire par phase + anti-goal explicite** — empêche la dérive "fixture devient preuve pipeline".
4. **Risk matrix R1–R10 couvre les fausses-pistes** — notamment R10 "operator misreads Phase 2 fixtures comme pipeline marche".

## Amendments required before `validated`

### A1 — Harmoniser le vocabulaire des verdicts Phase 0

Le plan utilise deux formats : `pipeline-live | pipeline-partial | pipeline-absent` (livrables) et `live | partial | absent` (DoD/AC).

**Décision** : verrouiller un seul format **snake_case** : `pipeline_live | pipeline_partial | pipeline_absent`. Appliqué dans : livrables, DoD, AC, risk matrix, Phase 5.

**Raison** : sinon Codex peut livrer un `live` alors que les docs attendent `pipeline_live`, validation devient floue.

### A2 — `X-Probe-Id` ne suffit pas comme preuve de trace

Sauf instrumentation explicite, un header HTTP arbitraire n'est pas forcément enregistré comme attribut OTel. Phase 0 risque de conclure `pipeline_absent` alors que seul le header n'est pas capturé.

**Décision** : la preuve trace de Phase 0 doit utiliser **au moins un** mécanisme OTel-standard parmi :
- injection d'un `traceparent` connu (si gateway accepte) ;
- récupération du `trace_id` depuis logs gateway ou Alloy ;
- recherche par fenêtre temporelle + route + méthode + status + `service.name` ;
- ou explicitement : "si `X-Probe-Id` n'est pas trouvé comme attribut, vérifier d'abord la capture des headers avant de conclure `pipeline_absent`".

**DoD corrigée** : "le probe id **ou un trace id corrélé** a été suivi de bout en bout". Pas "X-Probe-Id retrouvé partout".

`X-Probe-Id` reste utile pour logs applicatifs, audit, requêtes HTTP — pas comme unique preuve trace.

### A3 — Phase 0 n'est pas strictement read-only

La phase émet une requête prod : non destructive si la route est safe, mais peut créer logs, métriques, spans, voire audit events.

**Décision** : remplacer "Rollback : non applicable (read-only)" par :

> Rollback : non applicable côté données métier si la route est idempotente et dédiée ; la sonde crée volontairement de la télémétrie synthetic.

**Précondition à ajouter** : route utilisée = endpoint idempotent / health-like / tenant `demo-probe`, sans effet métier durable.

### A4 — Phase 0 ne livre pas de fix UI

Le risque R0.1 actuel ("Phase 0 livre un fix UI seul") contredit l'anti-goal "ne corrige pas".

**Décision** : reformuler en :

> Si la sonde révèle uniquement une mauvaise fenêtre UI, Phase 0 documente le fix recommandé et ouvre une micro-phase / PR séparée. Phase 0 ne modifie pas le code.

Sinon on casse "Gap 3 d'abord, no code".

### A5 — Phase 2 verrouillée sur `details.synthetic=true` (JSONB), pas migration

Gap 2 interdit toute migration de schéma `audit_events` avant ADR. Le plan hésite encore entre `source=seed` (nouvelle colonne) et `details.synthetic=true` (extension JSONB).

**Décision verrouillée** : **`details.synthetic=true`** sur la colonne JSONB existante. Structure :

```json
{
  "synthetic": true,
  "source": "seed",
  "fixture_batch": "observability-data-visibility-2026-05-09"
}
```

L'API expose un champ calculé : `is_synthetic: true`. Pas de nouvelle colonne avant ADR Gap 2.

Si une colonne dédiée devient souhaitable, elle est traitée avec la migration issue de l'ADR, pas dans Phase 2.

### A6 — Badge synthetic visible dans l'UI, pas seulement API

Le plan dit que l'API peut exposer `is_synthetic` et que le badge UI est "optionnel selon review". La contrainte challenger initiale interdit de mélanger events réels et synthetic sans distinction.

**Décision** : DoD Phase 2 durcie :

- [ ] API expose `is_synthetic=true`.
- [ ] UI `/audit-log` affiche une distinction visible (badge, chip, label, tooltip) pour les events synthetic.

Pas seulement API.

### A7 — Phase 5 scindée en deux sous-probes

Le plan suppose qu'une seule requête gateway prouve audit + Prom + traces. Or `emit_audit_event` est appelé surtout dans les routers control-plane (`apis.py`, `tenants.py`, `users.py`, `deployment_service.py`, `promotion_service.py`), pas par le simple trafic gateway runtime.

**Décision** : scinder Phase 5 :

- **5A — Control-plane audit probe** : exécute une action connue qui appelle `emit_audit_event` sur le control-plane ; vérifie Kafka → consumer → `audit_events` → API.
- **5B — Gateway runtime telemetry probe** : appelle une route gateway idempotente ; vérifie Prometheus + traces.

Si une même action peut prouver les deux, libre au PR de le démontrer, mais le plan ne doit pas l'assumer sans preuve.

### A8 — Phase 5 ne prétend pas être end-to-end si Phase 0 = `pipeline_absent`

Le plan dit que Phase 5 peut documenter `traces: n/a`. Acceptable pour une probe partielle, **pas** pour une "preuve runtime end-to-end".

**Décision** : trois modes Phase 5 selon le verdict Phase 0 :

| Phase 0 verdict | Phase 5 portée |
|---|---|
| `pipeline_live` | audit + Prom + traces visés |
| `pipeline_partial` | hops live testés, autres marqués `blocked by infra` |
| `pipeline_absent` | audit/Prom smoke uniquement ; **MEGA infra Gap 3 obligatoire avant validation trace** |

Évite un faux succès "end-to-end" sans traces.

### A9 — 6 questions ouvertes, pas 8

Le résumé opérateur mentionnait "8 questions ouvertes posées au challenger" alors que le plan n'en contient que 6 (Q8.1–Q8.6). Erreur de comptage côté résumé chat, pas dans le plan lui-même.

**Décision** : pas de modification du plan (le contenu est correct). Note logguée ici pour traçabilité.

## Answers to plan's open questions

### Q8.1 — Staging accueille-t-il les fixtures synthetic ?

**Réponse challenger** : oui seulement si staging sert aux démos ou validation UX. Distinguer deux types de staging :

| Profil | Fixtures Phase 2 |
|---|---|
| `dev` | enabled by default |
| `staging-demo` | enabled by explicit opt-in |
| `staging-prodlike` | disabled |
| `prod` | forbidden |

Ne pas dire simplement "staging oui/non". Le plan doit refléter cette distinction dans Phase 2.

### Q8.2 — `pipeline_absent` déclenche-t-il une MEGA infra ?

**Réponse challenger** : oui.

Si Alloy / Data Prepper / OpenSearch traces ne sont pas déployés ou pas routés, ce n'est plus une tâche applicative. Le plan doit alors s'arrêter après diagnostic pour la partie traces et produire une MEGA infra séparée. Phase 5 peut continuer pour audit/Prom uniquement, pas pour la preuve trace.

### Q8.3 — L'ADR Gap 2 doit-elle recommander ou rester neutre ?

**Réponse challenger** : elle doit **recommander**.

Une ADR neutre qui liste les options sans décision ne ferme pas Gap 2. Elle peut présenter les options mais doit finir par un verdict clair :

- `accepted` : implement `by_actor`
- `rejected` : keep `by_resource` only
- `deferred` : no migration until product/compliance signal X (signal de réouverture obligatoirement nommé)

### Q8.4 — Phase 5 probe : quelle fréquence CI ?

**Réponse challenger** : au départ `workflow_dispatch` only. Quand stable en dev/k3d :

| Environnement | Fréquence |
|---|---|
| `dev`/`k3d` | on demand + optional nightly |
| `staging` | manual before demo/release |
| `prod` | manual operator opt-in only |

Pas de hourly tant que routes, effets de bord et budgets métriques ne sont pas parfaitement maîtrisés.

### Q8.5 — `source=seed` ou `details.synthetic=true` ?

**Réponse challenger** : `details.synthetic=true` + `details.source="seed"` + `details.fixture_batch="observability-data-visibility-2026-05-09"`. Pas de nouvelle colonne avant ADR/migration. Cf A5.

### Q8.6 — Quel signal lance Phase 6 ?

**Réponse challenger** : Phase 6 lancée si **au moins un** des signaux existe :

1. Le produit confirme que `/observability/security` doit couvrir le trafic non-MCP.
2. Un opérateur ou incident montre que l'état actuel masque une absence d'instrumentation.
3. Phase 3 réduit la confusion de wording, mais les opérateurs demandent encore "zéro trip ou aucune évaluation ?".
4. Une revue sécurité exige la preuve `evaluations_total` / `decisions_total`.

Sans ce signal, Phase 6 reste correctement hors batch.

## Severity adjustments per phase

| Phase | Statut challenger |
|---|---|
| Phase 0 | Bonne priorité, mais DoD à durcir autour de `trace_id` et pas seulement `X-Probe-Id`. |
| Phase 1 | OK. |
| Phase 2 | OK si JSONB + prod forbidden + badge UI visible. **Pas OK si migration `source` avant ADR.** |
| Phase 3 | OK. Wording minimal cohérent. |
| Phase 4 | OK. ADR doit avoir un verdict, pas seulement un cadre. |
| Phase 5 | À scinder (5A audit / 5B gateway telemetry), sinon risque de fausse hypothèse. |
| Phase 6 | OK hors scope. |

## Path to `validated`

1. ✅ Verdict challenger initial archivé (ce fichier, v1).
2. ✅ Application des 9 amendements (A1–A9) dans le plan + transition `validation_status: challenged`.
3. ✅ Re-soumission au challenger 2026-05-09.
4. ✅ Re-challenge verdict v2 = `validated` après application des micro-corrections E1+E2 (cf section ci-dessous).
5. ✅ Transition `validation_status: validated`.
6. ⏳ Ouverture exécution Codex phase par phase, sous les gates listés au plan §"Prochaine étape humaine".

## Re-challenge 2026-05-09 v2

Verdict : **validated**, avec deux micro-corrections éditoriales appliquées avant la bascule du frontmatter. Pas de troisième challenge complet demandé.

### Strengths confirmed

Le plan ferme les deux risques bloquants du précédent challenge :

1. **Phase 0 / Phase 5 ne dépendent plus uniquement de `X-Probe-Id`**. Le plan exige une preuve trace via mécanisme OTel-standard : `traceparent`, `trace_id` extrait des logs gateway/Alloy, ou recherche par fenêtre/route/service.name. Le faux négatif "headers HTTP non capturés comme attributs OTel" est documenté.
2. **Phase 2 ne crée plus de migration prématurée**. Le marquage synthetic est verrouillé dans `audit_events.details` JSONB (`synthetic`, `source`, `fixture_batch`), exposé en `is_synthetic` calculé côté API, avec badge UI obligatoire.

La séquence reste alignée avec le verdict initial archivé : Gap 3 d'abord sans code, décision seed-vs-runtime, fixtures audit gated, wording guardrails minimal, ADR by_resource/by_actor, probes runtime séparées (5A/5B), MEGA 4A/4B-full hors batch.

### Micro-corrections éditoriales (E1, E2)

#### E1 — Harmoniser Phase 1 avec Phase 2 : `details.synthetic`, pas `metadata.synthetic`

Phase 1 disait encore `source=seed, metadata.synthetic=true` alors que la décision verrouillée est :

```
details.synthetic = true
details.source = "seed"
details.fixture_batch = "observability-data-visibility-2026-05-09"
```

**Correction appliquée** au plan ligne 151 : Phase 1 reflète maintenant la structure JSONB exacte verrouillée par A5/Q8.5.

#### E2 — Section Rollback : retirer le vieux "read-only" Phase 0

La section 7 "Rollback Strategy" disait encore "Phase 0 : aucun rollback nécessaire (read-only)" alors que le corps de Phase 0 a déjà été corrigé par A3.

**Correction appliquée** au plan ligne 480 : Phase 0 rollback reformulé en "aucun rollback côté données métier si la route est idempotente et dédiée ; la sonde crée volontairement de la télémétrie synthetic (cf A3)".

### Impact

Ces deux edits ne changent ni la stratégie, ni les DoD, ni les dépendances. Ils évitent qu'un reviewer ou Codex relise une formulation contradictoire avec le verdict verrouillé.

## Re-challenge 2026-05-09 v3 — Claude Review Contract addendum

Verdict : addendum opérationnel, pas de changement substantiel au plan.

### Constat challenger

Lecture par rôle :

| Rôle | Clarté avant addendum |
|---|---|
| Codex | Bonne (DoD/AC binaires par phase) |
| Claude | Moyenne (rôle reviewer défini, mais sans grille formelle) |
| Opérateur | Bonne (gates clairs) |

Codex avait suffisamment de matière pour exécuter ; Claude n'avait pas de checklist par phase ni de format de verdict standardisé.

### Action

Ajout d'une **section 11 — Claude Review Contract** au plan, contenant :

- 11.1 Verdict format (`pass | pass_with_minor_notes | blocked | re_challenge_required`).
- 11.2 Checklist commune à toutes les phases.
- 11.3 Liste explicite des choses que Claude ne doit pas faire.
- 11.4 Mini-grilles checks par phase (Phase 0 → Phase 6).
- 11.5 Posture cohérence-check (relecture plan + decision-log + artefacts par phase).

### Vérification reliquats E1/E2

Le challenger a re-mentionné E1 et E2 dans v3, mais la vérification du fichier confirme qu'ils étaient déjà correctement appliqués en v2 :

- E1 : `metadata.synthetic` n'apparaît plus que dans les sections narratives du decision-log qui réfèrent à l'ancienne formulation. Le plan utilise `details.synthetic` partout.
- E2 : section Rollback Phase 0 reformulée en "aucun rollback côté données métier si la route est idempotente et dédiée".

`grep -nE "metadata\.synthetic|aucun rollback nécessaire \(read-only\)" plan` retourne vide. Pas de reliquat à corriger.

### Statut

`validation_status: validated` maintenu. L'addendum est une grille Claude-side qui n'altère ni la stratégie, ni les DoD, ni les dépendances. Pas de re-challenge supplémentaire requis (le challenger a explicité "Je ne demande pas de troisième challenge complet après E1/E2" dans v2 ; v3 est un addendum opérationnel à grain plus fin).

## Operational gates post-validation

Aucune exécution Codex avant `validation_status: validated` — désormais atteint. Gates suivants verrouillés pour l'exécution :

1. Phase 0 d'abord, sans code.
2. Aucune Phase 2 tant que Phase 1 n'a pas fixé le contrat seed-vs-runtime.
3. Aucune migration `audit_events` avant ADR Phase 4.
4. Phase 5B trace seulement selon verdict Phase 0 (`pipeline_absent` ⇒ `blocked_by_infra` + MEGA infra séparée).
5. Chaque PR Codex référence le `plan_ref` et la phase couverte.
6. Claude Code valide la cohérence vs ce plan ; n'écrit pas le code applicatif.
7. Tickets Linear créables phase par phase au moment de l'exécution.
