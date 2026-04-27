# 03 — État DB legacy, contraintes, stoa-catalog

> Phase 1 audit, read-only. Réponses aux questions §3 du brief.

## 1. La table cible n'est pas `apis` — c'est `api_catalog`

Surprise majeure pour la spec. Recherche exhaustive `__tablename__` dans
`control-plane-api/src/models/` :
- Aucun modèle n'utilise `__tablename__ = "apis"`.
- Le modèle utilisé par le handler est `APICatalog` → `__tablename__ = "api_catalog"` (`control-plane-api/src/models/catalog.py:33-35`).
- Migration de création : `control-plane-api/alembic/versions/009_create_catalog_cache_tables.py:23-41`.
- Migration historiquement liée : `031_add_audience_to_api_catalog.py`, `015_add_target_gateways_to_api_catalog.py`, `084_api_uniqueness_tenant_name_version.py`.

La spec §6.3, §6.5, §6.6, §6.8, §7 référence systématiquement `apis.id`, `apis.name`, `apis.tenant_id`, `apis.backend_url`, `apis.spec_hash`, `apis.source_commit_sha`, `apis.display_name`. Aucun de ces noms ne correspond au schéma réel. Ce n'est pas un détail de naming : c'est un blocker conceptuel pour Phase 6.

## 2. Schéma actuel `api_catalog`

Source : migration `009` + ajouts `015` (`target_gateways`), `031` (`audience`),
`084` (uniqueness rebuild), modèle SQLAlchemy `models/catalog.py:33-95`.

