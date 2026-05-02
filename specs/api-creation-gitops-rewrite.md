# STOA Rewrite — API Creation GitOps

> **Statut**: v1.0 — 2026-04-26. Audit-informed + drift-justified + schema-confirmed. Validée pour exécution Phase 2 puis Phase 3.
> **Owner**: humain (Christophe). Les agents n'élargissent pas ce scope sans décision écrite.
> **Périmètre**: rewrite ciblé de la création d'API (`POST /v1/tenants/{tid}/apis`) vers un modèle Git-first avec `stoa-catalog` comme source de vérité, et **ré-adoption contrôlée non-destructive** des APIs saines du tenant `demo`.
> **Hors périmètre**: update, publish, promote, delete, prune ; migration destructive des UUID driftés ; suppression d'orphelins DB ; soft-delete inverse Git→DB ; conversion de format YAML→JSON ; multi-env. `uq_api_catalog_tenant_api` est retiré par migration 106 pour respecter le contrat soft-delete actif-only.
> **Invariant directeur**: à chaque phase, `./scripts/demo-smoke-test.sh` doit rester `REAL_PASS — DEMO READY`. Cf. [`rewrite-guardrails.md`](./rewrite-guardrails.md) §1.

## 0. Contexte — pourquoi cette spec existe

L'audit Phase 1 et 4 requêtes SQL diagnostiques sur `api_catalog` ont révélé **5 bugs structurels** du chemin actuel :

| # | Bug | Statut dans ce rewrite |
|---|---|---|
| **B-CATALOG** | Le code utilise `api_catalog`, pas `apis`. La spec v0.3.1 parlait à côté. | Corrigé (mapping aligné) |
| **B10** | `git_sync_worker` produit `git_path = "tenants/{tid}/apis/{UUID}/api.yaml"` au lieu de `"…/{slug}/api.yaml"`. 7 rows tenant `demo` 404 sur Git. | **In-scope partiel** : le nouveau chemin GitOps ne reproduit jamais ce bug. La migration destructive des 7 rows existantes reste hors scope. |
| **B11** | Le sync engine ne propage pas la disparition Git en soft-delete DB. `banking-services-v1-2` synced 2026-04-18, absent Git HEAD au 2026-04-26, row active. | **Out-of-scope complet** : cycle delete/prune séparé. Documenté dans le backlog Phase 2, jamais fixé dans ce rewrite. |
| **B-INDEX** | `uq_api_catalog_tenant_api` UNIQUE complet (sans `WHERE deleted_at IS NULL`) en doublon avec `ix_api_catalog_tenant_api_active`. Bloque la recréation après soft-delete (contredit CAB-1938). | **Résolu 2026-05-02** : migration 106 supprime la contrainte globale et garde l'unicité active-only. |
| **B-SPEC-HASH** | `_compute_spec_hash` privé tronqué à 16 chars sur OpenAPI dict. `demo-httpbin.uac.json` portait un hash 64 chars opaque. | **Résolu** : hash supprimé du fixture en commit `0aba7f4a9` (non utilisé). UAC V2 (cycle séparé) tranchera si hash UAC public nécessaire. |

État `api_catalog` du tenant `demo` au 2026-04-26 (13 rows actives) :

| Catégorie | Count | api_id | git_path stocké | Réalité Git |
|---|---|---|---|---|
| **A — Sain** | 5 | slug = api_name | `tenants/demo/apis/{slug}` | ✓ existe |
| **B — Drift UUID dur** | 7 | UUID | `tenants/demo/apis/{UUID}` | 404 (vrai = `…/{slug}`) |
| **C — Orphelin DB** | 1 | slug | `tenants/demo/apis/{slug}` | 404 (fichier disparu) |

Toutes synced en batch sha `ba7fc9f` le 2026-04-26 → drift produit par le sync engine actuel.

Ce rewrite est :
1. **justifié** par un drift terrain documenté ;
2. **ciblé** sur la création d'API uniquement ;
3. **non-destructif** : il ne migre ni ne supprime aucune row legacy.

## 1. Pourquoi ce rewrite

`POST /v1/tenants/{tid}/apis` aujourd'hui :
- valide le payload
- INSERT dans `api_catalog` (avec parfois `id` PK UUID qui fuite dans `git_path` — bug B10)
- émet un event Kafka `stoa.api.lifecycle`
- `git_sync_worker` background consomme et écrit dans `stoa-catalog` via PyGithub Contents API

La DB est de facto la source de vérité, mais elle ment sur Git. Conséquences observées : 7/13 rows avec `git_path` 404, 1 orphelin jamais nettoyé, aucune reconstructibilité.

## 2. Doctrine — adaptée à STOA

**Six invariants** :

1. **`stoa-catalog` Git remote = desired state.** `api_catalog` est un read model, pas la source.
2. **FastAPI ne projette jamais depuis le payload HTTP.** Validation, commit Git via `CatalogGitClient`, projection depuis le contenu **lu depuis le remote après commit**.
3. **Reconcilers idempotents.** Idempotence portée par `catalog_content_hash` (§6.2.1).
4. **Drift détecté par projection complète** sur **tous** les champs projetés, y compris `git_path`.
5. **Reconstructibilité.** Les rows GitOps-created reconstructibles depuis Git. Aucun champ DB-only mutable.
6. **Le path Git stocké en DB est une projection vérifiable du fichier Git réel.** Règle déterministe :
   ```
   api_catalog.git_path = "tenants/{tenant_id}/apis/{api_name}/api.yaml"
   ```
   où `api_name` = slug catalogue, **jamais** un UUID, **jamais** `api_catalog.id` (PK interne), **jamais** un ID gateway/runtime. Le reconciler vérifie que `read_at_commit(git_path, git_commit_sha)` retourne un contenu non-null avant de marquer `synced`.

Doctrine résultante :

> **Catalog describes. Git stores. Reconciler projects. Payload never projects. DB never guesses paths. Smoke proves.**

## 3. Contrats figés — non négociables

| Contrat | Source | Pourquoi figé |
|---|---|---|
| `POST /v1/tenants/{tid}/apis` → 201 + `{id, name}` | [`architecture-rules.md`](./architecture-rules.md) §2.1 | AT-1 du smoke en dépend |
| `GET /v1/tenants/{tid}/apis/{id}` → 200 + `{id, name, backend_url}` | [`architecture-rules.md`](./architecture-rules.md) §2.1 | AT-1 du smoke en dépend |
| Format public de `api_catalog.api_id` (string actuel) | Audit Phase 1 §03 + diagnostic SQL | Subscriptions, deployments, gateway routes y référencent |
| Schéma `api_catalog` existant (cf. §6.3) | `\d api_catalog` 2026-04-26 | 18 colonnes, 9 index, 0 FK. Migration additive seulement. |
| Index actif-only `ix_api_catalog_tenant_api_active` | CAB-1938 + migration 106 | Garantit l'unicité de routage active sans bloquer la réutilisation d'un slug soft-deleted. |
| Format `api.yaml` actuel (cf. §6.9 — référence : `payment-api/api.yaml`) | Inspection terrain 2026-04-26 | 12 APIs réelles l'utilisent |
| Fixture `specs/uac/demo-httpbin.uac.json` (forme depuis commit `0aba7f4a9`, sans `spec_hash`) | [`architecture-rules.md`](./architecture-rules.md) §2.2bis | Contrat UAC démo figé |
| Verdict `REAL_PASS — DEMO READY` du smoke | [`demo-acceptance-tests.md`](./demo-acceptance-tests.md) | Garde-fou universel |

