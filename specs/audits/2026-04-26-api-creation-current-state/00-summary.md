# 00 — Synthèse audit Phase 1

> Périmètre : `POST /v1/tenants/{tenant_id}/apis` (chemin actuel) vs spec
> `specs/api-creation-gitops-rewrite.md` v1.0. Read-only. Détail dans
> `01-call-graph.md`, `02-uac-and-spec-hash-location.md`,
> `03-legacy-state-and-constraints.md`.

## Verdict

Le chemin actuel est un **dual-write asynchrone Kafka-médié**, l'opposé doctrinal
du modèle GitOps de la spec. La spec est exécutable dans son ossature, mais
**plusieurs présuppositions de schéma DB et de tooling UAC sont fausses**. Phase 3
doit ouvrir une révision ciblée de la spec avant scaffold, sinon le module
`gitops_writer` est posé sur des colonnes/identifiants qui n'existent pas.

## Top 3 risques pour le rewrite

1. **La table cible n'est pas `apis`, c'est `api_catalog`.** Tous les §6.3/§6.6/§6.8/§7 référencent `apis.id`, `apis.name`, `apis.backend_url`, `apis.spec_hash`, `apis.source_commit_sha`. Aucun de ces noms n'existe ; la PK technique est `api_catalog.id` (UUID4 random), l'identifiant routing est `api_catalog.api_id` (`VARCHAR(100)`, slug), et `backend_url`/`display_name`/`description` vivent dans `api_catalog.metadata` JSONB. Phase 3 doit arbitrer : adapter la spec au schéma réel **ou** introduire une nouvelle table `apis` aux côtés de `api_catalog` (rewriting massif, contre §2.6 architecture-rules.md).
2. **`api_id` est un slug `VARCHAR(100)`, pas un UUID.** La spec §6.4 (`api_id = uuid5(NS, "tenant:env:name")`) suppose un type UUID. Le contrat REST §2.1 d'`architecture-rules.md` dit `GET /v1/tenants/{tid}/apis/{id}` ; aujourd'hui ce `{id}` est un slug, et le smoke AT-1 lit `.id` sans typer. Migrer `api_id` slug→UUID est **non additif** (interdit pendant le rewrite par §3.2 architecture-rules.md). À trancher avant Phase 3 : (a) `compute_api_id` retourne un slug déterministe (`tenant:env:name` slugifié) ; (b) garde UUID5 mais coexistence sur une nouvelle colonne `apis.uuid_id`.
3. **`compute_spec_hash` n'existe pas comme fonction publique partagée Python/Rust.** L'unique candidat est `_compute_spec_hash` (`uac_transformer.py:233`), privé, tronqué à 16 hex chars, qui opère sur un OpenAPI dict — pas sur un `UACContract`. La parité Rust est nulle (`stoa-gateway` traverse le champ sans recalculer). Le `spec_hash="515839b4...e39"` (64 chars) du `demo-httpbin.uac.json` ne peut pas être reproduit par le code actuel : il a été écrit à la main avec un algorithme inconnu. Phase 4 doit produire `compute_spec_hash` Python **et** Rust en même temps, et soit recalculer le hash du fixture canonique, soit demander à Christophe quelle valeur fait foi.

## Top 3 surprises (la spec présuppose, le code dément)

1. **Pas d'appel synchrone à Git dans le handler.** La spec §1 dit "selon flags propage vers stoa-catalog Git" — au présent — comme si c'était un side-effect inline. En réalité l'écriture Git est **complètement asynchrone**, médiée par le topic Kafka `stoa.api.lifecycle` et le worker `git_sync_worker` (`workers/git_sync_worker.py`). Le handler `routers/apis.py:235-358` ne touche jamais Git. La transformation §6.5 n'est donc pas "déplacer Git avant DB" mais "remplacer un pipeline Kafka post-commit par un commit Git pré-DB qui n'existe pas encore".
2. **Le layout `stoa-catalog` actuel est `tenants/{tid}/apis/{name}/api.yaml + uac.json + policies/.gitkeep + …`, pas `tenants/{tid}/environments/{env}/apis/{name}.uac.json`.** Le segment `environments/{env}` n'apparaît nulle part dans `GitHubService` (`github_service.py:909-1041`). Le clone monorepo `stoa/stoa-catalog/` utilise un layout encore différent : un seul `tenants/{tenant}/uac.yaml` par tenant. Conséquence : le nouveau pipeline ne peut pas réutiliser une ligne du `GitHubService` existant pour la création.
3. **L'écriture Git actuelle se fait via PyGithub Contents API (REST), pas via `git clone + git push`.** La spec §6.5 (`git fetch origin`, `git checkout -B main origin/main`, `git push origin main` avec retry borné, `git show {sha}:{path}`) suppose un working tree local avec subprocess `git`. Aucun working tree n'est aujourd'hui maintenu côté cp-api ; tout est REST API GitHub. La spec §6.11 (worktrees isolés) introduit donc un mécanisme **entièrement neuf**, sans précédent dans cp-api. Confirmé : `grep -rn "git worktree" control-plane-api/src/` → 0 résultat.