| Colonne | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `id` | `UUID` | NOT NULL (PK) | `gen_random_uuid()` server + `uuid.uuid4()` Python | **Random**, pas déterministe. |
| `tenant_id` | `VARCHAR(100)` | NOT NULL | – | indexé `ix_api_catalog_tenant` |
| `api_id` | `VARCHAR(100)` | NOT NULL | – | **Slug `[a-z0-9-]+` produit par `_slugify(api.name)` côté handler** (`apis.py:91-96, 275`). C'est lui que l'API REST retourne comme `id`, pas le UUID PK. |
| `api_name` | `VARCHAR(255)` | NOT NULL (depuis migration `084`) | – | display string libre, conservé tel quel |
| `version` | `VARCHAR(50)` | NOT NULL (depuis `084`) | `"1.0.0"` | |
| `status` | `VARCHAR(50)` | NOT NULL | `"active"` côté DB ; `"draft"` côté handler | divergence connue |
| `category` | `VARCHAR(100)` | NULL | – | |
| `tags` | `JSONB` | NOT NULL | `[]` | |
| `portal_published` | `BOOLEAN` | NOT NULL | `false` | |
| `audience` | `VARCHAR(20)` | NOT NULL | `"public"` | ajouté par migration `031` |
| `metadata` (mappé Python `api_metadata`) | `JSONB` | NOT NULL | – | **C'est ici que `backend_url`, `description`, `display_name`, `deployments` vivent**. Pas de colonne dédiée. |
| `openapi_spec` | `JSONB` | NULL | – | |
| `git_path` | `VARCHAR(500)` | NULL | – | optionnel ; écrit par les sync workers (`catalog_sync_service`, `git_sync_worker`) |
| `git_commit_sha` | `VARCHAR(40)` | NULL | – | **40 chars** (SHA-1 only) ; la spec §6.3 demande `varchar(64)` pour la migration future SHA-256 |
| `target_gateways` | `JSONB` | NOT NULL | `[]` | ajouté par migration `015` |
| `synced_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | utilisée comme created_at + updated_at de fortune (`apis.py:76-79`) |
| `deleted_at` | `TIMESTAMPTZ` | NULL | – | soft delete |

Pas de colonnes `name`, `backend_url`, `display_name`, `version` dédiées au-delà de ce qui est listé : tout ce que la spec §6.8 veut **projeter en colonne** est aujourd'hui **dans le JSONB `metadata`**.

## 3. Contraintes uniques (état post-`084`)

- `id PRIMARY KEY` (UUID).
- `ix_api_catalog_tenant_name_version` UNIQUE partial sur `(tenant_id, api_name, version) WHERE deleted_at IS NULL` (`alembic/versions/084_*.py:32-38`).
- `ix_api_catalog_tenant_api_active` UNIQUE partial sur `(tenant_id, api_id) WHERE deleted_at IS NULL` (`084` lignes 41-47).

Conséquences pour la spec :
- **La contrainte `(tenant_id, api_name, version)` est blocante pour Phase 6** si la stratégie est `INSERT ... ON CONFLICT` ou recreate. Une API legacy `(demo, "Demo Httpbin", 1.0.0)` empêcherait l'insertion d'une ligne GitOps `(demo, "demo-httpbin", 1.0.0)` seulement si `_slugify` produit la même valeur ; en pratique `api_name` est libre côté legacy donc collision possible.
- **La contrainte `(tenant_id, api_id)` est strictement le scénario §6.14** : `compute_api_id("demo","demo","demo-httpbin")` produit un UUID — mais la colonne `api_id` est `VARCHAR(100)` (slug), **pas un UUID**. Donc :
  - Soit la spec §6.4 doit changer la sémantique de `api_id` (UUID5) **et** changer le type de colonne (UUID → VARCHAR ne fonctionne pas dans l'autre sens) ⇒ migration non-additive non triviale, en violation de §3.2 d'`architecture-rules.md`.
  - Soit `compute_api_id` doit retourner un **slug** déterministe, pas un UUID5. Dans ce cas la spec §6.4 + §7 doivent être ajustées avant Phase 3.
  - **Non déterminé** : à clarifier avec Christophe avant Phase 3.

## 4. Comment `apis.id` est-il généré aujourd'hui ?

Trois identifiants se télescopent dans `api_catalog`, à ne pas confondre :

| Identifiant logique | Colonne | Comment | Ce que la REST API retourne |
|---|---|---|---|
| PK technique | `api_catalog.id` | UUID4 random (`uuid.uuid4()` + `gen_random_uuid()`), jamais retourné par la REST | jamais |
| Routing slug | `api_catalog.api_id` | `_slugify(api.name)` (`apis.py:275`) | `APIResponse.id = api_catalog.api_id` (`apis.py:151-152`, `apis.py:335`) |
| Display | `api_catalog.api_name` | `api.name` brut côté handler | `APIResponse.name = api_catalog.api_id` (slug, `apis.py:154`) ; `APIResponse.display_name = metadata.display_name or api_name or api_id` |

Donc `GET /v1/tenants/{tid}/apis/{id}` cherche par **slug**, pas par UUID (`repositories/catalog.py: get_api_by_id` opère sur `api_id`). La spec §6.4 (`api_id` = `uuid5(...)`) dit que `GET /v1/tenants/{tid}/apis/{id}` "continue de fonctionner avec un UUID" — c'est faux aujourd'hui, le contrat actuel exige un **slug**, et le smoke AT-1 lit `.id` du JSON sans typer (`scripts/demo-smoke-test.sh:342`).

## 5. APIs déjà présentes sur le tenant `demo`

Seedés via Alembic (idempotent `ON CONFLICT (tenant_id, api_id) DO UPDATE`) sur le tenant `"demo"` :

- `074_seed_realdata_apis.py` — 6 APIs : `exchange-rate`, `coingecko`, `openweathermap`, `newsapi`, `alphavantage`, `echo-fallback`.
- `075_seed_traffic_seeder_apis.py` — 6 APIs : `ecb-financial-data`, `eurostat`, `echo-oauth2`, `echo-bearer`, `fapi-accounts`, `fapi-transfers`.

Aucun seed ne contient `demo-httpbin`. Donc à froid, aucune collision de nom avec le contrat AT-1 sur le tenant `demo` — mais le handler peut en avoir créé un en cours de smoke (idempotent à `(tenant_id, api_name, version)`, retourne 409 sinon).

Risque de collision avec `compute_api_id("demo","demo",<name>)` :
- La fonction §6.4 produit un **UUID5** ; les seeds insèrent dans `api_id VARCHAR(100)` un **slug** (`exchange-rate`…). Donc collision littérale impossible (types incompatibles), **mais** la cohabitation force soit migrer la colonne, soit accepter que les APIs legacy ne soient jamais addressables via `/apis/{uuid}` (ce que la spec §6.14 prévoit, mais sous une hypothèse d'égalité de types).
- Conclusion (à valider) : la politique §6.14 (tenant `demo-gitops` propre) suffit à éviter la collision pour le critère d'arrivée Phase 7 ; mais elle ne lève pas le débat type colonne.

## 6. État du repo `stoa-catalog`

- Le dossier `stoa/stoa-catalog/` est **inclus dans le monorepo** comme un sous-dossier non-Git (vérifié : `ls stoa-catalog/.git` ⇒ absent ; pas de submodule). Layout actuel : `stoa-catalog/{tenants,_templates,environments,schemas,scripts}/`. Les tenants présents ont chacun **un seul fichier `uac.yaml`** (ex. `tenants/oasis/uac.yaml`), pas un fichier par API.
- Le repo distant utilisé par le `git_sync_worker` est défini par config : `settings.git.github.org="stoa-platform"`, `settings.git.github.catalog_repo="stoa-catalog"` (`config.py:58-59`), donc cible `github.com/stoa-platform/stoa-catalog`. Il n'a **jamais** été cloné localement par cp-api : `GitHubService` opère via PyGithub Contents API (REST), pas via `git clone`.
- Le layout Git utilisé par `GitHubService.create_api` (`github_service.py:909-910, 983-1041`) est :
  - `tenants/{tenant_id}/apis/{api_name}/api.yaml`
  - `tenants/{tenant_id}/apis/{api_name}/uac.json`
  - `tenants/{tenant_id}/apis/{api_name}/policies/.gitkeep`
  - + optionnel `openapi.yaml` et `overrides/{env}.yaml`
  Donc **incompatible** avec la spec §6.1 qui exige `tenants/{tid}/environments/{env}/apis/{api_name}.uac.json` (un seul fichier `.uac.json` par API, dossier `environments/{env}` au milieu, pas de sous-dossier par API).
- Droits cp-api : configurés via `GITHUB_TOKEN` (`config.py:57`, `SecretStr`). Token GitHub PAT/App, pas un compte GitHub spécifique côté code. Pas de fallback `file://` pour démo offline (la spec §6.12 le veut explicitement).
- Conséquence : la Phase 3 doit décider entre (a) faire évoluer le layout `tenants/{tid}/apis/{name}/` historique vers le layout `environments/{env}/apis/{name}.uac.json` de la spec, en cassant tous les writers GitOps existants ; (b) coexister deux layouts pendant la transition. Aucune des deux options ne tient sur le `GitHubService` actuel sans rework. La spec §4.1 dit "pas de réutilisation de `GIT_SYNC_ON_WRITE`" — donc la Phase 3 introduit un nouveau pipeline parallèle, ce qui plaide pour (b).

