---
id: plan-2026-05-09-observability-data-visibility
triggers: [a, c]                       # a: >5h cumulative ; c: irreversible (Gap 2 schema migration)
validation_status: validated           # draft | challenged | validated | rejected
challenge_ref: "docs/decisions/2026-05-09-observability-data-visibility.md"
audit_ref: "docs/audits/2026-05-09-observability-data-visibility/findings.md"
verdict_ref: "docs/audits/2026-05-09-observability-data-visibility/challenger-verdict.md"
---

# Plan — Observability Data Visibility Closure

> Source: `docs/audits/2026-05-09-observability-data-visibility/findings.md` (audit) + `challenger-verdict.md` (verdict initial) + `docs/decisions/2026-05-09-observability-data-visibility.md` (verdict plan + re-challenge).
> Statut : **validated** (amendements A1–A9 intégrés 2026-05-09 ; micro-corrections E1+E2 appliquées 2026-05-09).
> Exécution prévue : phase par phase par Codex, review indépendante par Claude Code, cohérence vs ce plan vérifiée à chaque PR.

## 1. Context

L'audit du 2026-05-09 a établi que l'absence apparente de données dans les surfaces observabilité (`/audit-log`, `/observability/live-calls`, `/observability/security`) **n'est pas un bug du seeder**. C'est un système-de-systèmes où :