## Bugs observés (à ticketiser Phase 2, **pas fixés ici**)

- `routers/apis.py:41-48` `APICreate` Pydantic accepte sans validation les champs AT-1 `protocol` et `paths[]` ; ils sont silencieusement ignorés. Conséquence : un client AT-1 strict envoie `paths=[{path:"/get",methods:["GET"]}]` que le handler ne consomme jamais — le payload AT-1 et le contrat HTTP figé `architecture-rules.md` §2.1 ne se rencontrent qu'à la réponse minimale `{id, name}`. Pas un bug bloquant, mais un trou de validation à signaler.
- `routers/apis.py:332-342, 351-356` : la conversion d'erreur 409 repose sur `if "unique" in str(e).lower() or "duplicate"` — fragile vis-à-vis de futures migrations Postgres / pg-driver (locale, message). À durcir vers le code SQLSTATE.
- `schemas/uac_contract_v1_schema.json:63` indique `"first 16 hex chars"` pour `spec_hash` ; le fixture canonique `specs/uac/demo-httpbin.uac.json:43` porte un hash 64 chars. Incohérence intra-codebase.
- `models/catalog.py:43` : `api_name VARCHAR(255)` mais la migration `084` exige NOT NULL après backfill ; le code handler colle `api.name` brut (capitalisation possible). Cohabite avec un index UNIQUE sur `api_name` ⇒ deux noms qui diffèrent uniquement par casse créent deux lignes distinctes (Postgres `VARCHAR` est case-sensitive).
- `services/uac_transformer.py:238` : `_compute_spec_hash` tronquée à 16 chars n'est pas idempotent vis-à-vis de la valeur 64 chars qu'attend `demo-httpbin.uac.json`. Au mieux une dette, au pire une régression silencieuse pour tout consommateur futur du field.

## Réponses aux questions transverses §0 du brief

- **Invariants doctrine §2 — état actuel** :
  - §2.1 (Git = desired state) : **violé**. La DB est la vérité ; Git est un journal post-commit.
  - §2.2 (FastAPI ne projette jamais depuis le payload) : **violé**. Le handler INSERT directement les champs du payload HTTP dans `api_catalog`.
  - §2.3 (Reconcilers idempotents par `spec_hash`) : **violé**. Pas de reconciler scan-Git en place ; `git_sync_worker` est un consumer Kafka one-shot par event, pas un reconciler.
  - §2.4 (Drift par projection complète) : **non implémenté**. Aucun mécanisme de drift detection en place pour les APIs (la table `catalog_sync_status` existe mais sert au sync inverse `git_sync_worker` log).
  - §2.5 (Reconstructibilité) : **violé**. `api_catalog.id` est UUID4 random ; supprimer la table efface des identifiants non reconstructibles depuis Git.
- **Worker reconciler — pattern existant ?** Oui : `control-plane-api/src/workers/` contient déjà `sync_engine.py`, `gateway_health_worker.py`, `gateway_reconciler.py`, `git_sync_worker.py`, `telemetry_worker.py`, `*_metering_consumer.py`. Tous démarrés par `main.py:240-339` via `asyncio.create_task(worker.start())` (boucle async, pas Celery, pas RQ). C'est le pattern à suivre pour `catalog_reconciler` Phase 4. Pas de Celery ni RQ dans `requirements.txt` (vérifié indirectement : aucun import `celery`/`rq` dans `src/`).
- **Postgres advisory locks — usage existant ?** Aucun. `grep -rn "advisory_lock\|pg_advisory" control-plane-api/src/` → 0 résultat. Phase 3 introduira ce pattern from scratch ; pas de convention interne à respecter.
- **Worktrees Git — usage existant ?** Aucun. `grep -rn "git worktree\|worktree add" control-plane-api/src/` → 0 résultat. `GitHubService` clone via `git clone --depth=1` dans `tempfile.mkdtemp` (`github_service.py:321-345`) pour des opérations one-shot, jamais avec des worktrees persistants. Tout est à construire.

## Ce que Phase 1 valide

- Le chemin de code complet est tracé (`01-call-graph.md`).
- L'emplacement et l'état du tooling UAC sont connus (`02-...md`).
- Les contraintes uniques et l'identité legacy sont catalogues (`03-...md`).
- Le backlog Phase 2 a six entrées concrètes (B1-B9 §8 du document `03-...md`, plus les bugs §"Bugs observés" ci-dessus).

## Ce que Phase 1 ne tranche pas

- Choix `compute_api_id` slug vs UUID5 (cf. risque #2).
- Algorithme canonique exact qui produit `spec_hash="515839b4..."` du fixture (cf. risque #3 et `02-...md` §5).
- Stratégie de coexistence layout Git legacy vs spec §6.1 (cf. surprise #2).

À clarifier avec Christophe avant l'amorçage de la Phase 3.