## 4. Périmètre exact

### 4.1 In-scope

- Endpoint `POST /v1/tenants/{tid}/apis` (création uniquement)
- Module Python `control-plane-api/src/services/gitops_writer/`
- Reconciler in-tree via `asyncio.create_task(worker.start())` (audit Phase 1 §00)
- Abstraction `CatalogGitClient` (§6.7) — première impl `GitHubContentsCatalogClient` réutilisant le service PyGithub existant
- Layout Git **conservateur** : `tenants/{tid}/apis/{name}/api.yaml`. Format YAML conservé.
- Migration Alembic additive **minimale** : ajout d'une seule colonne `catalog_content_hash` (cf. §6.6). `git_path` et `git_commit_sha` existent déjà et sont réutilisés.
- Projection et **correction non-destructive** de `api_catalog.git_path` pour les APIs GitOps-created ou ré-adoptées
- Vérification que `git_path` pointe vers un fichier lisible via `read_at_commit()` non-null
- **Ré-adoption contrôlée des 5 APIs saines (catégorie A) du tenant `demo`** en Phase 6.5
- Endpoint `GET /v1/tenants/{tid}/apis/{id}/sync-status`
- Feature flag `GITOPS_CREATE_API_ENABLED` par tenant
- Lock distribué Postgres advisory (§6.8)
- Politique de collision legacy en 3 catégories (§6.14)
- Helper CLI pour produire un `api.yaml` valide selon §6.9

### 4.2 Out-of-scope (refus automatique)

**Cycle update API** :
- `PATCH/PUT /v1/tenants/{tid}/apis/{id}`

**Cycle delete / prune API** :
- `DELETE /v1/tenants/{tid}/apis/{id}`
- Soft-delete automatique des orphelins DB (catégorie C, ex: `banking-services-v1-2`)
- Correction du sync engine pour propager Git→DB la disparition de fichier (B11)
- Hard-delete d'une row `api_catalog` soft-deleted

**Cycle migration legacy** :
- Migration destructive des 7 rows catégorie B (UUID drifté) du tenant `demo`
- Migration de masse d'un `api_id` UUID vers slug sans fichier Git canonique
- Migration globale legacy → GitOps de tenants existants

Exception in-scope après audit prod du 2026-05-02 : si le reconciler lit un
fichier Git canonique `tenants/{tenant}/apis/{slug}/api.yaml`, qu'aucune row
active `(tenant, api_id=slug)` n'existe, et qu'une seule row active
`(tenant, api_name=slug, version)` existe, cette row peut être adoptée en place.
Le PK `api_catalog.id` est conservé et les références souples connues
(`deployments`, `promotions`, `subscriptions`, `credential_mappings`,
`pipeline_traces`) sont déplacées dans la même transaction.

**Cycle promotion / multi-env** :
- Promotion dev/staging/prod
- Migration du layout Git vers `environments/{env}/`
- Décision d'identité multi-env

**Cycle UAC V2** :
- Création d'une fonction publique `compute_uac_spec_hash`
- Modification de `_compute_spec_hash` privé existant
- Régénération du fixture `demo-httpbin.uac.json`
- Conversion YAML → JSON UAC

**Autres** :
- Changement du format public de `api_catalog.api_id`
- Calcul `api_id = uuid5(...)` déterministe — retiré
- Création d'un `api_fingerprint` métier — possible mais reportée
- Publication portail (CPD-* dans [`client-prospect-demo-scope.md`](./client-prospect-demo-scope.md))
- Projection `stoa-catalog → gateway routes` ou `→ portal`
- Refactor des subscriptions, applications, deployments
- Multi-repo, multi-org GitHub
- ArgoCD / Flux

### 4.3 Règle d'or de scope

Si pendant l'exécution une question type *« et si on en profitait pour... »* émerge, la réponse par défaut est **NON**. La question va dans le backlog Phase 2 et sera traitée dans un cycle ultérieur.

## 5. Plan d'exécution — phases séquentielles

| Phase | Livrable | Critère de fin | Durée cible |
|---|---|---|---|
| 0 | **Cette spec validée** | Christophe valide v1.0 | ½ jour |
| 1 | `specs/audits/2026-04-26-api-creation-current-state/` | **DONE** — audit livré | — |
| 2 | Backlog Linear `label:api-creation-rewrite-backlog` | ≥ 14 tickets, **dont B10 (in-scope partiel) et B11 (out-of-scope deferred)** | 1 jour |
| 3 | Décisions Phase 3 + scaffold | (a) format helper CLI catalogue YAML défini ; (b) interface `CatalogGitClient` figée ; (c) migration Alembic mergeable (ajout `catalog_content_hash` uniquement) ; (d) PR scaffold avec `NotImplementedError` partout, CI verte | 1 jour |
| 4 | Implémentation `gitops_writer.create_api()` + reconciler asyncio + helper CLI | Le POST avec flag ON écrit dans `stoa-catalog` via le mode configuré: `direct` compatibilité ou `pull_request` canonique (branche + PR + merge + tag release), puis projette. Le reconciler boucle. Le helper produit un `api.yaml` valide. | 2-3 jours |
| 5 | Tests isolés | Couverture 100%, drift detection par projection complète **incluant `git_path` + `read_at_commit` non-null**, idempotence, advisory_lock_key stable, mapping payload→catalogue déterministe, **3 catégories legacy correctement classifiées**, refus UUID-shaped api_name | 1 jour |
| 6 | Strangler sur tenant `demo-gitops` propre | Sur tenant `demo-gitops`, POST commit Git via PyGithub puis projette `api_catalog`. Tenant `demo` historique inchangé. AT-1 vert sur les deux. | 1-2 jours |
| **6.5** | **Ré-adoption contrôlée des 5 APIs saines (catégorie A) du tenant `demo`** | Pour chaque API `account-management-api`, `customer-360-api`, `fraud-detection-api`, `payment-api`, `petstore` : `git_path` confirmé/corrigé canonique, `git_commit_sha` rempli, `catalog_content_hash` rempli, `read_at_commit` non-null, projection cohérente. **Catégories B et C non touchées.** Aucune mutation de subscriptions/deployments/keys. Smoke historique reste `REAL_PASS`. | 1 jour |
| 7 | Re-run smoke + tests GitOps | `GITOPS_CREATE_API_ENABLED=true ./scripts/demo-smoke-test.sh` = `REAL_PASS` sur `demo-gitops`. §7 et §7bis passent. | 1 jour |
| 8 | Fix du backlog Phase 2 | **100% des tickets in-scope sont fixed avec test de régression.** B-INDEX est résolu par migration 106. Tickets encore out-of-scope (B11, migration B, prune C) sont closed-documented/deferred avec cycle cible explicite. | variable |
| 9 | Re-run smoke + régression + §7/§7bis | Toutes métriques Phase 7 maintenues | ½ jour |
| 10 | Bascule limitée aux tenants éligibles | Flag ON par défaut **uniquement** sur (i) tenants GitOps-initialized (`demo-gitops` + nouveaux), et (ii) tenants explicitement classés clean par audit SQL préalable. **Tenants contenant des catégories B ou C non résolues restent sur l'ancien chemin.** Doc de rollback. | ½ jour |

**Total estimé** : 9-12 jours calendaires. Avec AI Factory : 5-7 jours réels.

## 6. Contrat technique

### 6.1 Layout `stoa-catalog` — conservateur