## 7. `GIT_SYNC_ON_WRITE` : où, et comportement réel

Configuration :
- Source : `control-plane-api/src/config.py:253` — `GIT_SYNC_ON_WRITE: bool = True` (kill-switch). Peut être désactivé via env var.
- Lu par : `workers/git_sync_worker.py:84` (cache via `self._git_sync_enabled`), `main.py:318` (gate d'instanciation du worker), `services/gateway_deployment_service.py:51` (label de status).

Comportement réel quand `True` :
1. Boot cp-api lance `git_sync_worker.start()` (`main.py:316-323`) si `KAFKA_CONSUMERS_ENABLED=true` et `ENABLE_GIT_SYNC_WORKER=true`.
2. Worker créé un `KafkaConsumer` sur `stoa.api.lifecycle` (group `git-sync-worker`).
3. Pour chaque event `api-created` / `api-updated` / `api-deleted`, appelle `git_provider_factory()` (factory qui retourne `GitHubService` ou `GitLabService`), puis `service.create_api(...)` / `update_api(...)` / `delete_api(...)`.
4. `GitHubService.create_api` écrit via PyGithub Contents API au layout `tenants/{tid}/apis/{name}/...`.

Comportement quand `False` :
- Worker démarre puis log `"Git sync worker disabled (GIT_SYNC_ON_WRITE=false)"` (`workers/git_sync_worker.py:90`) et **return immédiat** sans consommer Kafka.
- Le handler continue d'émettre les events Kafka et d'INSERT en DB. Les events s'accumulent dans Kafka (selon TTL topic) et sont perdus pour la sync Git.
- `gateway_deployment_service.py:51` annote les statuts avec `git_sync_status="git_sync_disabled"`.

Conséquence pour la Phase 3 :
- La spec §9.6 interdit de réutiliser `GIT_SYNC_ON_WRITE` pour le nouveau pipeline. C'est cohérent avec l'état actuel : ce flag pilote un pipeline **Kafka-based**, asynchrone, post-commit DB. Le nouveau pipeline §6.5 doit être **commit-first** (Git avant DB), donc fondamentalement incompatible.

## 8. Synthèse des blockers / divergences pour Phase 3

| # | Constat | Impact spec |
|---|---|---|
| B1 | Pas de table `apis` ; `api_catalog` est utilisée. | §2.1, §6.3, §6.6, §6.8, §7 référencent un schéma absent. |
| B2 | Tous les champs métiers (`backend_url`, `display_name`, `description`) vivent dans `api_catalog.metadata` (JSONB). | §6.6 `db_row_matches_projection()` doit décider colonne dédiée vs JSONB diff. |
| B3 | `api_id` est `VARCHAR(100)` (slug), pas UUID. La spec §6.4 veut UUID5. | Migration non triviale, choix d'identité à arbitrer. |
| B4 | `api_catalog.id` (UUID PK) est random. | Briser §2.5 si les rows GitOps en gardent un — sauf si on y range `uuid5(...)`. |
| B5 | Layout Git existant `tenants/{tid}/apis/{name}/api.yaml + uac.json + …` ≠ spec §6.1 `tenants/{tid}/environments/{env}/apis/{name}.uac.json`. | Coexistence ou rebuild du writer. |
| B6 | `git_commit_sha VARCHAR(40)` (SHA-1 only). Spec §6.3 demande `varchar(64)`. | Migration additive triviale. |
| B7 | `_compute_spec_hash` privé, tronqué à 16, opère sur OpenAPI dict. | À réécrire (cf. `02-uac-and-spec-hash-location.md`). |
| B8 | `GET /v1/tenants/{tid}/apis/{id}` accepte un slug aujourd'hui. | Spec §6.4 dit "continue de fonctionner avec un UUID" — claim incorrect, à amender. |
| B9 | Aucun helper CLI `write_canonical_contract` n'existe. | Phase 4 le crée from scratch (cf. `02-...md` §6). |