- le seeder est catalog-only par design (CAB-1411) ;
- une partie du pipeline runtime n'est pas confirmée déployée en prod (Alloy / Data Prepper / Tempo / OpenSearch traces) ;
- les counters guardrails ne sont émis que depuis le path MCP, donc invisibles pour le trafic non-MCP ;
- les empty states honnêtes du PR train récent (#2730–#2745) sont parfois lus comme "broken" alors qu'ils sont véridiques.

Le challenger a verrouillé six contraintes (cf `challenger-verdict.md`) :

1. Gap 3 cluster diag avec sonde traçable end-to-end avant tout code.
2. Gap 1A est une **fixture**, pas une preuve pipeline. Gated, taggée synthetic.
3. Gap 4B-minimal = wording honnête, sans prétendre distinguer 0 vs absence.
4. Gap 2 passe par **ADR** avant migration, avec matrice d'autorisation cross-tenant.
5. Gap 1B (synthetic traffic) sort du seeder core, vit comme smoke/probe.
6. Gap 4A + 4B-full sont une **MEGA séparée**, hors du batch observability.

Le plan respecte cet ordre et ces gates.

## 2. Goals

Dans l'ordre de priorité :

1. **Localiser précisément où le pipeline traces s'arrête** (Gap 3) avant d'écrire la moindre ligne de code.
2. **Décider explicitement si le seeder doit générer de la donnée runtime** ou rester catalog-only (contrat seed-vs-runtime).
3. **Donner aux démos / staging / dev une histoire d'audit-log riche** sans mentir : fixtures gated et taggées synthetic.
4. **Aligner le wording UI guardrails** avec ce que le backend peut effectivement prouver.
5. **Cadrer le modèle audit `by_resource` vs `by_actor`** par ADR avant toute migration de schéma.
6. **Construire un smoke / probe end-to-end** comme preuve runtime indépendante du seeder.
7. **Découpler l'instrumentation guardrails du chemin MCP** dans une MEGA séparée, avec compteur d'évaluations dédié.

## 3. Non-goals

Hors scope explicite de ce plan :

- ❌ Pas de migration du modèle d'audit (`audit_events` schema) avant ADR Gap 2 validée.
- ❌ Pas de réintroduction de fallbacks synthétiques silencieux en prod (`STOA_AUDIT_DEMO_FALLBACK` reste fail-closed prod).
- ❌ Pas d'extension de l'instrumentation guardrails en dehors du chemin MCP dans ce plan (sortira en MEGA séparée Phase 6).
- ❌ Pas de bascule vers une stack traces alternative (Jaeger, Loki traces, etc.) — Alloy/Data Prepper/Tempo/OpenSearch reste le contrat à confirmer.
- ❌ Pas de compteur Prometheus `evaluations_total` dans la version minimale Gap 4B (réservé à 4B-full / Phase 6).
- ❌ Pas de génération de trafic dans le seeder core (1B vit séparément).

## 4. Phase Execution Sequence

Sept phases. Chaque phase a un livrable atomique, des préconditions explicites, une DoD binaire et un anti-goal (ce que la phase **ne** prouve **pas**).

### Phase 0 — Gap 3 cluster diagnostic with traceable end-to-end probe

**Objectif** : localiser le hop précis où le pipeline traces s'arrête en prod, sans écrire de code applicatif.

**Préconditions** :
- Accès kubectl prod (cluster OVH MKS).
- Token API gateway valide pour émettre une requête tagguée.
- Accès OpenSearch prod (`opensearch.gostoa.dev`).
- **Route utilisée = endpoint idempotent / health-like / tenant `demo-probe`, sans effet métier durable** (A3).

**Livrables** :
1. `docs/audits/2026-05-09-observability-data-visibility/probe-trace-walk.md` — séquence diag exécutée + résultats par hop.
2. Si le pipeline est partiellement déployé : inventaire des composants manquants (Alloy CR, Data Prepper config, OpenSearch index template).
3. Verdict explicite : `pipeline_live` | `pipeline_partial` | `pipeline_absent` (A1 — format snake_case verrouillé).

**Séquence diag (verrouillée par le challenger, durcie A2)** :

```
1. Pod gateway env contains STOA_OTEL_ENDPOINT=http://stoa-alloy-otlp.stoa-monitoring:4317
   kubectl exec -n stoa-system <gateway-pod> -- env | grep STOA_OTEL
2. Service stoa-alloy-otlp exists in stoa-monitoring and accepts OTLP gRPC (4317)
   kubectl -n stoa-monitoring get svc,deploy
   kubectl -n stoa-monitoring describe svc stoa-alloy-otlp
3. Émettre une requête tagguée — DOUBLE preuve (header + traceparent OTel-standard)
   TP="00-$(openssl rand -hex 16)-$(openssl rand -hex 8)-01"     # W3C traceparent
   PID="probe-2026-05-09-$(openssl rand -hex 4)"
   curl -H "X-Probe-Id: $PID" -H "traceparent: $TP" \
        https://api.gostoa.dev/<idempotent-route>
   # Le trace_id W3C est ${TP:3:32}
4. Span visible dans Alloy logs (chercher PAR trace_id, fallback PAR probe_id ou time-window)
   kubectl -n stoa-monitoring logs deploy/stoa-alloy --tail=200 | grep -E "${TP:3:32}|$PID"
   # Si rien : vérifier d'abord si Alloy logge les attributs avant de conclure pipeline_absent.
5. Span écrit dans OpenSearch otel-v1-apm-span-* (chercher PAR trace_id en priorité)
   curl -u <ops>:<key> "https://opensearch.gostoa.dev/otel-v1-apm-span-*/_search?q=traceId:${TP:3:32}"
   # Fallback : recherche par fenêtre temporelle + service.name + http.route + status_code.
   # Fallback header : attributes.X-Probe-Id:$PID (uniquement si capture des headers est confirmée).
6. Trace résolue par /v1/monitoring/transactions
   curl -H "Authorization: Bearer <jwt>" \
        "https://api.gostoa.dev/v1/monitoring/transactions?api_name=<known>&time_range=15"
7. UI time-window check
   /observability/live-calls in browser, time range >= window contenant la requête
```

**Règle A2 verrouillée** : la preuve trace s'appuie sur **au moins un** mécanisme OTel-standard (`traceparent` injecté, `trace_id` extrait des logs gateway/Alloy, ou recherche par fenêtre + route + service.name + status). Si `X-Probe-Id` n'est pas trouvé comme attribut, **vérifier d'abord la capture des headers** avant de conclure `pipeline_absent`. `X-Probe-Id` reste utile pour logs applicatifs / audit / corrélation HTTP — pas comme unique preuve trace.

**Failure modes à enumerer explicitement** (aucune pré-élimination) :
- Exporter OTel non initialisé côté gateway (env présent mais SDK silencieux).
- DNS / NetworkPolicy bloque gateway → alloy.
- Alloy reçoit mais Data Prepper down ou misconfig pipeline.
- OpenSearch index `otel-v1-apm-span-*` absent ou mapping rejette.
- Tempo fallback inactif.
- UI time range ne couvre pas la fenêtre.
- **Headers HTTP non capturés comme attributs OTel** (faux positif `pipeline_absent` si on ne cherche que par `X-Probe-Id`).

**DoD binaire** :
- [ ] `probe-trace-walk.md` existe avec un verdict explicite parmi `pipeline_live | pipeline_partial | pipeline_absent` (A1).
- [ ] Si `pipeline_partial` ou `pipeline_absent` : composants manquants nommés.
- [ ] La preuve trace est **soit** par `trace_id` W3C corrélé, **soit** par recherche par fenêtre/route/service.name (A2). Pas uniquement par `X-Probe-Id` header.
- [ ] Aucun code applicatif modifié.

**Anti-goal** : cette phase **ne** corrige **pas** le pipeline. Elle le diagnostique. **Elle ne livre aucun code, même un fix UI** (A4).

**Risques** :
- R0.1 (A4 corrigé) : si la sonde révèle uniquement une mauvaise fenêtre UI, Phase 0 **documente** le fix recommandé et ouvre une **micro-phase / PR séparée**. Phase 0 ne modifie pas le code.
- R0.2 : sonde émise depuis console n'a pas le bon JWT → préparer creds avant.
- R0.3 (A2) : faux verdict `pipeline_absent` parce que les headers ne sont pas capturés comme attributs OTel. Mitigation : double mécanisme `traceparent` + recherche par fenêtre.

**Rollback** (A3 corrigé) : non applicable côté données métier si la route est idempotente et dédiée ; la sonde crée volontairement de la télémétrie synthetic.

**Effort estimé** : 1–2h (challenger : 1–2h validés).

**Owner candidat** : SRE / platform.

**Dépendances** : aucune. Premier acte du plan.

---

### Phase 1 — Seed-vs-runtime contract decision

**Objectif** : décider noir-sur-blanc si le seeder doit jamais générer de la donnée runtime, ou s'il reste catalog-only et délègue au module `observability_fixtures` séparé.

**Préconditions** :
- Phase 0 complétée (le verdict pipeline informe la décision).

**Livrables** :
1. `docs/decisions/2026-05-09-seed-vs-runtime-contract.md` (decision-log court, ≤ 1 page).
2. Ce decision-log fixe :
   - Le seeder reste **catalog-only** OU le seeder accueille un sous-module `observability_fixtures` clairement séparé.
   - Les marqueurs obligatoires sur toute donnée fixture : `details.synthetic=true`, `details.source="seed"`, `details.fixture_batch="observability-data-visibility-2026-05-09"` (JSONB sur la colonne `audit_events.details` existante, pas de migration — verrouillé par A5/Q8.5).
   - Les profils où ces fixtures sont **autorisées** (`dev`, `staging`) et **interdites** (`prod`).
   - Les contrôles d'accès / variables d'environnement qui empêchent l'activation accidentelle.

**DoD binaire** :
- [ ] Decision-log committé avec un verdict explicite.
- [ ] Decision-log référencé par Phase 2 et Phase 5.

**Anti-goal** : ce decision-log **ne** spécifie **pas** le contenu des fixtures (Phase 2) ni le générateur de trafic (Phase 5). Il fixe la frontière.

**Risques** :
- R1.1 : décision "le seeder reste strictement catalog-only" — Phase 2 doit alors créer un nouveau module séparé (`observability_fixtures/`), légèrement plus d'effort.
- R1.2 : décision "fixtures dans le seeder" — risque accru de fuite prod si gating mal conçu, doit lister contrôles redondants.

**Rollback** : decision-log peut être révisé via nouveau decision-log + ADR si le verrou se révèle inadapté.

**Effort estimé** : 0.5j (rédaction + alignement court).

**Owner candidat** : platform lead.

**Dépendances** : Phase 0.

---

### Phase 2 — Gap 1A: audit-log fixtures (gated + synthetic)

**Objectif** : alimenter `/audit-log` en environnements démo / staging-demo / dev avec des données contrôlées, taggées synthetic, jamais en prod par défaut.

**Préconditions** :
- Phase 1 decision-log validé.

**Fichiers touchés** (estimation, à confirmer après Phase 1) :
- Soit `control-plane-api/scripts/seeder/steps/observability_fixtures.py` (nouveau) si décision "module séparé".
- Soit `control-plane-api/scripts/seeder/steps/audit_events.py` (nouveau) si décision "step seeder".
- `control-plane-api/scripts/seeder/profiles/dev.py` (et `staging.py` si applicable) : ajout du step en queue.
- `control-plane-api/src/routers/audit.py` ou `services/audit_service.py` : surface API qui expose `is_synthetic`.
- `control-plane-ui/src/pages/AuditLog.tsx` (et tests) : badge UI visible pour events synthetic.

**Contraintes verrouillées (A5 + A6 + Q8.1)** :

- ❌ **Jamais activé par défaut en prod**. Garde stricte par profil :

  | Profil | Phase 2 fixtures |
  |---|---|
  | `dev` | enabled by default |
  | `staging-demo` | enabled by explicit opt-in (variable env dédiée) |
  | `staging-prodlike` | disabled |
  | `prod` | forbidden (raise au démarrage si tentative) |

- ✅ **Marqueur verrouillé sur la colonne JSONB `details` existante (A5)**. Pas de migration de schéma `audit_events` avant ADR Gap 2. Structure :

  ```json
  {
    "synthetic": true,
    "source": "seed",
    "fixture_batch": "observability-data-visibility-2026-05-09"
  }
  ```

  L'API expose un champ calculé : `is_synthetic: true`. Pas de nouvelle colonne `source`. Si une colonne dédiée devient souhaitable, elle est traitée avec la migration issue de l'ADR Gap 2, pas dans Phase 2.

- ✅ **Badge UI visible obligatoire (A6)**. L'API expose `is_synthetic=true` ET l'UI `/audit-log` affiche une distinction visible (badge, chip, label, ou tooltip). Aucun mélange opaque avec des events réels.

- ❌ La présence de fixtures **ne** prouve **pas** que `emit_audit_event → Kafka → consumer → audit_events → UI` fonctionne. Tests et description PR doivent l'énoncer explicitement.

**Volume cible** (proposition, à challenger) :
- ~100 events / tenant `demo` sur 30 jours, distribués (10 actions × 5 outcomes × variabilité timestamp).
- Tenants exclus : aucun tenant prod réel (`free-aech`, autres clients).

**DoD binaire (A6 durcie)** :
- [ ] Step (ou module) implémenté avec marqueur `details.synthetic=true` + `details.source="seed"` + `details.fixture_batch="observability-data-visibility-2026-05-09"`.
- [ ] Aucune migration `alembic` ajoutée. La colonne `audit_events.details` JSONB existante suffit.
- [ ] Test unitaire vérifie : (1) tous les events insérés portent le marqueur synthetic, (2) garde prod fonctionne (`make seed` en `ENVIRONMENT=production` raise), (3) profil `dev` insère le volume cible, (4) profil `staging-demo` n'insère qu'avec opt-in explicite, (5) `staging-prodlike` n'insère pas.
- [ ] **API expose `is_synthetic=true`** sur les events seedés.
- [ ] **UI `/audit-log` affiche un badge / chip / label visible** sur les events où `is_synthetic=true`. Test régression UI couvre.
- [ ] Le PR description énonce explicitement : "this PR does not validate the audit pipeline end-to-end".

**Anti-goal** : pas de validation pipeline. Phase 5 (5A) s'en charge.

**Risques** :
- R2.1 : marqueur `details.synthetic=true` est filtré par les requêtes UI existantes, faisant disparaître les events. Mitigation : test E2E qui vérifie qu'un event seedé apparaît dans `/v1/audit/{tenant}` avec `is_synthetic=true`.
- R2.2 : un opérateur active le seeder en prod par accident. Mitigation : double garde (variable d'env + `if ENVIRONMENT == "production": raise RuntimeError`).
- R2.3 : les events synthetic polluent les exports CSV / JSON sans badge. Mitigation : exporter inclut le champ `is_synthetic`.
- R2.4 (A6) : badge UI omis ou désactivable par CSS, mélangeant events réels et synthetic. Mitigation : test régression UI vérifie le badge présent et non-supprimable par config tenant.

**Rollback** : `git revert` du PR. Les events déjà insérés peuvent être nettoyés via une requête SQL ciblée (`DELETE FROM audit_events WHERE details->>'synthetic' = 'true' AND tenant_id IN ('demo')`), ou laissés (synthétiques explicites, pas dommageables hors prod).

**Effort estimé** : 3h–1j selon le verdict Phase 1, +0.5j pour le badge UI + tests régression (A6).

**Owner candidat** : platform / cp-api + ui pour badge.

**Dépendances** : Phase 1.

---

### Phase 3 — Gap 4B-minimal: honest wording for guardrails empty states

**Objectif** : remplacer le copy "No metrics sample" par une formulation qui ne prétend pas distinguer "0 trips" de "no series", tant que le backend ne peut pas le prouver.

**Préconditions** : aucune. Indépendante de Phase 0/1/2.

**Fichiers touchés** :
- `control-plane-ui/src/pages/SecurityDashboard*` (ou équivalent — chemin exact à confirmer ; cf `routers/gateway_observability.py:35` et UI guardrails contract).
- Tests régression UI correspondants.

**Contraintes verrouillées** :
- Le wording doit être honnête : "No guardrail trip samples in window" ou équivalent qui ne distingue pas implicitement 0 et absence.
- Aucune nouvelle métrique côté gateway (réservé à Phase 6 / 4B-full).
- Aucun changement backend de `gateway_observability.py` pour ce sous-gap (pure UI).

**DoD binaire** :
- [ ] Toutes les occurrences de "No metrics sample" sur les cartes guardrails remplacées par le copy honnête.
- [ ] Tests régression mis à jour.
- [ ] Aucune nouvelle métrique Prometheus ajoutée.

**Anti-goal** : ce sous-gap **ne** distingue **pas** "0 trips réels" de "aucune série Prometheus". Il documente l'ambigüité au lieu de la cacher.

**Risques** :
- R3.1 : le wording change casse des tests régression existants (ex: `regression/observability-titles.test.tsx`). Mitigation : update tests dans le même PR.
- R3.2 : opérateurs déjà habitués à "No metrics sample" peuvent être perturbés. Mitigation : doc release notes interne.

**Rollback** : `git revert` PR. Wording redevient l'ancien.

**Effort estimé** : 0.5j (challenger : ~0.5j).

**Owner candidat** : ui.

**Dépendances** : aucune.

---

### Phase 4 — Gap 2 ADR: audit by_resource vs by_actor

**Objectif** : poser la doctrine produit qui décide si l'audit log doit exposer une vue actor en plus de la vue resource, et avec quelle matrice d'autorisation cross-tenant.

**Préconditions** : aucune. Indépendante de Phase 0–3.

**Livrables** :
- `stoa-docs/docs/architecture/adr/ADR-066-audit-log-actor-resource-views.md` (numérotation à confirmer via `stoa-docs/docs/architecture/adr/` index — le memory pointe ADR-066 comme prochain libre, à vérifier au moment du draft).

**Contenu obligatoire ADR (verrouillé par challenger)** :

1. **Définition formelle des dimensions** :
   - `resource_tenant_id` : tenant propriétaire de la ressource modifiée. Source actuelle de `audit_events.tenant_id`.
   - `actor_subject_id` : user / service account / API token. Source actuelle de `audit_events.actor_id`.
   - `actor_home_tenant_id` ou `actor_workspace_tenant_id` : seulement si la sémantique est non-ambiguë au moment de la requête.
2. **Cas multi-tenant** : un user qui appartient à plusieurs tenants. Comportement défini explicitement.
3. **Cas service accounts / API tokens / platform admins** : règles de backfill, gestion de l'absence de `actor_home_tenant_id`.
4. **Visibility scope / redaction cross-tenant** : règles d'accès de la vue `by_actor` pour éviter les fuites ("user de A a modifié ressource de B" — qui peut le voir ?).
5. **Matrice d'autorisation** : qui voit quoi, par rôle (`tenant-admin`, `cpi-admin`, `viewer`, `devops`).
6. **Verdict** : on implémente la vue `by_actor` ? Si oui, schéma cible ; si non, justification.

**DoD binaire** :
- [ ] ADR mergée dans `stoa-docs` avec verdict explicite (`accepted` / `rejected` / `deferred`).
- [ ] Si `accepted`, ADR référence cette plan comme déclencheur.
- [ ] Aucune migration de schéma `audit_events` exécutée à ce stade.

**Anti-goal** : l'ADR **ne** code **pas** la migration. Elle pose la doctrine. Si la doctrine implique une migration, la migration sera planifiée séparément (out of this plan, ou plan séparé).

**Risques** :
- R4.1 : ADR `accepted` mais sans consensus → re-challenge avant exécution.
- R4.2 : ADR `deferred` indéfiniment → Gap 2 reste ouvert mais ce plan continue sans bloquer Phase 5/6.

**Rollback** : ADR `rejected` ou `superseded` par un futur ADR.

**Effort estimé** : 0.5j rédaction + ~2h review Council.

**Owner candidat** : data + platform.

**Dépendances** : aucune. Peut courir en parallèle de Phase 2/3.

---

### Phase 5 — Gap 1B: synthetic-traffic probes (split into 5A + 5B per A7)

**Objectif** : preuve runtime indépendante du seeder. Le challenger a verrouillé un split en deux sous-probes parce qu'`emit_audit_event` n'est pas appelé par le simple trafic gateway runtime — c'est un appel des routers control-plane (`apis.py`, `tenants.py`, `users.py`, `deployment_service.py`, `promotion_service.py`).

**Préconditions** :
- Phase 0 verdict connu (informe la portée Phase 5 selon A8).
- Phase 1 decision-log validé (confirme que ces probes vivent hors du seeder).
- Phase 2 livrée (réduit la pression sur Phase 5 pour servir de "fixture").

**Portée selon Phase 0 verdict (A8 verrouillée)** :

| Phase 0 verdict | Phase 5 portée |
|---|---|
| `pipeline_live` | 5A audit + 5B Prom + 5B traces visés |
| `pipeline_partial` | 5A audit + 5B Prom ; hops trace live testés, autres marqués `blocked by infra` |
| `pipeline_absent` | 5A audit + 5B Prom **uniquement** ; **MEGA infra Gap 3 obligatoire avant validation trace** |

**Aucun verdict `n/a` n'est acceptable comme preuve "end-to-end"**. Si Phase 0 = `pipeline_absent`, Phase 5 documente explicitement que la couche trace n'est pas testée et qu'une MEGA infra séparée est requise (Q8.2 verrouillée).

---

#### Phase 5A — Control-plane audit probe

**Objectif** : prouver le chemin `action control-plane → emit_audit_event → Kafka → audit consumer → audit_events → /v1/audit/{tenant} → UI`.

**Livrables** :
- Soit `control-plane-api/scripts/probes/audit_pipeline_probe.py`, soit job CI dédié `.github/workflows/audit-pipeline-probe.yml`.
- Documentation `docs/observability/audit-pipeline-probe.md`.

**Contraintes** :
- ❌ Jamais activé par défaut en prod. Opération manuelle, traçable, signée par opérateur (Q8.4).
- ✅ Exécute une action connue qui appelle `emit_audit_event` (par ex. `POST /v1/apis` créant une API tenant test, ou équivalent idempotent).
- ✅ Vérifie chaque hop : (1) action POST réussit, (2) Kafka `audit-events` topic enregistre, (3) `audit_trail_consumer` ingère, (4) row présent dans `audit_events` table, (5) `/v1/audit/{tenant}` retourne l'event, (6) UI `/audit-log` peut le rendre.
- ✅ Output binaire par hop : `audit_emit: pass | fail`, `kafka_consumed: pass | fail`, `pg_persisted: pass | fail`, `api_visible: pass | fail`.
- ✅ Tenant dédié `audit-probe` (nettoyé par la probe en début/fin).

**DoD binaire** :
- [ ] Probe exécutable en `dev` k3d et complète sans erreur sur tous les hops.
- [ ] Probe documentée avec hops listés.
- [ ] Probe **non** auto-déclenchée en prod (`workflow_dispatch` only).

#### Phase 5B — Gateway runtime telemetry probe

**Objectif** : prouver le chemin `requête gateway → Prometheus scrape → /v1/metrics/query_range → UI Live Calls` et, conditionnellement (A8), `requête gateway → OTel SDK → Alloy → Data Prepper → OpenSearch otel-v1-apm-span-* → /v1/monitoring/transactions → UI Live Traces`.

**Livrables** :
- Soit `stoa-gateway/probes/runtime_telemetry_probe.sh` (ou `.py`), soit job CI dédié `.github/workflows/gateway-telemetry-probe.yml`.
- Documentation `docs/observability/gateway-telemetry-probe.md`.

**Contraintes** :
- ❌ Jamais activé par défaut en prod. Workflow_dispatch only.
- ✅ Appelle une route gateway idempotente (health-like ou route catalog test) avec `traceparent` + `X-Probe-Id` (cf A2).
- ✅ Vérifie hops Prometheus : (1) `stoa_http_requests_total` incrémenté pour la route, (2) `query_range` UI retourne la valeur attendue.
- ✅ Vérifie hops trace **uniquement si Phase 0 verdict ≠ `pipeline_absent`** (A8) : (3) span écrit dans Alloy, (4) span présent dans OpenSearch `otel-v1-apm-span-*` (recherche par `trace_id` W3C de A2), (5) `/v1/monitoring/transactions` retourne la trace, (6) UI Live Traces peut la rendre.
- ✅ Output binaire par hop. Si trace bloquée par Phase 0 = `pipeline_absent`, output : `traces: blocked_by_infra (see Phase 0 verdict)`.

**DoD binaire** :
- [ ] Probe exécutable en `dev` k3d et complète sans erreur sur les hops applicables.
- [ ] Probe documentée avec hops listés et matrice de blocage selon verdict Phase 0.
- [ ] Probe **non** auto-déclenchée en prod.

---

**Anti-goal Phase 5** : cette phase **ne** remplace **pas** les fixtures Phase 2. Elle vérifie le runtime, les fixtures servent les démos. Elle **ne** prétend **pas** être "end-to-end" si Phase 0 = `pipeline_absent`.

**Risques** :
- R5.1 : la probe peut taper des routes prod réelles si déployée par erreur en prod sans gating. Mitigation : `if ENVIRONMENT == "production" and not OPERATOR_OPT_IN: refuse`.
- R5.2 : la probe peut déclencher des effets de bord (cascade audit events, alertes). Mitigation : routes dédiées, idempotentes, instrumentées, tenant `audit-probe` isolé.
- R5.3 (A8) : si Phase 0 = `pipeline_absent`, prétendre tester les traces serait un faux succès. Mitigation : output `blocked_by_infra` explicite, plan reconnaît qu'une MEGA infra séparée est requise.
- R5.4 : 5A et 5B ont des call-paths différents → la même action ne prouve pas les deux. Mitigation : probes séparées par design (A7).

**Rollback** : `git revert` PR. Si workflow CI déclenché en prod par accident, kill workflow + rollback.

**Effort estimé** : 5A ~1j, 5B ~1j (selon verdict Phase 0). Total ~1.5–2j.

**Owner candidat** : sre + platform pour 5A, sre + gateway pour 5B.

**Dépendances** : Phase 0, Phase 1, Phase 2.

---

### Phase 6 — Gap 4A + 4B-full MEGA: separate, deferred

**Objectif** : étendre l'instrumentation guardrails au-delà du chemin MCP et introduire les compteurs `evaluations_total` / `decisions_total` pour permettre un split sémantique honnête côté UI.

**Statut** : **MEGA séparée**. Hors batch observability data integrity. Référencée ici uniquement pour traçabilité.

**Pré-décisions à valider avant lancement Phase 6** :
1. Le produit confirme que les guardrails doivent observer le trafic non-MCP (proxy modes : sidecar, connect, etc.).
2. Le compteur d'évaluations est validé comme un nouveau public contract Prometheus (cardinalité acceptable, label set fini).

**Livrables (esquisse, à détailler dans MEGA propre)** :
- Nouveaux compteurs gateway :
  ```
  stoa_guardrails_evaluations_total{mode, tenant, route, policy}
  stoa_guardrails_decisions_total{decision="allow|redact|block", ...}
  ```
- Call-sites étendus aux modes non-MCP (`stoa-gateway/src/proxy/`, `router/`, etc. à confirmer).
- Backend `routers/gateway_observability.py` exploite les nouveaux counters pour produire le split sémantique 5 états.
- UI rend les 5 états : `metrics_unavailable | no_evaluations | evaluations_zero_trips | trips_observed | stale_data`.

**DoD binaire** : (à raffiner dans MEGA)
- [ ] Compteurs émis depuis tous les modes guardrail-applicables.
- [ ] Cardinalité Prometheus validée (cf `docs/observability/gateway-metrics-cardinality.md`).
- [ ] UI états distincts visibles en environnement test avec scénarios fabriqués.

**Anti-goal** : ce plan **ne** spécifie **pas** la MEGA. Phase 6 = pointer.

**Risques** : explosion cardinalité Prometheus si labels mal conçus. Mitigation : revue cardinalité pré-merge.

**Rollback** : revert de la MEGA au cas par cas.

**Effort estimé** : 2–3j coverage non-MCP + 1–2j compteurs + 1j UI = ~1 semaine MEGA.

**Owner candidat** : gateway.

**Dépendances** : Phase 0 verdict (informe si trafic non-MCP existe en prod), arbitrage produit explicite.

---

## 5. Acceptance Criteria

Mesurables et vérifiables au terme de chaque phase :

| # | Critère | Phase | Cible / preuve |
|---|---|---|---|
| AC-0 | Pipeline traces localisé | 0 | `probe-trace-walk.md` existe avec verdict `pipeline_live\|pipeline_partial\|pipeline_absent` (A1) + composants manquants nommés si applicable + preuve trace par `trace_id` W3C ou recherche fenêtre/route/service.name (A2) |
| AC-1 | Contrat seed-vs-runtime décidé | 1 | `docs/decisions/2026-05-09-seed-vs-runtime-contract.md` mergé avec verdict explicite |
| AC-2 | Audit-log fixtures isolées | 2 | (a) ~100 events synthetic / tenant `demo`, (b) profil `prod` refuse, (c) `staging-prodlike` refuse, (d) `staging-demo` opt-in only, (e) marqueur `is_synthetic` exposé API + **badge UI visible** (A6), (f) aucune migration alembic ajoutée (A5) |
| AC-3 | Wording guardrails honnête | 3 | "No metrics sample" remplacé partout sur cartes guardrails ; tests régression à jour |
| AC-4 | ADR audit views verdict | 4 | ADR mergée dans `stoa-docs` avec **verdict** explicite (`accepted`/`rejected`/`deferred`) + matrice d'autorisation (Q8.3) ; si `deferred`, signal de réouverture nommé |
| AC-5a | Audit pipeline probe (5A) | 5A | Job exécutable en dev, hops binaires `audit_emit/kafka_consumed/pg_persisted/api_visible`, doc associée |
| AC-5b | Gateway telemetry probe (5B) | 5B | Job exécutable en dev, hops Prom binaires + hops trace selon verdict Phase 0 (A8) ; `blocked_by_infra` explicite si applicable |
| AC-6 | Aucune régression empty-state | toutes | Tests `regression/observability-titles.test.tsx`, `live-calls-metric-integrity.test.tsx`, audits PR-3A guardrails restent green |
| AC-7 | Aucun fallback synthétique en prod | toutes | `STOA_AUDIT_DEMO_FALLBACK` reste `false` en prod ; aucune fixture insérée en `ENVIRONMENT=production` |
| AC-8 | Traçabilité plan ↔ challenger | toutes | Chaque PR cite cette plan + le verdict challenger ; aucune dérive silencieuse |

## 6. Risk Matrix

| ID | Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Phase 0 révèle un pipeline `pipeline_absent` complet → Phase 5B perd sa couche traces | MEDIUM | MEDIUM | Phase 5B documente `traces: blocked_by_infra` (A8) ; Gap 3 sort en MEGA infra séparée (Q8.2). 5A et la couche Prom de 5B continuent. |
| R2 | Phase 2 fixtures synthetic activées par accident en prod | LOW | HIGH | Garde double : `if ENVIRONMENT == "production": raise` + variable d'env explicite. Test couvre les deux branches. |
| R3 | Phase 2 fixtures filtrées par les requêtes UI existantes (badge cassé) | MEDIUM | LOW | E2E test : un event seedé apparaît bien dans `/v1/audit/{demo}` avec `is_synthetic=true`. |
| R4 | Phase 3 wording change casse tests régression UI | MEDIUM | LOW | Update tests dans la même PR. CI bloque sinon. |
| R5 | Phase 4 ADR rejected sans alternative → Gap 2 reste ouvert indéfiniment | MEDIUM | LOW | Plan documente le `deferred` comme acceptable, n'arrête pas Phase 5/6. |
| R6 | Phase 5 probe exécutée en prod par erreur | LOW | MEDIUM | `workflow_dispatch` only + opt-in env var explicite. CI default = dev seulement. |
| R7 | Phase 5 probe émet trafic qui pollue les métriques prod | LOW | LOW | Routes dédiées, label `synthetic=true` sur les requêtes émises. Phase 0 décide si Prometheus filtre. |
| R8 | Phase 6 ajoute compteurs avec cardinalité explosive | LOW | MEDIUM | Cardinalité revue pré-merge MEGA contre `gateway-metrics-cardinality.md`. |
| R9 | Drift plan ↔ exécution Codex (PRs ne respectent plus les contraintes) | MEDIUM | MEDIUM | Claude review chaque PR contre cette plan ; toute déviation → re-challenge. |
| R10 | Operator misreads Phase 2 fixtures comme "audit pipeline marche" | MEDIUM | MEDIUM | PR description Phase 2 + doc explicite : "fixtures, not pipeline proof". |

## 7. Rollback Strategy

Chaque phase est conçue pour être réversible.

- **Phase 0** : aucun rollback côté données métier si la route est idempotente et dédiée ; la sonde crée volontairement de la télémétrie synthetic (cf A3).
- **Phase 1** : decision-log peut être révisé par un nouveau decision-log. Aucun code touché.
- **Phase 2** : `git revert` PR. Events déjà insérés en dev/staging peuvent être nettoyés via SQL ciblée sur `details->>'synthetic' = 'true'`.
- **Phase 3** : `git revert` PR. Wording revient.
- **Phase 4** : ADR `superseded` par un futur ADR. Aucun code touché.
- **Phase 5** : `git revert` PR. Workflow ou script supprimé.
- **Phase 6** : MEGA séparée, ses propres rollbacks (TBD).

Aucune destruction de données prod prévue à aucune phase.

## 8. Open Questions — toutes résolues par challenger 2026-05-09

Toutes les questions ouvertes du draft initial ont été tranchées par le challenger ChatGPT. Les réponses verrouillées sont listées ci-dessous et reflétées dans les phases / DoD / AC. Verdict complet : `docs/decisions/2026-05-09-observability-data-visibility.md` §"Answers to plan's open questions".

### Q8.1 — Profil staging accueille-t-il les fixtures synthetic ?

**Verrouillé** :

| Profil | Phase 2 fixtures |
|---|---|
| `dev` | enabled by default |
| `staging-demo` | enabled by explicit opt-in |
| `staging-prodlike` | disabled |
| `prod` | forbidden |

Reflété dans Phase 2 § "Contraintes verrouillées".

### Q8.2 — Phase 0 verdict `pipeline_absent` débloque-t-il une MEGA infra ?

**Verrouillé : oui**. Si Alloy / Data Prepper / OpenSearch traces ne sont pas déployés ou pas routés, MEGA infra séparée requise (sre/k8s-ops). Phase 5B trace est alors marquée `blocked_by_infra`, 5A audit + 5B Prom continuent. Reflété dans Phase 5 § A8.

### Q8.3 — Phase 4 ADR : doit-elle inclure une recommandation ou rester neutre ?

**Verrouillé : doit recommander**. Une ADR neutre ne ferme pas Gap 2. Verdict explicite obligatoire (`accepted` / `rejected` / `deferred`). Si `deferred`, le signal de réouverture est nommé. Reflété dans AC-4.

### Q8.4 — Phase 5 probe : quelle fréquence en CI ?

**Verrouillé** : initialement `workflow_dispatch` only. Quand stable :

| Environnement | Fréquence |
|---|---|
| `dev`/`k3d` | on demand + optional nightly |
| `staging` | manual before demo/release |
| `prod` | manual operator opt-in only |

Pas de hourly tant que routes / effets de bord / budgets métriques ne sont pas maîtrisés.

### Q8.5 — Phase 2 marqueur : `source=seed` (colonne) ou `details.synthetic=true` (JSONB) ?

**Verrouillé : `details.synthetic=true` (JSONB)**. Pas de migration de schéma `audit_events` avant ADR Gap 2. Structure exacte :

```json
{
  "synthetic": true,
  "source": "seed",
  "fixture_batch": "observability-data-visibility-2026-05-09"
}
```

API expose `is_synthetic` calculé. Reflété dans Phase 2 § A5.

### Q8.6 — Phase 6 lancement : déclencheur ?

**Verrouillé** : Phase 6 lancée si **au moins un** des signaux existe :

1. Le produit confirme que `/observability/security` doit couvrir le trafic non-MCP.
2. Un opérateur ou incident montre que l'état actuel masque une absence d'instrumentation.
3. Phase 3 réduit la confusion de wording, mais opérateurs demandent encore "zéro trip ou aucune évaluation ?".
4. Une revue sécurité exige la preuve `evaluations_total` / `decisions_total`.

Sans ce signal, Phase 6 reste correctement hors batch.

## 9. Cross-references

- Audit : `docs/audits/2026-05-09-observability-data-visibility/findings.md`
- Verdict challenger : `docs/audits/2026-05-09-observability-data-visibility/challenger-verdict.md`
- ADR-067 (UAC/MCP/Smoke doctrine) — relevant pour Phase 6 (guardrails sont conceptuellement UAC).
- CAB-1411 — origine seeder catalog-only.
- CAB-1475 — `audit_events` table (alembic 044).
- CAB-1831 — gateway OTel always-compiled-in.
- CAB-1997 — Data Prepper / `otel-v1-apm-span-*`.
- PR train récent : #2723–#2745 (observability data integrity batch).
- Audits prior : `2026-05-08-live-calls-runtime-verification`, `2026-05-09-audit-log-runtime-verification`, `2026-05-09-guardrails-runtime-verification`.

## 10. Annexe — Matrice traçabilité audit → verdict → phase

| Gap (audit) | Verdict (challenger) | Phase plan |
|---|---|---|
| Gap 3 — trace pipeline | "Diagnostic cluster avec sonde traçable end-to-end" | Phase 0 |
| (cadre seed-vs-runtime) | "Décision courte avant 1A" | Phase 1 |
| Gap 1A — seeder fixtures | "Fixture audit, pas validation pipeline. Gated, taggée synthetic." | Phase 2 |
| Gap 4B-minimal | "Wording honnête, sans claim 0 vs absence" | Phase 3 |
| Gap 2 — by_resource/by_actor | "ADR avant migration, matrice d'autorisation" | Phase 4 |
| Gap 1B — synthetic traffic | "Smoke job séparé du seeder core" | Phase 5A (audit) + 5B (gateway telemetry) — split par A7 |
| Gap 4A + 4B-full | "MEGA séparée, hors batch observability" | Phase 6 (référencé) |

---

## 11. Claude Review Contract

Claude Code n'écrit pas le code de ce plan. Claude intervient comme **reviewer indépendant** sur chaque PR Codex.

### 11.1 Verdict format

Pour chaque PR Codex, Claude rend exactement un verdict parmi :

| Verdict | Sens |
|---|---|
| `pass` | Phase couverte, DoD/AC satisfaits, anti-goals respectés. |
| `pass_with_minor_notes` | Phase couverte, mais notes éditoriales / docs / nits à traiter en suivi. Pas bloquant. |
| `blocked` | DoD/AC non satisfaits, ou un risque listé est réalisé. PR à corriger avant merge. |
| `re_challenge_required` | La PR dévie du plan validé. Le plan ou la décision doit être ré-ouvert avant de continuer. |

Le verdict est posté en commentaire de PR avec : (1) le verdict, (2) la phase couverte, (3) la liste des items checklist passés / échoués, (4) les preuves (file:line, logs, screenshots) si disponibles.

### 11.2 Checklist commune à toutes les phases

Claude vérifie sur chaque PR :

- [ ] La PR cite ce plan (`docs/plans/2026-05-09-observability-data-visibility.md`) et le verdict challenger (`docs/decisions/2026-05-09-observability-data-visibility.md`).
- [ ] La PR cible **une seule** phase de ce plan (pas de scope creep cross-phase).
- [ ] Les **anti-goals** de la phase ne sont pas violés.
- [ ] Les **DoD** de la phase sont couverts par tests, docs ou preuves archivables.
- [ ] Aucun fallback synthetic silencieux n'est introduit en prod (`STOA_AUDIT_DEMO_FALLBACK` reste fail-closed prod).
- [ ] Aucun changement de schéma `audit_events` (Alembic) n'est introduit avant ADR Phase 4.
- [ ] Aucune migration de schéma autre que celles explicitement autorisées par la phase.
- [ ] Toute déviation du plan est signalée comme `re_challenge_required`, pas masquée comme nit.

### 11.3 Claude ne doit pas

- ❌ Écrire ou corriger le code applicatif.
- ❌ Créer de ticket Linear (l'opérateur ouvre les tickets phase par phase au moment de l'exécution).
- ❌ Approuver une phase suivante tant que la phase précédente gated n'est pas close (gates §"Prochaine étape humaine").
- ❌ Accepter une PR qui transforme une fixture Phase 2 en preuve pipeline.
- ❌ Accepter une PR Phase 0 qui modifie du code applicatif (Phase 0 = no code, A4 verrouillé).
- ❌ Accepter une PR Phase 5 qui prétend être "end-to-end" si Phase 0 = `pipeline_absent` (A8 verrouillé).
- ❌ Cumuler `pass_with_minor_notes` pour absorber des déviations qui auraient dû être `blocked`.

### 11.4 Claude checks by phase

#### Phase 0 — cluster diagnostic

- [ ] Aucun code applicatif modifié (A4).
- [ ] Verdict produit est exactement `pipeline_live`, `pipeline_partial` ou `pipeline_absent` (A1, snake_case).
- [ ] Si `pipeline_partial` ou `pipeline_absent` : composants manquants nommés.
- [ ] La preuve trace s'appuie sur `trace_id` W3C corrélé OU recherche par fenêtre/route/service.name (A2). **Pas uniquement `X-Probe-Id`.**
- [ ] Failure mode "headers HTTP non capturés" pris en compte avant verdict `pipeline_absent`.
- [ ] Route utilisée idempotente / health-like / tenant `demo-probe` (A3).

#### Phase 1 — seed-vs-runtime contract

- [ ] Decision-log existe à `docs/decisions/2026-05-09-seed-vs-runtime-contract.md`.
- [ ] Verdict explicite (seeder catalog-only OU sous-module `observability_fixtures`).
- [ ] Marqueurs cités : `details.synthetic=true`, `details.source="seed"`, `details.fixture_batch="observability-data-visibility-2026-05-09"` (E1 verrouillé). Jamais `metadata.synthetic`.
- [ ] Profils autorisés / interdits explicités (`dev`, `staging-demo`, `staging-prodlike`, `prod`).

#### Phase 2 — audit-log fixtures

- [ ] **Aucune migration Alembic** ajoutée (A5).
- [ ] Garde prod active : `if ENVIRONMENT == "production": raise`.
- [ ] `staging-prodlike` refuse également ; `staging-demo` opt-in only (Q8.1).
- [ ] API expose `is_synthetic=true` sur events seedés.
- [ ] **UI affiche un badge / chip / label visible** (A6) — vérifié par test régression UI.
- [ ] Description PR contient : "this PR does not validate the audit pipeline end-to-end".
- [ ] Marqueur dans `details` JSONB est exactement `{synthetic, source, fixture_batch}`.
- [ ] Exporter CSV/JSON inclut `is_synthetic`.

#### Phase 3 — guardrails wording minimal

- [ ] **Wording UI uniquement.** Aucune nouvelle métrique Prometheus.
- [ ] "No metrics sample" remplacé par formulation honnête type "No guardrail trip samples in window".
- [ ] Tests régression UI mis à jour (notamment `regression/observability-titles.test.tsx`).
- [ ] Aucun changement backend `routers/gateway_observability.py`.

#### Phase 4 — ADR by_resource / by_actor

- [ ] ADR mergée dans `stoa-docs` avec verdict explicite (`accepted` / `rejected` / `deferred`) — pas neutre (Q8.3).
- [ ] Si `deferred` : signal de réouverture nommé.
- [ ] Matrice d'autorisation présente : `tenant-admin`, `cpi-admin`, `viewer`, `devops`.
- [ ] Cas multi-tenant utilisateur traité.
- [ ] Cas service accounts / API tokens / platform admins traité.
- [ ] Règles de redaction cross-tenant explicitées.
- [ ] **Aucune migration `audit_events`** exécutée à ce stade.

#### Phase 5 — runtime probes

- [ ] **Phase 5 scindée** en 5A (audit) + 5B (gateway telemetry) (A7). Pas de probe unique prétendant prouver les deux.
- [ ] **Phase 5A** : action déclenche `emit_audit_event`, hops binaires `audit_emit / kafka_consumed / pg_persisted / api_visible`.
- [ ] **Phase 5B** : route gateway idempotente, hops Prom binaires, hops trace selon verdict Phase 0 (A8).
- [ ] Si Phase 0 = `pipeline_absent` : 5B trace marquée `blocked_by_infra` explicitement, **pas** `n/a` (A8).
- [ ] `workflow_dispatch` only — pas de schedule auto en prod (Q8.4).
- [ ] Tenant dédié `audit-probe` pour 5A, nettoyé en début/fin.
- [ ] Documentation `docs/observability/audit-pipeline-probe.md` et `gateway-telemetry-probe.md` présentes.

#### Phase 6 — guardrails non-MCP + 4B-full

- [ ] **Aucune implémentation Phase 6 n'entre dans ce batch.** Phase 6 = pointer MEGA séparée.
- [ ] Si une PR Codex tente d'introduire `evaluations_total` ou de toucher `stoa-gateway/src/proxy/` au nom de Phase 6 : verdict `re_challenge_required`.
- [ ] La MEGA Phase 6 démarre uniquement sur signal explicite (Q8.6) — pas par initiative Codex.

### 11.5 Coherence-check posture

À chaque PR, Claude relit :

1. La phase ciblée du plan (file:line réf au plan).
2. Le decision-log (`docs/decisions/2026-05-09-observability-data-visibility.md`).
3. Les artefacts produits par la phase (probe-trace-walk.md, decision-log seed-vs-runtime, ADR, etc.).

Si l'un des trois manque ou contredit la PR, verdict `blocked` ou `re_challenge_required`.

---

## Prochaine étape humaine

État actuel : **`validation_status: validated`** (re-challenge 2026-05-09, micro-corrections E1+E2 appliquées, Claude Review Contract section 11 ajoutée).

L'exécution phase par phase par Codex est ouverte, sous les gates verrouillés ci-dessous :

1. **Phase 0 d'abord, sans code.** Aucune autre phase ne démarre tant que le verdict `pipeline_live | pipeline_partial | pipeline_absent` n'est pas archivé.
2. **Aucune Phase 2 tant que Phase 1 n'a pas fixé le contrat seed-vs-runtime.**
3. **Aucune migration `audit_events` avant ADR Phase 4.**
4. **Phase 5B trace seulement selon le verdict Phase 0** (cf A8 : `pipeline_absent` → trace marquée `blocked_by_infra` + MEGA infra séparée).
5. Chaque PR Codex référence ce plan (`plan_ref: docs/plans/2026-05-09-observability-data-visibility.md`) et indique la phase couverte.
6. **Claude Code valide la cohérence des PRs vs ce plan, mais n'écrit pas le code applicatif.** Toute déviation détectée → re-challenge.
7. Tickets Linear créables phase par phase au moment de l'exécution, pas en bloc.