```
stoa-catalog/
  tenants/{tenant_id}/apis/{api_name}/api.yaml
```

`{tenant_id}` et `{api_name}` slugs `[a-z0-9-]+`, **jamais UUID-shaped**.

Migration vers `environments/{env}/` out-of-scope.

### 6.2 Interface `gitops_writer`

```python
class GitOpsWriter:
    def create_api(
        self,
        tenant_id: str,
        contract_payload: ApiCreatePayload,
        actor: str,
    ) -> CreateApiResult:
        """
        Idempotent par catalog_content_hash. Trois cas figés :

        Case A — fichier api.yaml absent dans Git :
          → render YAML, commit via CatalogGitClient.create_or_update()
          → relire le contenu remote au commit produit
          → projection api_catalog (incluant git_path canonique)

        Case B — fichier api.yaml présent avec même content_hash :
          → no-op Git
          → projection api_catalog depuis le contenu remote actuel
            (Permet aux retry HTTP de réussir si la projection avait échoué)

        Case C — fichier api.yaml présent avec content_hash différent :
          → raise GitOpsConflictError → 409 Conflict
        """
```

`api_id` retourné = slug du payload, **jamais un UUID**, **jamais `api_catalog.id` PK**.

### 6.2.1 Hash de contenu — figé

```
catalog_content_hash = sha256_hex(api_yaml_bytes_from_git_remote)
```

Hash technique du contenu Git remote relu. Suffisant pour idempotence et drift detection. Ne prétend pas être un hash UAC sémantique. La fonction `compute_uac_spec_hash` n'est pas créée dans ce rewrite (UAC V2 décidera).

### 6.3 Schéma `api_catalog` réel et `api_sync_status` nouveau

**`api_catalog` existant** (`\d api_catalog` 2026-04-26, ne pas modifier) :

```
id                   uuid PK gen_random_uuid()       ← interne, jamais exposé
tenant_id            varchar(100) not null
api_id               varchar(100) not null           ← public, slug
api_name             varchar(255) not null
version              varchar(50) not null
status               varchar(50) not null default 'active'
category             varchar(100) nullable
tags                 jsonb not null default '[]'
portal_published     boolean not null default false
metadata             jsonb not null
openapi_spec         jsonb nullable
git_path             varchar(500) nullable           ← réutilisé, contient bug B10
git_commit_sha       varchar(40) nullable            ← réutilisé
synced_at            timestamptz not null default now()
deleted_at           timestamptz nullable
target_gateways      jsonb not null default '[]'
audience             varchar(20) not null default 'public'

UNIQUE (tenant_id, api_name, version) WHERE deleted_at IS NULL
UNIQUE (tenant_id, api_id) WHERE deleted_at IS NULL
-- migration 106: aucun UNIQUE global (tenant_id, api_id) sans deleted_at
```

**Migration additive Phase 3** (une seule colonne) :

```sql
ALTER TABLE api_catalog ADD COLUMN catalog_content_hash VARCHAR(64) NULL;
```

Aucune autre colonne ajoutée. `git_path` et `git_commit_sha` existent et sont réutilisés.

**Nouvelle table `api_sync_status`** :

```
api_sync_status
- tenant_id              varchar(100)
- api_id                 varchar(100)               (= api_catalog.api_id, slug)
- target                 enum(api_catalog, gateway, portal)
- desired_commit_sha     varchar(64)
- desired_content_hash   varchar(64)                 (catalog_content_hash)
- observed_content_hash  varchar(64) nullable
- desired_git_path       text                        (= "tenants/{tid}/apis/{name}/api.yaml")
- status                 enum(pending, syncing, synced, failed,
                              drift_detected, drift_orphan)
- last_error             text nullable
- last_sync_at           timestamptz

PRIMARY KEY (tenant_id, api_id, target)
```

Reconstructible depuis `stoa-catalog` + `api_catalog`.

### 6.4 Identité — 5 niveaux distincts

**Aucun UUID5 figé dans ce cycle.** L'identité publique reste `api_catalog.api_id`.

| # | Niveau | Identifiant | Format | Rôle |
|---|---|---|---|---|
| 1 | **Catalogue interne** | `api_catalog.id` | UUID PK `gen_random_uuid()` | Clé technique DB. **Jamais exposée publiquement. Jamais utilisée pour `git_path`.** Probable source du bug B10 si fuite. |
| 2 | **Catalogue public** | `api_catalog.api_id` | string slug actuel | Identité publique exposée par `POST/GET /apis/{id}`. Subscriptions/deployments/keys y référencent. |
| 3 | **Fingerprint métier** *(optionnel, futur)* | `api_fingerprint` | hash longueur fixe | Décision Phase 3 si besoin. **Non figé ici.** |
| 4 | **Gateway runtime** | `gateway_route_id` / `gateway_api_id` | propre à chaque gateway | Hors scope. Ne doit jamais devenir l'`api_id`. |
| 5 | **Déploiement runtime** | `GatewayDeployment.id`, `desired_generation` | cf. [`api-deployment-flow.md`](./api-deployment-flow.md) | Hors scope. |

**Règle dure** : aucun ID des niveaux 1, 4 ou 5 ne devient le niveau 2. Le bug B10 viole cette règle (fuite probable du niveau 1 vers `git_path`).

### 6.5 Flow détaillé `POST /v1/tenants/{tid}/apis` avec flag ON

```
 1. Valider payload HTTP (Pydantic schema)
 2. Normaliser tenant_id, api_name = slug(payload.name)
       Refus si api_name match un pattern UUID → 422
 3. Render contenu api.yaml via le mapping figé (cf. §6.9)
 4. Validation projectabilité : single backend_url → sinon 422
 5. Calculer catalog_content_hash = sha256_hex(api_yaml_bytes)
 6. Calculer git_path = "tenants/{tenant_id}/apis/{api_name}/api.yaml"
       NEVER from api_catalog.id (PK UUID), NEVER from any UUID source
 7. Vérification anti-collision en 3 catégories (cf. §6.14) :
       SELECT api_id, git_path, git_commit_sha
       FROM api_catalog WHERE tenant_id = ? AND api_id = ? AND deleted_at IS NULL
       - row absente → continuer (Case A possible)
       - row catégorie A (slug + git_path canonique + commit_sha présent) → ré-adoption sûre
       - row catégorie B (api_id UUID-shaped ou git_path UUID-shaped) → 409 legacy collision
       - row catégorie C (git_commit_sha référence un fichier disparu Git HEAD) → 409 legacy collision
 8. Acquérir lock distribué scope=(tenant_id, api_id)
 9. Lire contenu actuel via CatalogGitClient.get(git_path) :
       - absent              → Case A
       - hash identique      → Case B (no-op Git, jump à étape 12)
       - hash différent      → Case C → 409 Conflict
10. CatalogGitClient.create_or_update(git_path, api_yaml_bytes,
                                      expected_sha=..., actor=actor,
                                      message="create api {tid}/{name}")
       - race condition → relire, réévaluer Case A/B/C, retry max 3×
       - épuisement → 503, aucune projection
10bis. Écrire aussi `tenants/{tenant_id}/apis/{api_id}/openapi.yaml`.
       Si le payload contient `openapi_spec`, sérialiser cette spec; sinon
       générer une spec OpenAPI 3.0 minimale depuis `display_name`, `version`
       et `backend_url`. La spec générée doit rester compatible avec le
       preflight webMethods, notamment sans `additionalProperties` booléen.
       Ce fichier est la vérité configurationnelle de la description API.
11. file_commit_sha = CatalogGitClient.latest_file_commit(git_path)
12. Relire contenu depuis Git remote :
       committed_bytes = CatalogGitClient.read_at_commit(git_path, file_commit_sha)
       Vérifier non-null. Si null → 500, last_error="git_path 404 after commit"
       committed_content_hash = sha256_hex(committed_bytes)
       parsed_content = parse_yaml(committed_bytes)
       openapi_spec = parse sibling openapi.yaml|yml|json ou swagger.yaml|yml|json
                      si présent; fichier présent mais invalide => status=failed
13. Vérification cohérence path ↔ contenu (cf. §6.10)
14. project_to_api_catalog(parsed_content, file_commit_sha,
                           committed_content_hash, git_path,
                           openapi_spec,
                           target="api_catalog")
       Mappings : cf. §6.9
       Transactionnel et idempotent
       NE PAS écraser target_gateways (cf. §6.9)
15. update api_sync_status(target='api_catalog', status='synced', ...)
16. Pas d'émission de l'event Kafka stoa.api.lifecycle (cf. §6.13)
17. Relâcher le lock
18. Retourner 201 {id: api_id, name: api_name}
```

**Points non négociables** :
- **Étape 2.** Refus si `api_name` UUID-shaped. Plus jamais de niveau 1 dans le niveau 2.
- **Étape 6.** `git_path` calculé depuis le slug, jamais depuis un UUID. Test scaffold Phase 3 vérifie qu'aucune fonction du nouveau code ne convertit `api_catalog.id` → `git_path`.
- **Étape 7.** 3 catégories distinguées, pas binaire.
- **Étape 12.** `read_at_commit` retourne null après push réussi → 500 explicite (bug d'infrastructure), pas dégradation silencieuse.
- **Étape 10bis.** `openapi_spec` n'est pas sérialisé dans `api.yaml`; il vit dans le fichier Git canonique `openapi.yaml`, fourni ou généré minimalement à la création.
- **Étape 14.** La projection consomme le contenu Git relu, jamais le payload. **Jamais d'écrasement de `target_gateways`**. `openapi_spec` est hydraté depuis le fichier Git frère (`openapi.*` ou `swagger.*`) et devient un cache runtime dérivé de Git.
- **Étape 16.** Court-circuit explicite de l'event Kafka legacy.
- **Reconciler.** La boucle utilise les blob SHA du tree Git pour ignorer les fichiers inchangés déjà réconciliés; elle ne doit pas relire chaque `api.yaml` à chaque tick.

### 6.6 Reconciler in-tree — pattern asyncio existant

```python
# Ajout dans main.py:
from control_plane_api.services.catalog_reconciler.worker import CatalogReconcilerWorker
asyncio.create_task(CatalogReconcilerWorker(catalog_git_client, db).start())
```

Boucle (extraits clés) :

```
async def start():
    while not shutdown:
        try:
            for remote_file in await catalog_git_client.list_file_metadata("tenants/*/apis/*/api.yaml"):
                git_path = remote_file.path
                tenant_id, api_name = parse_path(git_path)

                # Refus si api_name UUID-shaped (corruption Git)
                if is_uuid_shaped(api_name):
                    await update_status(failed, "uuid-shaped api_name in git_path")
                    continue

                if blob_cache[git_path] == remote_file.sha:
                    seen.add((tenant_id, api_name))
                    continue

                content_bytes = await catalog_git_client.get(git_path)
                content_hash = sha256_hex(content_bytes)
                commit_sha = remote_file.commit_sha or await catalog_git_client.latest_file_commit(git_path)
                parsed = parse_yaml(content_bytes)

                # Validation cohérence path ↔ contenu (§6.10)
                # Validation projectabilité (single backend_url)

                # Anti-collision legacy en 3 catégories
                category = await classify_legacy(tenant_id, api_name, git_path)
                if category in ("uuid_drift", "orphan"):
                    await update_status(drift_detected, f"legacy: {category}")
                    continue   # ne pas réparer automatiquement

                # Render projection attendue
                expected_row = render_api_catalog_projection(
                    parsed, commit_sha, content_hash, git_path)

                # Lecture état réel
                actual_row = await db.fetch_one(
                    "SELECT api_id, tenant_id, api_name, version, status, "
                    "category, tags, portal_published, audience, "
                    "git_path, git_commit_sha, catalog_content_hash "
                    "FROM api_catalog "
                    "WHERE tenant_id=? AND api_id=? AND deleted_at IS NULL",
                    tenant_id, api_name)

                # Décision drift par projection complète
                if actual_row is None:
                    if try_advisory_lock(tenant_id, api_name):
                        await project_to_api_catalog(parsed, commit_sha,
                                                     content_hash, git_path)
                        await update_status(synced, ...)

                elif not row_matches_projection(actual_row, expected_row):
                    if try_advisory_lock(tenant_id, api_name):
                        await update_status(drift_detected, "projection drift")
                        await project_to_api_catalog(parsed, commit_sha,
                                                     content_hash, git_path)
                        await update_status(synced, ...)

                elif sync_status_missing or sync_status.status != 'synced':
                    await update_status(synced, ...)

            # Détection orphelins DB (information seulement, jamais de delete)
            for orphan in await find_db_orphans():
                await update_status(drift_orphan, "no git file at HEAD")

        except Exception as e:
            logger.exception("reconciler iteration failed")

        await asyncio.sleep(CATALOG_RECONCILE_INTERVAL_SECONDS)
```

`row_matches_projection()` compare au minimum :
- `api_id`, `tenant_id`, `api_name`, `version`, `status`, `category`, `tags`, `portal_published`, `audience`
- `git_path`, `git_commit_sha`, `catalog_content_hash`
- `read_at_commit(actual_row.git_path, actual_row.git_commit_sha)` retourne non-null

**Pas dans la comparaison (champs préservés, gérés par d'autres flows)** :
- `target_gateways` (déploiement)
- `metadata` (réservé)

`openapi_spec` est dans la comparaison: il est un cache runtime dérivé du
fichier Git frère et doit être réconcilié comme drift de projection.

`CATALOG_RECONCILE_INTERVAL_SECONDS=10`.

### 6.7 Abstraction `CatalogGitClient`

```python
class CatalogGitClient(Protocol):
    async def get(self, path: str) -> RemoteFile | None
    async def create_or_update(self, path, content, expected_sha,
                               actor, message) -> RemoteCommit
    async def read_at_commit(self, path: str, commit_sha: str) -> bytes | None
    async def latest_file_commit(self, path: str) -> str
    async def list(self, glob_pattern: str) -> list[str]
```

Première impl : `GitHubContentsCatalogClient` réutilisant le service PyGithub existant. Pas de worktree, pas de `git push` CLI.

### 6.8 Lock distribué

```python
import hashlib

def advisory_lock_key(tenant_id: str, api_id: str) -> int:
    raw = f"stoa:gitops:{tenant_id}:{api_id}".encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    return int.from_bytes(digest[:8], "big", signed=True)
```

Writer : `pg_advisory_lock` bloquant. Reconciler : `pg_try_advisory_xact_lock` non-bloquant. **Jamais `hash()` Python natif**.

### 6.9 Mapping payload HTTP → `api.yaml` puis → `api_catalog`

Format référence (`payment-api/api.yaml` 2026-04-26) :

```yaml
id: payment-api
name: payment-api
display_name: "Payment Initiation API"
version: "3.1.0"
description: |
  Multiline description...
backend_url: https://httpbin.org/anything
status: active
category: Banking
tags: [portal:published, banking, payments]
deployments:
  dev: true
  staging: false
```

**Mapping payload HTTP → `api.yaml`** :

| Champ YAML | Source payload |
|---|---|
| `id` | `slug(payload.name)` (refus si UUID-shaped) |
| `name` | `slug(payload.name)` |
| `display_name` | `payload.display_name` ou `payload.name` |
| `version` | `payload.version` |
| `description` | `payload.description` ou vide |
| `backend_url` | `payload.backend_url` (single-backend imposé) |
| `status` | `"active"` (constant pour ce cycle) |
| `category` | `payload.category` ou non émis |
| `tags` | `payload.tags` ou `[]` |
| `deployments` | `{dev: true, staging: false}` (par défaut pour ce cycle) |

**Champs payload AT-1 ignorés** (non sérialisés) : `protocol`, `paths[]`.

**Mapping `api.yaml` → `api_catalog`** :

| Colonne `api_catalog` | Source | Notes |
|---|---|---|
| `id` (PK) | non écrite par GitOps | gen_random_uuid() pour un nouveau INSERT, préservé pour un UPDATE |
| `tenant_id` | tenant du `git_path` | |
| `api_id` | YAML `.id` (= slug) | **jamais UUID**; peut remplacer un ancien UUID en adoption contrôlée par `(tenant, api_name, version)` |
| `api_name` | YAML `.name` | |
| `version` | YAML `.version` | |
| `status` | YAML `.status` | |
| `category` | YAML `.category` | nullable |
| `tags` | YAML `.tags` (jsonb) | sérialisation directe |
| `portal_published` | dérivé : `"portal:published" in tags` | |
| `audience` | YAML `.audience` ou `'public'` (default DB) | |
| `metadata` | projection de `api.yaml` | champs Console/runtime (`display_name`, `backend_url`, `description`, etc.) |
| `openapi_spec` | fichier frère `openapi.yaml|yml|json` ou `swagger.yaml|yml|json` | cache runtime dérivé; Git reste la source de vérité |
| `target_gateways` | **non écrit par GitOps** | préservé, géré par déploiement |
| `git_path` | path réellement lu/committé | canonique, jamais UUID |
| `git_commit_sha` | `latest_file_commit(git_path)` | |
| `catalog_content_hash` | `sha256_hex(api_yaml_bytes)` | colonne ajoutée Phase 3 |
| `synced_at` | `now()` | |
| `deleted_at` | non touché | |

### 6.10 Validation cohérence path ↔ contenu

| Vérification | Règle | Action si violée |
|---|---|---|
| Filename | `path.api_name == slug(content.name)` | `failed`, "name mismatch" |
| ID/Name cohérence | `content.id == content.name` | `failed`, "id != name" |
| Slug | `api_name` matche `[a-z0-9-]+` (pas UUID-shaped) | rejet writer (422), rejet reconciler |
| Path canonique | `git_path == "tenants/{tenant_id}/apis/{api_name}/api.yaml"` | rejet projection |

### 6.11 [Section retirée v1.0]

Workspace Git isolation caduque avec PyGithub Contents API.

### 6.12 Compatibilité avec `demo-scope.md`

Le smoke historique reste sur l'ancien chemin. `GIT_SYNC_ON_WRITE` non modifié. L'activation GitOps court-circuite l'event Kafka pour éviter la concurrence.

### 6.13 Coexistence avec le chemin legacy

| Flag | Chemin actif | Event `stoa.api.lifecycle` | `git_sync_worker` |
|---|---|---|---|
| `GITOPS_CREATE_API_ENABLED=false` (défaut) | Legacy DB-first | Émis | Consomme et écrit Git (avec bug B10) |
| `GITOPS_CREATE_API_ENABLED=true` | GitOps writer | **Non émis** par le POST | Inactif sur les writes GitOps |

Test Phase 5 : aucun event de type `created` émis lors d'un POST avec flag ON.

### 6.14 Politique de collision legacy — 3 catégories

#### Catégorie A — Sain adoptable (5 APIs `demo` : account-management-api, customer-360-api, fraud-detection-api, payment-api, petstore)

```
api_id = slug = api_name
git_path = "tenants/demo/apis/{slug}/api.yaml"
fichier Git présent
```

**Action** : ré-adoption autorisée Phase 6.5.
- Reconciler **remplit/corrige** : `git_commit_sha`, `catalog_content_hash`, `git_path` canonique
- `api_id` reste inchangé
- Aucune subscription/deployment/key mutée
- Smoke historique reste `REAL_PASS`

#### Catégorie B — Drift UUID dur (7 APIs `demo` : demo-api2, test, test2, test3, test5, toto-api, toto2)

```
api_id = UUID string  OU  git_path UUID-shaped
fichier Git réel = sous le slug
```

**Action par défaut** : **détection seulement, aucune réparation automatique**.

Justification : `subscriptions.api_id`, `deployments.api_id`, gateway routes, API keys référencent potentiellement le UUID. La migration relève d'un cycle séparé qui devra identifier toutes les FK et choisir une stratégie.

**Exception reconciler 2026-05-02** : lorsque le fichier Git canonique existe et
que la DB n'a pas de row `(tenant, api_id=slug)` mais a une unique row active
`(tenant, api_name=slug, version)`, le reconciler adopte cette row en place :
`api_catalog.id` reste stable, `api_id/git_path/git_commit_sha/catalog_content_hash`
deviennent canoniques, et les références souples connues sont mises à jour dans
la même transaction. Ce cas évite les `UNIQUE (tenant_id, api_name, version)` en
prod sans créer une seconde API. La migration 106 garantit que les anciennes rows
soft-deleted portant déjà le slug canonique ne bloquent pas cette adoption.

Comportement reconciler :
- `update_status(drift_detected, "uuid hard drift")`
- `last_error` documente : `api_id={UUID}, real_git_name={slug}`
- hors exception ci-dessus : **aucune mutation `api_catalog`, aucune écriture Git**

#### Catégorie C — Orphelin DB (1 API `demo` : banking-services-v1-2)

```
api_catalog row active (deleted_at IS NULL)
fichier Git absent à HEAD
```

**Action** : **détection seulement, aucune suppression automatique**.

Justification : auto-delete relève du cycle delete/prune (B11), pas de ce rewrite.

Comportement reconciler :
- `update_status(drift_orphan, "no git file at HEAD")`
- aucune mutation

#### Bascule Phase 10

Flag ON par défaut **uniquement** sur :
- tenants GitOps-initialized (`demo-gitops` + nouveaux)
- tenants explicitement classés clean par audit SQL préalable (toutes rows = catégorie A)

Tenants contenant des catégories B ou C non résolues restent sur l'ancien chemin.

**Verdict audit B14 (CAB-2193, exécuté 2026-04-27)** : scénario **β — drift sur 2-3 tenants minoritaires** (PAS γ systémique, PAS α isolé `demo`). Détail dans §11. Hypothèse défensive γ levée.

#### Catégorie D — Pré-GitOps DB-only (nouveau, surfacé par B14)

```
api_catalog row active
git_path IS NULL ET git_commit_sha IS NULL
```

13 rows détectées par l'audit B14 (12 sur `demo` + 1 sur `oasis`). Ces rows sont antérieures à l'introduction du writer GitOps : `git_sync_worker` legacy n'a jamais résolu de pointeur Git pour elles. Distinct de cat C (cat C a `git_path` rempli mais fichier absent à HEAD).

**Action** : **détection seulement, aucune réparation automatique** (mêmes raisons que cat B/C — FK potentielles vers `api_id` slug).

Comportement reconciler :
- `update_status(drift_pre_gitops, "no git_path nor commit pointer")`
- aucune mutation `api_catalog`, aucune écriture Git
- ces tenants restent exclus de Phase 10 jusqu'à cycle migration séparé

## 7. Critère de succès final

### §7 — Test GitOps create propre (sur `demo-gitops`)

```bash
TENANT=demo-gitops
NAME=manual-test-$(date +%s)   # nom unique par run, contournement B-INDEX

# 1. Construire api.yaml à la main
python -m control_plane_api.services.catalog.write_api_yaml \
  --tenant ${TENANT} --name ${NAME} --version 1.0.0 \
  --backend http://mock-backend:9090 \
  --output /tmp/api.yaml

# 2. Push direct dans stoa-catalog via PyGithub
gh api -X PUT "repos/stoa-platform/stoa-catalog/contents/tenants/${TENANT}/apis/${NAME}/api.yaml" \
  -f message="manual: add ${NAME}" \
  -f content="$(base64 < /tmp/api.yaml)"

# 3. Attendre le reconcile
sleep 30

# 4. Vérifier api_catalog
curl -s ${API_URL}/v1/tenants/${TENANT}/apis/${NAME}

# 5. Vérifier git_path canonique et git_commit_sha rempli
psql $DATABASE_URL -c "SELECT api_id, api_name, git_path, git_commit_sha, catalog_content_hash \
  FROM api_catalog WHERE tenant_id='${TENANT}' AND api_id='${NAME}' AND deleted_at IS NULL;"
# git_path = "tenants/demo-gitops/apis/${NAME}/api.yaml"
# git_commit_sha non NULL, catalog_content_hash non NULL

# 6. Vérifier read_at_commit (le path stocké pointe vers un fichier réel)
COMMIT=$(psql -tAc "SELECT git_commit_sha FROM api_catalog WHERE ...")
gh api "repos/stoa-platform/stoa-catalog/contents/tenants/${TENANT}/apis/${NAME}/api.yaml?ref=${COMMIT}"

# 7. Drift hostile sur backend_url
psql -c "UPDATE api_catalog SET tags='[]'::jsonb WHERE ..."
sleep 30
psql -c "SELECT tags FROM api_catalog WHERE ..."
# → revenu à la valeur Git

# 8. Drift hostile sur git_path (reproduction du bug B10)
psql -c "UPDATE api_catalog SET git_path='tenants/${TENANT}/apis/00000000-0000-0000-0000-000000000000/api.yaml' WHERE ..."
sleep 30
psql -c "SELECT git_path FROM api_catalog WHERE ..."
# → revenu à "tenants/${TENANT}/apis/${NAME}/api.yaml"

# 9. Smoke complet vert
GITOPS_CREATE_API_ENABLED=true \
TENANT_ID=${TENANT} \
DEMO_UAC_CONTRACT=specs/uac/demo-httpbin.uac.json \
./scripts/demo-smoke-test.sh
# → REAL_PASS — DEMO READY
```

### §7bis — Ré-adoption contrôlée des APIs saines (catégorie A) du tenant `demo`

Borné aux **5 APIs catégorie A uniquement** (`account-management-api`, `customer-360-api`, `fraud-detection-api`, `payment-api`, `petstore`).

```bash
for API_NAME in account-management-api customer-360-api fraud-detection-api payment-api petstore; do
  GIT_PATH=$(psql -tAc "SELECT git_path FROM api_catalog \
    WHERE tenant_id='demo' AND api_id='${API_NAME}' AND deleted_at IS NULL;")
  EXPECTED="tenants/demo/apis/${API_NAME}/api.yaml"
  [ "${GIT_PATH}" = "${EXPECTED}" ] || fail "git_path drift for ${API_NAME}"

  COMMIT=$(psql -tAc "SELECT git_commit_sha FROM api_catalog WHERE ...")
  [ -n "${COMMIT}" ] || fail "git_commit_sha NULL for ${API_NAME}"

  HASH=$(psql -tAc "SELECT catalog_content_hash FROM api_catalog WHERE ...")
  [ -n "${HASH}" ] || fail "catalog_content_hash NULL for ${API_NAME}"

  gh api "repos/stoa-platform/stoa-catalog/contents/${GIT_PATH}?ref=${COMMIT}" \
    > /dev/null || fail "read_at_commit 404 for ${API_NAME}"

  YAML=$(gh api "repos/.../contents/${GIT_PATH}?ref=${COMMIT}" -H "Accept: application/vnd.github.raw")
  GIT_BACKEND=$(echo "${YAML}" | yq '.backend_url')
  DB_BACKEND=$(psql -tAc "SELECT backend_url FROM api_catalog WHERE ...")
  # Note : backend_url n'est pas une colonne de api_catalog ; vérification via metadata
  # ou via re-projection. Ajustement Phase 5.
done

# Vérification : les 7 catégorie B et l'orphelin C sont INCHANGÉS
psql -c "SELECT api_id, git_path FROM api_catalog \
  WHERE tenant_id='demo' AND api_id ~ '^[0-9a-f]{8}-' AND deleted_at IS NULL;"
# → 7 rows toujours présentes avec git_path UUID

psql -c "SELECT api_id FROM api_catalog WHERE tenant_id='demo' AND api_id='banking-services-v1-2';"
# → row toujours présente, deleted_at toujours NULL

# Smoke historique reste REAL_PASS
./scripts/demo-smoke-test.sh
```

**Garanties §7bis** :
- 7 catégorie B inchangées
- Orphelin C inchangé
- Aucune subscription/deployment/key mutée
- Smoke historique vert

## 8. Risques identifiés et mitigations

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| Hypothèses v0.3.1 ré-introduites par habitude (UUID5, worktree, table `apis`) | Moyen | Haut | §0 explicite. Test scaffold Phase 3 vérifie absence de `uuid5` et `worktree` dans le nouveau code. |
| Concurrence Git entre nouveau writer et `git_sync_worker` legacy | Haut | Haut | §6.13 : flag ON court-circuite l'event Kafka. Test Phase 5. |
| Réparation accidentelle des UUID driftés (catégorie B) | Moyen | Critique | §6.14 explicite : détection seulement. Test Phase 5 vérifie. |
| Suppression accidentelle d'orphelins (catégorie C) | Faible | Critique | §6.14 : pas de delete dans ce rewrite. Garde-fou §9.13. |
| `git_path = UUID` re-introduit | Faible | Haut | §6.5 étape 2+6 + §6.6 : refus UUID-shaped. Test §7 étape 8. B10 fixé Phase 8 (in-scope partiel). |
| Phase 6.5 mute des subscriptions/deployments par effet de bord | Faible | Critique | §6.14 catégorie A : `api_id` inchangé. §6.9 : `target_gateways` non écrit et `openapi_spec` dérivé uniquement de Git. Test §7bis vérifie. |
| Confusion entre les 5 niveaux d'identité | Moyen | Haut | §6.4. Garde-fou §9.14. |
| INSERT/adoption bloqué par `uq_api_catalog_tenant_api` après soft-delete précédent | Observé en prod `free-aech` le 2026-05-02 | P0 | Migration 106 supprime la contrainte globale et conserve `ix_api_catalog_tenant_api_active`. Test de régression: adoption avec slug canonique soft-deleted. |
| Drift UUID systémique au-delà de `demo` | Inconnu (SQL b à lancer) | Haut | Hypothèse défensive γ Phase 10. Bascule limitée. |
| Sync engine ne soft-delete pas les fichiers Git disparus (B11) | Confirmé | Moyen | Out-of-scope complet. Documenté dans §0. Cycle delete/prune séparé. |
| Le rewrite déborde sur update/delete sous pression | Haut | Haut | Règle §4.3 + §4.2 out-of-scope étendu. |

## 9. Garde-fous spécifiques

1. **Aucune ADR créée pendant Phases 0-7** sauf décision irréversible.
2. **Aucun fix pendant Phases 1-2.** Tout bug observé va dans le backlog.
3. **Aucun refactor cosmétique.**
4. **Smoke = gate démo non négociable + tests GitOps = gates de merge.** Tests dédiés couvrent : parité advisory_lock_key, 3 cas idempotents, drift detection complète incluant `git_path`+`read_at_commit`, atomicité commit GitHub, validation path↔content, mapping payload→YAML déterministe, refus UUID-shaped, classification 3 catégories legacy.
5. **Pas de skill Claude Code créée avant Phase 4.**
6. **Interdiction d'utiliser `GIT_SYNC_ON_WRITE`** dans le nouveau chemin.
7. **Le payload HTTP ne projette jamais.** Test scaffold Phase 3 : `project_to_api_catalog` accepte uniquement un type `CommittedContent` produit par `read_at_commit`.
8. **Aucun champ métier DB-only mutable** pour les APIs GitOps-created.
9. **Cette spec ne remplace pas `demo-scope.md`.** Exception contrôlée (§6.12).
10. **Pas de `uuid5(...)`, pas de `git worktree`, pas de table `apis`** dans le code de ce rewrite.
11. **Event Kafka `stoa.api.lifecycle` non émis quand flag ON.**
12. **`catalog_content_hash` suffit pour l'idempotence.** Pas de blocker `uac_spec_hash`.
13. **Pas de delete dans ce rewrite.** Aucune suppression de row, même catégorie C. Status `drift_orphan`, jamais `DELETE`.
14. **Aucun ID gateway/runtime/PK interne ne devient `api_id` catalogue.**
15. **Pas de réparation automatique des catégories B et C.** Détection + ticket Phase 2 uniquement.
16. **Unicité catalogue active-only.** `uq_api_catalog_tenant_api` global est interdit ; seul `ix_api_catalog_tenant_api_active` peut porter l'unicité de routage. Le sync engine B11 reste hors scope.

## 10. Liens avec l'écosystème specs

- Source de vérité scope démo : [`demo-scope.md`](./demo-scope.md)
- Tests d'acceptance figés : [`demo-acceptance-tests.md`](./demo-acceptance-tests.md) AT-1
- Contrats HTTP figés : [`architecture-rules.md`](./architecture-rules.md) §2.1, §2.2bis
- Garde-fous transverses : [`rewrite-guardrails.md`](./rewrite-guardrails.md)
- Format UAC : [`uac/README.md`](./uac/README.md)
- Démo client/prospect (cycle séparé) : [`client-prospect-demo-scope.md`](./client-prospect-demo-scope.md)
- Flow déploiement runtime (cycle séparé) : [`api-deployment-flow.md`](./api-deployment-flow.md)
- Audit Phase 1 : `specs/audits/2026-04-26-api-creation-current-state/`
- Diagnostic SQL terrain : §0 de cette spec

## 11. Sortie de ce rewrite

Conditions pour clôturer cette spec et la passer en statut *Référence* :

1. Phases 0 à 10 toutes terminées avec critère de fin validé
2. Test §7 + §7bis passent en CI sur 5 runs consécutifs
3. Le flag `GITOPS_CREATE_API_ENABLED` est `true` par défaut sur tous les **tenants éligibles** (cf. politique de bascule ci-dessous) depuis ≥ 7 jours
4. Aucun rollback déclenché pendant ces 7 jours
5. Le backlog `api-creation-rewrite-backlog` :
   - Tickets in-scope **fixed** avec test de régression (B10, bugs runtime)
   - Tickets out-of-scope **closed-documented/deferred** avec cycle cible (B11, migration B, prune C, backfill D)
6. Les 5 APIs catégorie A du tenant `demo` ont `git_path` canonique, `git_commit_sha` rempli, `catalog_content_hash` rempli, `read_at_commit` non-null
7. Les 7 catégorie B du tenant `demo`, les 3 catégorie B du tenant `free-aech`, l'orphelin C, et les 13 rows catégorie D sont marqués `drift_detected`, `drift_orphan` ou `drift_pre_gitops` avec `last_error` documenté
8. **B11** est référencé par un ticket explicite dans le backlog du futur cycle delete/prune
9. **Les rows catégorie D** sont référencées par un ticket explicite dans le backlog du futur cycle backfill

Une fois clôturée, cette spec sert de pattern de référence pour les rewrites GitOps suivants.

### 11.1 Bascule Phase 10 — Politique audit-informed

**Verdict B14** (CAB-2193, exécuté 2026-04-27) : scénario **β confirmé** — drift sur 3/6 tenants actifs. Hypothèse défensive γ levée.

#### Tenants éligibles à l'activation GitOps create par défaut

| Tenant | Rows actives | Statut |
|---|---:|---|
| `banking-demo` | 1 | ✅ Éligible |
| `high-five` | 4 | ✅ Éligible |
| `ioi` | 3 | ✅ Éligible |
| `demo-gitops` (futur) | — | ✅ Éligible par construction |

Soit 8 rows actives sur 42 (~19%) dans des tenants immédiatement éligibles à l'activation du chemin GitOps create par défaut.

#### Tenants exclus de la bascule

| Tenant | Rows | Motif | Cycle de résolution |
|---|---:|---|---|
| `demo` | 25 | 7 cat B (UUID drift) + 12 cat D (pré-GitOps) | Migration legacy + backfill |
| `free-aech` | 6 | 3 cat B (UUID drift) | Migration legacy |
| `oasis` | 3 | 1 cat D (pré-GitOps) | Backfill |

#### Politique de bascule

1. `GITOPS_CREATE_API_ENABLED=true` est activé par défaut **uniquement** sur les tenants éligibles ci-dessus.
2. Les nouveaux tenants créés post-Phase 10 sont éligibles **par construction** si le flow §6.5 refuse les `api_name` UUID-shaped (étape 2) et projette un `git_path` canonique depuis le fichier Git réel (étapes 6+12).
3. Les tenants exclus restent sur l'ancien chemin DB-first jusqu'à résolution de leur cycle cible : migration legacy (cat B) ou backfill (cat D).
4. Phase 6.5 (CAB-2189) cible **spécifiquement** les 5 APIs catégorie A du tenant `demo`. Elle n'affecte aucune autre row.
5. **Cette bascule n'est pas une migration automatique des lignes existantes** : elle active le nouveau chemin de création GitOps pour les tenants éligibles. Les rows pré-existantes des tenants exclus ne sont **jamais** touchées par ce rewrite.

#### Pattern UUID drift uniforme (cat B)

L'audit B14 a confirmé que sur les 10 rows catégorie B identifiées (7 sur `demo`, 3 sur `free-aech`), **toutes** ont à la fois :

- `api_id` UUID-shaped
- `git_path` UUID-shaped (`tenants/{tid}/apis/{UUID}/api.yaml`)

Aucune variante "UUID `api_id` avec `git_path` canonique" n'a été observée. La catégorie B (§6.14) reste donc uniforme : `UUID hard drift`.

La migration des catégories B sur `demo` et `free-aech` est hors scope du rewrite create-api. Elle relève d'un cycle legacy migration séparé.

#### Note sur les tenants partiels

`oasis` a 2 rows saines (cat A) et 1 row cat D. Dans ce rewrite, le tenant entier est **exclu** de la bascule par défaut, même si 2 de ses 3 rows sont saines. Justification : la complexité d'un mode mixte par-row n'est pas justifiée pour ce cycle. Une fois la row cat D résolue par le cycle backfill, `oasis` deviendra éligible automatiquement.

## 12. Révisions

| Date | Version | Auteur | Delta |
|---|---|---|---|
| 2026-04-26 | v0.1-v0.3.1 DRAFT | Claude + ChatGPT rounds 1-3 | Construction itérative doctrine GitOps |
| 2026-04-26 | v1.0 (refusée) | Claude après round 4 | Architecture théorique idéale, refusée car non alignée code réel |
| 2026-04-26 | v0.4 DRAFT | Claude après audit Phase 1 + round 5 | `apis` → `api_catalog`, retrait UUID5, retrait worktree, layout conservateur, `CatalogGitClient` PyGithub-first, worker asyncio in-tree |
| 2026-04-26 | v1.0 DRAFT (intermédiaire) | Claude après round 6 + diagnostic SQL terrain (drift 5/7/1) | §0 drift terrain, 6e invariant `git_path` réel, 4 niveaux d'identité, §6.14 3 catégories non-destructives, Phase 6.5, §7bis borné catégorie A, B10 backlog |
| 2026-04-26 | **v1.0 (finale)** | Claude après `\d api_catalog` réel + round 7 | (1) Schéma `api_catalog` réel intégré §6.3 — `git_path` et `git_commit_sha` existent déjà, seule colonne ajoutée = `catalog_content_hash` ; (2) 5 niveaux d'identité §6.4 (ajout `api_catalog.id` PK UUID interne, probable source du bug B10 si fuite) ; (3) B11 (sync engine ne soft-delete pas les fichiers Git disparus) cadré out-of-scope complet ; (4) B-INDEX (`uq_api_catalog_tenant_api` dangereux, hérité) cadré out-of-scope complet ; (5) Phase 8 reformulée : "in-scope fixed + out-of-scope deferred" pour ne pas bloquer le rewrite sur B11 ; (6) §6.5 étape 14 : non-écrasement explicite de `target_gateways` ; (7) §6.9 mapping enrichi avec colonnes réelles (`audience`, `portal_published`, `metadata`, etc.) ; (8) §7 test utilise `manual-test-${TIMESTAMP}` unique pour contourner B-INDEX ; (9) §0 drift terrain documenté avec 5 bugs structurels nommés ; (10) Hypothèse défensive γ par défaut sur Phase 10 (à ajuster après SQL globale lancée en parallèle). **Spec exécutable Phase 2 → Phase 3.** |
| 2026-05-02 | v1.1 | Codex après audit prod `free-aech` | B-INDEX résolu: migration 106 supprime `uq_api_catalog_tenant_api` global, garde l'unicité active-only et ajoute un test de régression pour l'adoption d'une row UUID active quand le slug canonique existe seulement en soft-delete. |

## 12.1 Phase 6 closure (LIVE 2026-04-27)

Phase 6 strangler activated on OVH prod for tenant `demo-gitops`. The full chain
(stoa-catalog GitHub → reconciler tick → `api_catalog` projection) is proven in
production.

### Activation chain

| PR | Repo | Purpose |
|---|---|---|
| stoa-infra #63 | infra | Alembic `PreSync` Job in chart — applies migrations 096 + 097 |
| stoa-infra #64 | infra | First flag flip (broken — CSV value tripped pydantic-settings JSON decode) |
| stoa-infra #65 | infra | JSON-array fix: `GITOPS_ELIGIBLE_TENANTS: '["demo-gitops"]'` |
| stoa #2613 | code | `git_service` singleton made provider-aware (CAB-2197) — unblocks reconciler |
| stoa-infra `16f0be1` | infra | Image tag bump to `dev-ec9da59d` (PR #2613 deployed) |

Two ops gotchas surfaced and are now in memory for the next strangler:

1. `GITOPS_ELIGIBLE_TENANTS` (typed `list[str]`) must be a JSON array string in
   env, not a CSV. The `@field_validator(mode="before")` does not see the raw
   env value — `pydantic_settings.EnvSettingsSource.decode_complex_value` runs
   first and json-fails on `"demo-gitops"`. Tighten the docstring in a
   follow-up.
2. ArgoCD `PreSync` hooks only fire during a sync **operation**, not on a
   `refresh=hard` annotation. Adding a hook-only template (no diff in the
   tracked Deployment/Service/Ingress) reconciles to `Synced` without firing
   the hook. Trigger the first run with
   `kubectl patch application <app> --type merge -p '{"operation":{"sync":{}}}'`.
   Subsequent syncs fire the hook normally as part of any operation.

### Evidence (§7 manual smoke)

```
api_id              = manual-test-1777312098
api_name            = manual-test-1777312098
version             = 1.0.0
status              = active
git_path            = tenants/demo-gitops/apis/manual-test-1777312098/api.yaml
git_commit_sha      = 8ba68bb54086541995e4b5272d92f64c0efd67e1   ← matches gh api PUT
catalog_content_hash = 8763431733a1c15fcd0fff844625942048e980ce11be0e69a788ed644b43f04c
is_active           = true
synced_at           = 2026-04-27 17:49:38 UTC
```

Projection landed 44 s after the catalog PUT, well within
`CATALOG_RECONCILE_INTERVAL_SECONDS=10`. The `git_commit_sha` stored in
`api_catalog` is the exact commit returned by `gh api PUT` — proof the
reconciler reads the commit from GitHub Contents API and pins it, instead of
re-deriving it.

Residual fixture left in place intentionally per **B11 deferred** (CAB-2191):
the `manual-test-1777312098` file + DB row remain in prod as a future cycle
input for delete/prune.

### Steady-state observation

First hour after activation:

| Pod | `iteration_failed` | `Catalog reconciler started` markers | `catalog_sync_status` ticks |
|---|---|---|---|
| `5cc9b9ff75-bccsq` | 0 | 2 | 355 |
| `5cc9b9ff75-s7xlz` | 0 | 2 | 385 |

ArgoCD `Synced/Healthy` on rev `16f0be1`. cp-api image `dev-ec9da59d` rolling
on both replicas, 0 restarts.

### What this unlocks

- **Phase 6.5** (CAB-2189) — controlled re-adoption of 5 healthy category-A
  APIs from the `demo` tenant.
- **Phase 10** — broader rollout per CAB-2193 B14 audit verdict β: eligible
  tenants are `banking-demo`, `high-five`, `ioi`, `demo-gitops` (excluding
  `demo`, `free-aech`, `oasis` for the reasons in §11).

### What is still open

- **B11** (CAB-2191) — sync engine no soft-delete. Out-of-scope of this
  rewrite; required for the eventual delete/prune cycle. The §7 fixture row
  becomes a natural test input.
- Code follow-up on `control-plane-api/src/config.py:269-278` — drop the
  misleading "Comma-separated env var" claim from the
  `GITOPS_ELIGIBLE_TENANTS` docstring or wire a custom env source if CSV is
  the desired contract.
