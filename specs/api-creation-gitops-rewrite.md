# STOA Rewrite — API Creation GitOps

> **Statut**: v1.0 — 2026-04-26. Validée pour exécution Phase 1.
> **Owner**: humain (Christophe). Les agents n'élargissent pas ce scope sans décision écrite.
> **Périmètre**: rewrite ciblé du chemin de création d'API (`POST /v1/tenants/{tid}/apis`) vers un modèle GitOps avec UAC en Git comme source de vérité.
> **Hors périmètre**: update, publish, promote, delete API. Tout ça fera l'objet d'un cycle séparé après stabilisation de la création.
> **Invariant directeur**: à chaque phase, `./scripts/demo-smoke-test.sh` doit rester `REAL_PASS — DEMO READY`. Cf. [`rewrite-guardrails.md`](./rewrite-guardrails.md) §1.

## 1. Pourquoi ce rewrite

Aujourd'hui, `POST /v1/tenants/{tid}/apis` est un endpoint impératif :
- valide le payload
- écrit en DB
- (selon flags) propage vers `stoa-catalog` Git
- (selon flags) déclenche un sync gateway

Les side-effects sont éparpillés dans la route FastAPI, la DB est de facto la source de vérité, et `GIT_SYNC_ON_WRITE` est désactivé pour la démo (`demo-acceptance-tests.md` AT-0). Conséquence : on tourne en rond sur des bugs transverses (drift DB ↔ gateway, états incohérents subscription/route, race conditions multi-agents HEGEMON).

Ce rewrite applique les principes OpenGitOps **uniquement à la création d'API**, en réutilisant l'infrastructure UAC déjà en place (cf. [`uac/README.md`](./uac/README.md), ADR-067).

## 2. Doctrine — adaptée à STOA

Cinq invariants tirés d'OpenGitOps, reformulés dans le vocabulaire STOA :

1. **UAC en Git = desired state.** Un `UAC contract` versionné dans `stoa-catalog` est la vérité. La DB est un read model / index opérationnel, pas la source.
2. **FastAPI ne projette jamais depuis le payload HTTP.** La route `POST /v1/tenants/{tid}/apis` valide, écrit un commit dans `stoa-catalog`, puis projette vers DB en utilisant **le contrat tel qu'il a été committé sur le remote**, jamais le payload HTTP entrant ni un fichier local non poussé.
3. **Reconcilers idempotents.** Rejouer N fois le sync d'un commit `abc123` produit le même état (DB + gateway). L'idempotence est portée par `spec_hash` (déjà présent dans UAC, calcul figé en §6.2.1).
4. **Drift détecté par comparaison de projection complète.** Le drift se mesure entre la projection attendue depuis Git (`render_db_projection(contract)`) et la ligne réelle de la table `apis`, **pas** par simple comparaison de hash. Une falsification d'un champ projeté qui ne change pas le hash stocké doit être détectée. Cf. §6.6.
5. **Reconstructibilité.** Si on supprime la table `apis`, on doit pouvoir la reconstruire intégralement depuis `stoa-catalog`. Donc tous les champs persistants (y compris `api_id` et `display_name`) sont déterministes ou dérivés du UAC. Aucun champ DB-only mutable pour les APIs créées via GitOps. Cf. §6.4 et §6.10.

Règle qui découle des cinq, étendant la doctrine ADR-067 :

> **UAC describes. Git stores. Reconciler projects. Payload never projects. Smoke proves.**

La ligne « Payload never projects » est le garde-fou anti-faux-GitOps. Elle interdit le pattern dual-write classique où la DB serait écrite depuis le payload HTTP en parallèle de Git, et elle interdit aussi de projeter depuis un fichier local non poussé sur le remote.

## 3. Contrats figés — non négociables

Ce rewrite ne casse aucun de ces contrats. Une PR qui les touche = NO-GO automatique (cf. [`rewrite-guardrails.md`](./rewrite-guardrails.md) §2).

| Contrat | Source | Pourquoi figé |
|---|---|---|
| `POST /v1/tenants/{tid}/apis` → 201 + `{id, name}` | [`architecture-rules.md`](./architecture-rules.md) §2.1 | AT-1 du smoke en dépend |
| `GET /v1/tenants/{tid}/apis/{id}` → 200 + `{id, name, backend_url}` | [`architecture-rules.md`](./architecture-rules.md) §2.1 | AT-1 du smoke en dépend |
| Schéma UAC v1 (JSON Schema + Pydantic + Rust) | [`uac/README.md`](./uac/README.md) | Parité cross-langage déjà enforced |
| `spec_hash` calculé identiquement Python/Rust selon §6.2.1 | [`uac/demo-httpbin.uac.json`](./uac/demo-httpbin.uac.json) | Idempotence du reconciler en dépend |
| Verdict `REAL_PASS — DEMO READY` du smoke | [`demo-acceptance-tests.md`](./demo-acceptance-tests.md) | Garde-fou universel |

## 4. Périmètre exact de ce rewrite

### 4.1 In-scope

- Endpoint `POST /v1/tenants/{tid}/apis` (création uniquement)
- Module Python nouveau dans `control-plane-api/src/services/gitops_writer/`
- Worker Python séparé `control-plane-api/src/services/catalog_reconciler/` (process distinct, cf. §6.6)
- Repo `stoa-catalog` en mode read+write par cp-api via un nouveau pipeline GitOps (pas de réutilisation de `GIT_SYNC_ON_WRITE`, cf. §9.6)
- Support d'un remote Git local `file://` pour la démo, pas de dépendance GitHub externe en local (cf. §6.12)
- Layout des contrats UAC dans `stoa-catalog` figé en §6.1
- Migration Alembic additive : ajout de colonnes `apis.spec_hash` et `apis.source_commit_sha` (cf. §6.6)
- Projection `stoa-catalog → DB` pour la table `apis` uniquement (target=`db`)
- Endpoint `GET /v1/tenants/{tid}/apis/{id}/sync-status` (nouveau, optionnel pour la démo)
- Feature flag `GITOPS_CREATE_API_ENABLED` par tenant
- Lock distribué pour les writes Git (cf. §6.7)
- Isolation des working trees Git (cf. §6.11)
- Helper CLI `control_plane_api.services.uac.write_canonical_contract` pour produire un fichier UAC avec `spec_hash` correct, utilisé par le test §7. Doit réutiliser la fonction `compute_spec_hash` existante du module UAC (cf. [`uac/README.md`](./uac/README.md)) ; emplacement exact confirmé par audit Phase 1.
- Mapping déterministe payload HTTP → UACContract (cf. §6.13)
- Politique de collision avec les APIs legacy (cf. §6.14)

### 4.2 Out-of-scope (refus automatique)

- `PATCH/PUT /v1/tenants/{tid}/apis/{id}` (update)
- `DELETE /v1/tenants/{tid}/apis/{id}`
- Promotion dev/staging/prod (la valeur unique `demo` suffit, cf. §6.1)
- Publication portail (CPD-* dans [`client-prospect-demo-scope.md`](./client-prospect-demo-scope.md), cycle séparé)
- Projection `stoa-catalog → gateway routes` (target=`gateway`, cycle séparé, géré par AT-2)
- Projection `stoa-catalog → portal` (target=`portal`, cycle séparé)
- Refactor des subscriptions, applications, deployments (AT-2/3 du smoke, cycle séparé)
- Migration vers un nouveau format de manifest (UAC reste le format)
- Multi-repo, multi-org GitHub
- ArgoCD / Flux (le reconciler reste un worker Python interne à cp-api, pas d'intro K8s natif à ce stade)
- Optimisation du scan worker pour 1000+ APIs (la boucle scanne tout `stoa-catalog` ; backlog Phase 2)
- Extension du schéma UAC (ajout de champs comme `display_name` au UAC v1) — cycle séparé qui touche la parité Python/Rust
- Migration des APIs legacy (créées hors GitOps) vers `api_id` déterministe — cycle séparé
- Décision d'identité multi-env (`api_id` catalogue global vs env-scoped) — cycle promotion (cf. §6.4 note)

### 4.3 Règle d'or de scope

Si pendant l'exécution une question type *« et si on en profitait pour... »* émerge, la réponse par défaut est **NON**. La question va dans le bug inventory de Phase 2 et sera traitée dans un cycle ultérieur.

## 5. Plan d'exécution — phases séquentielles

| Phase | Livrable | Critère de fin | Durée cible |
|---|---|---|---|
| 0 | **Cette spec validée** | Christophe valide v1.0 | ½ jour |
| 1 | `specs/audits/2026-XX-XX-api-creation-current-state/` | Le chemin actuel est tracé, emplacement exact de `compute_spec_hash` confirmé, contraintes uniques sur `apis` documentées (cf. §6.14), zéro modif code | 1 jour |
| 2 | Backlog Linear `label:api-creation-rewrite-backlog` | ≥ 10 tickets, zéro fix | 1 jour (parallèle Phase 1) |
| 3 | Layout `stoa-catalog` + interface `gitops_writer` figés dans cette spec §6 | PR mergeable scaffold, CI verte, `NotImplementedError` partout, migration Alembic prête, helper `write_canonical_contract` scaffold | 1 jour |
| 4 | Implémentation `gitops_writer.create_api()` + worker `catalog_reconciler` + helper `write_canonical_contract` + mapping payload→UAC | `python -m gitops_writer.create_api ...` produit un commit visible ; worker boucle et projette ; helper produit un UAC canonique vérifiable ; AT-1 payload accepté et converti en UAC | 2-3 jours |
| 5 | Tests isolés des deux modules | Couverture 100% des chemins, parité `spec_hash` Python/Rust, drift detection par projection complète, push remote atomicité, workspace isolation, advisory_lock_key stabilité, mapping payload→UAC déterministe, legacy collision rejection | 1 jour |
| 6 | **Commit-first projection** dans `POST /v1/tenants/{tid}/apis` derrière flag, sur tenant `demo-gitops` propre | Sur tenant `demo-gitops`, le POST commit Git puis projette DB depuis le contrat relu via `git show`. AT-1 reste vert. Tenant `demo` historique reste sur l'ancien chemin. | 1-2 jours |
| 7 | Re-run du smoke avec flag ON sur tenant `demo-gitops` | `GITOPS_CREATE_API_ENABLED=true ./scripts/demo-smoke-test.sh` = `REAL_PASS` ; remote Git local `file://` suffit | 1 jour |
| 8 | Fix du backlog Phase 2 | 100% des tickets soit closed-resolved, soit fixed avec test de régression | variable |
| 9 | Re-run smoke + régression + test §7 du commit Git manuel + drift hostile | Toutes métriques Phase 7 maintenues, test §7 passe entièrement | ½ jour |
| 10 | Bascule limitée aux tenants GitOps-initialized | Flag ON par défaut sur les tenants GitOps-initialized uniquement, ancien chemin en log-only sur ces tenants, doc de rollback. **Tenants legacy non migrés restent sur l'ancien chemin** (cf. §6.14) | ½ jour |

**Total estimé** : 10-13 jours calendaires. Avec AI Factory : 5-7 jours réels.

## 6. Contrat technique

### 6.1 Layout `stoa-catalog`

```
stoa-catalog/
  tenants/
    {tenant_id}/
      environments/
        {environment}/
          apis/
            {api_name}.uac.json
  README.md
```

Contraintes de forme :
- `{tenant_id}` : slug minuscule `[a-z0-9-]+`, sanitisé avant écriture
- `{environment}` : seule valeur autorisée pendant ce cycle = `demo`
- `{api_name}` : slug minuscule `[a-z0-9-]+`, pas de `..`, pas de `/`
- Le chemin segmenté par environnement est figé maintenant pour éviter une migration au prochain cycle (promotion dev/staging/prod), même si une seule valeur est acceptée aujourd'hui

### 6.2 Interface `gitops_writer`

```python
class GitOpsWriter:
    def create_api(
        self,
        tenant_id: str,
        environment: str,    # forcé à "demo" pendant ce cycle
        contract: UACContract,
        actor: str,
    ) -> CreateApiResult:
        """
        Idempotent par spec_hash. Trois cas figés :

        Case A — fichier UAC absent dans Git :
          → write file, commit, push remote
          → projection DB depuis le contrat relu via git show {sha}:{path}
          → return CreateApiResult(api_id, spec_hash, commit_sha,
                                   status="committed", case="created")

        Case B — fichier UAC présent avec même spec_hash :
          → no-op Git
          → projection DB depuis le contrat relu via git show {sha_existing}:{path}
            (Permet aux retry HTTP de réussir si la projection DB avait échoué
             sans avoir à re-commit)
          → return CreateApiResult(api_id, spec_hash, commit_sha_existing,
                                   status="committed", case="idempotent")

        Case C — fichier UAC présent avec spec_hash différent :
          → raise GitOpsConflictError
          → ne touche ni Git ni DB
          → l'appelant HTTP retourne 409 Conflict
        """
```

Pas de méthodes `update_api`, `delete_api`, `promote_api` à ce stade (out-of-scope §4.2).

### 6.2.1 Calcul canonique de `spec_hash`

Pour éviter toute auto-référence (le hash est lui-même un champ du contrat) et toute divergence Python/Rust, le calcul est figé :

```
spec_hash = sha256_hex(canonical_json(contract MINUS field "spec_hash"))
```

Règles du JSON canonique :
- `sort_keys=True`
- `separators=(",", ":")` (pas d'espaces)
- encodage UTF-8
- floats sérialisés en représentation minimale stable (cf. RFC 8785 ou implémentation existante UAC)
- aucun champ volatil ne doit influencer le hash (timestamps, ids générés à la volée, etc.)

Discipline du reconciler :
- Le reconciler **ne fait jamais confiance** au `spec_hash` embarqué dans le fichier UAC
- Il recalcule le hash à chaque lecture et compare
- Si `embedded_hash != recalculated_hash` : `status='failed'`, `last_error="spec_hash mismatch"`, **aucune projection DB**

Cette règle protège contre une corruption ou une falsification du fichier UAC dans Git.

### 6.3 Statut de sync

Stocké en DB dans une nouvelle table `api_sync_status` :

```
api_sync_status
- tenant_id              str
- environment            str
- api_id                 uuid (déterministe, cf. §6.4)
- api_name               str
- target                 enum(db, gateway, portal)
- desired_commit_sha     varchar(64)    (commit du fichier UAC, cf. §6.5 étape 12)
- desired_spec_hash      varchar(64)
- observed_spec_hash     varchar(64) | null
- status                 enum(pending, syncing, synced, failed, drift_detected)
- last_error             text | null
- last_sync_at           timestamp

PRIMARY KEY (tenant_id, environment, api_id, target)
```

Pendant ce cycle, seul `target='db'` est utilisé. `gateway` et `portal` réservés pour les cycles suivants. Cette table est entièrement reconstructible depuis `stoa-catalog` + table `apis` (invariant §2.5).

**Note dimensionnement** : `varchar(64)` partout pour les commit SHA — accommode SHA-1 (40 chars) et future migration Git SHA-256 (64 chars) sans dette.

### 6.4 `api_id` déterministe

Pour respecter l'invariant de reconstructibilité (§2.5), `api_id` est dérivé de manière déterministe :

```python
import uuid

# Namespace dérivé une fois pour toutes via :
#   uuid.uuid5(uuid.NAMESPACE_DNS, "stoa.io/api/v1")
# Puis figé. Ne jamais recalculer avec une autre chaîne — rotation = casse tous les api_id.
STOA_API_NAMESPACE = uuid.UUID("c276f996-0520-5de1-ab27-83ab8749e086")

def compute_api_id(tenant_id: str, environment: str, api_name: str) -> uuid.UUID:
    return uuid.uuid5(STOA_API_NAMESPACE, f"{tenant_id}:{environment}:{api_name}")
```

Exemples vérifiables (calcul reproductible) :
```
compute_api_id("demo", "demo", "demo-httpbin") = d5844819-0eab-5ebf-baa2-6ff5c27ea29d
compute_api_id("demo", "demo", "manual-test")  = aa50c822-2ef4-59bc-afe1-d428fb92f03b
```

Conséquences :
- `GET /v1/tenants/{tid}/apis/{id}` continue de fonctionner avec un UUID
- Pas besoin de stocker l'`id` dans le UAC contract
- Reconstruire la table `apis` depuis `stoa-catalog` est mécanique
- Aucun `id` aléatoire DB-generated n'est créé pour les APIs créées via le chemin GitOps

**Note multi-env (cycle promotion)** :
> Le choix `api_id = uuid5(tenant_id:environment:api_name)` est figé uniquement pour le cycle create API avec `environment=demo`. Il ne constitue pas encore une décision multi-env pour dev/staging/prod.
> Le cycle promotion devra trancher explicitement entre :
> - **Identité catalogue globale** : un `api_id` unique par `(tenant, name)`, plus des overlays par environnement projetés vers `GatewayDeployment` (cf. [`api-deployment-flow.md`](./api-deployment-flow.md))
> - **Identité env-scoped** : un `api_id` distinct par environnement, sémantique actuelle
> Ce choix n'est pas pris dans cette spec.

### 6.5 Flow détaillé `POST /v1/tenants/{tid}/apis` avec flag ON

```
 1. Valider payload HTTP (Pydantic schema)
 2. Normaliser tenant_id, environment="demo", api_name (slug)
 3. Convertir payload → UACContract via le mapping figé (cf. §6.13)
 4. **Validation projectabilité DB** (refus pré-Git) :
       - tous les endpoints partagent le même backend_url
         sinon → 422 Unprocessable Entity, last_error="multiple backend_url",
                 aucune écriture Git
 5. Calculer spec_hash canonique (§6.2.1, exclusion du champ spec_hash)
 6. Calculer api_id = uuid5(STOA_API_NAMESPACE, f"{tenant_id}:{env}:{api_name}")
 7. **Vérification anti-collision legacy** (cf. §6.14) :
       - SELECT id, spec_hash FROM apis
         WHERE tenant_id = ? AND name = ? AND id != api_id
       - si une ligne legacy existe (id différent, spec_hash NULL) → 409 Conflict,
         last_error="legacy api name collision", aucune écriture Git
 8. Acquérir lock distribué scope=(tenant_id, environment)         (cf. §6.7)
 9. Ouvrir/réutiliser un worktree dédié (cf. §6.11) :
       git fetch origin
       git checkout -B main origin/main
       assert clean working tree
10. Lire fichier tenants/{tid}/environments/{env}/apis/{name}.uac.json
       - absent          → Case A
       - même hash       → Case B  (no-op Git, jump à étape 13)
       - hash différent  → raise GitOpsConflictError → 409
11. Écrire fichier, git add, git commit -m "create api {tid}/{env}/{name}"
12. git push origin main avec retry borné (max 3×) :
       - push rejected → reset --hard origin/main, fetch, **retour à l'étape 10**
         (réévaluation Case A/B/C, parce qu'un autre acteur a peut-être
          écrit le même fichier entre-temps)
       - épuisement → 503 Service Unavailable, aucune projection DB,
         worktree resetté propre
13. Récupérer le commit du fichier (PAS le HEAD repo) :
       file_commit_sha = git log -n1 --format=%H -- {path}
       (Pour Case B, identique : commit du fichier existant)
14. Relire le contrat depuis Git, jamais depuis le payload ni l'in-memory :
       committed_contract_bytes = git show {file_commit_sha}:{path}
       committed_contract = parse(committed_contract_bytes)
15. Vérification anti-corruption :
       recomputed_hash = compute_spec_hash(committed_contract)
       if embedded_hash(committed_contract) != recomputed_hash :
           status='failed', last_error="spec_hash mismatch", retour 500
16. Vérification cohérence path ↔ contract (cf. §6.9) :
       if committed_contract.tenant_id != tenant_id : 422
       if committed_contract.name      != api_name  : 422
17. Appeler la fonction de projection partagée avec le reconciler :
       project_to_db(committed_contract, file_commit_sha, target="db")
       Mappings : cf. §6.8
       project_to_db est transactionnel et idempotent
18. Écrire api_sync_status(target='db', status='synced',
                           desired_spec_hash=recomputed_hash,
                           observed_spec_hash=recomputed_hash,
                           desired_commit_sha=file_commit_sha)
19. Relâcher le lock
20. Retourner 201 {id: api_id, name: api_name}
```

Points non négociables :
- **Étape 4.** La validation multi-backend est faite **avant** toute écriture Git. Sinon Git contient un contrat non-projetable, état dégradé permanent.
- **Étape 7.** La vérification anti-collision legacy est faite **avant** toute écriture Git. Sinon on commit dans `stoa-catalog` un contrat dont la projection échouera à cause d'une legacy en DB.
- **Étape 12.** Avant push remote réussi, aucune projection DB. En cas d'échec définitif, le worktree local est reset sur `origin/main`. En cas de push rejected, le retry **réévalue Case A/B/C** depuis l'étape 10 — il ne refait pas aveuglément le même push.
- **Étape 13.** `desired_commit_sha` = dernier commit qui a modifié *ce fichier*, pas le HEAD du repo. Plus stable, plus lisible en debug.
- **Étape 14.** La projection consomme `git show {sha}:{path}`, jamais le payload HTTP, jamais l'objet Pydantic in-memory, jamais un fichier local non poussé. C'est ce qui rend « Payload never projects » incontestable.
- **Étape 15.** Le `spec_hash` embarqué dans le fichier UAC n'est jamais cru sur parole.

### 6.6 Reconciler comme worker séparé

Le reconciler n'est **pas** un side-effect de la route FastAPI. Deux processus coexistent :

```
process 1 :  uvicorn control_plane_api.main:app
process 2 :  python -m control_plane_api.services.catalog_reconciler.worker
```

Boucle du worker :

```
loop forever:
    git fetch origin                                   (dans son propre clone, cf. §6.11)
    git checkout -B main origin/main
    for each tenants/{tid}/environments/{env}/apis/{name}.uac.json :

        # 1. Validation cohérence path ↔ contenu (cf. §6.9)
        if path validation fails:
            update_status(failed, "path/content mismatch")
            continue

        # 2. Lecture desired state depuis Git
        contract = parse(file)
        desired_spec_hash = compute_spec_hash(contract)
        if embedded_hash(contract) != desired_spec_hash:
            update_status(failed, "spec_hash mismatch")
            continue
        desired_commit_sha = git log -n1 --format=%H -- {path}

        # 3. Validation projectabilité DB (single-backend pour ce cycle)
        if has_multiple_backends(contract):
            update_status(failed, "multiple backend_url")
            continue

        # 4. Render projection attendue depuis UAC
        api_id = compute_api_id(tid, env, name)
        expected_row = render_db_projection(contract, desired_commit_sha)

        # 5. Vérification anti-collision legacy (cf. §6.14)
        if legacy_collision_exists(tenant_id, name, api_id):
            update_status(failed, "legacy api name collision")
            continue

        # 6. Lecture état réel DB
        actual_row = SELECT id, tenant_id, name, version,
                            backend_url, spec_hash, source_commit_sha,
                            display_name
                     FROM apis WHERE id = api_id

        # 7. Décision drift par comparaison de projection complète
        if actual_row is None:
            # Cas reconstruction (test §7 étape 4) : DB vide, Git plein
            if try_advisory_lock(tid, env):
                project_to_db(contract, desired_commit_sha, target='db')
                update_status(synced, ...)
            else:
                continue  # POST tient le lock, on rattrapera

        elif not db_row_matches_projection(actual_row, expected_row):
            # Vrai drift : DB diverge de la projection attendue.
            # Couvre l'UPDATE hostile sur backend_url, name, version,
            # display_name, ou tout autre champ projeté — même si
            # actual_row.spec_hash est resté identique.
            if try_advisory_lock(tid, env):
                update_status(drift_detected, last_error="db projection drift")
                project_to_db(contract, desired_commit_sha, target='db')
                update_status(synced, ...)
            else:
                continue

        elif sync_status_missing or sync_status.status != 'synced':
            # DB et Git d'accord sur les champs métier, mais statut absent
            update_status(synced, ...)

        else:
            # Tout aligné, no-op
            pass

    sleep CATALOG_RECONCILE_INTERVAL_SECONDS
```

Le worker compare la **projection complète attendue** avec la ligne `apis` réelle, pas seulement les hashes. Un `UPDATE apis SET backend_url='hijack'` est détecté même si `apis.spec_hash` reste correct, parce que `expected_row.backend_url != actual_row.backend_url`.

`db_row_matches_projection()` compare au minimum :
- `id`
- `tenant_id`
- `name`
- `version`
- `backend_url`
- `display_name`
- `spec_hash`
- `source_commit_sha`

Pour rendre cette comparaison possible, **migration additive** sur la table `apis` :
```sql
ALTER TABLE apis ADD COLUMN spec_hash VARCHAR(64) NULL;
ALTER TABLE apis ADD COLUMN source_commit_sha VARCHAR(64) NULL;
```
Ces colonnes sont écrites par `project_to_db()` à chaque projection. Pour les APIs legacy (créées hors GitOps), elles restent NULL — le reconciler les ignore (out-of-scope, cf. §6.14).

Réglages :
- `CATALOG_RECONCILE_INTERVAL_SECONDS=10` pour la démo (cohérent avec test §7 ≤30s)
- En prod future : webhook GitHub → trigger immédiat, polling 60s en fallback
- Le worker doit pouvoir tourner même si personne n'appelle `POST /apis` — c'est ce qui rend le test §7 (commit Git manuel) possible

### 6.7 Lock distribué

Lock Python en mémoire **insuffisant** (cp-api tourne en multi-worker uvicorn et potentiellement multi-pod). Choix figé : **Postgres advisory lock** (pas de nouvelle dépendance).

Clé de lock — déterministe, stable cross-process, **ne jamais utiliser `hash()` Python natif** (randomisé via PYTHONHASHSEED depuis Python 3.3) :

```python
import hashlib

def advisory_lock_key(tenant_id: str, environment: str) -> int:
    """
    Clé bigint signée stable pour pg_advisory_lock / pg_try_advisory_xact_lock.
    Stabilité testée en Phase 5.
    """
    raw = f"stoa:gitops:{tenant_id}:{environment}".encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    return int.from_bytes(digest[:8], "big", signed=True)
```

Valeurs vérifiables :
```
advisory_lock_key("demo", "demo")        =  8118093876459178279
advisory_lock_key("demo-gitops", "demo") = -9202343674291749306
```

Pattern `gitops_writer` (POST) — lock bloquant :
```python
key = advisory_lock_key(tenant_id, environment)
with pg_advisory_lock(key):
    # étapes 9-18 du flow §6.5
    ...
```

Pattern `catalog_reconciler` (worker) — try-lock non bloquant :
```python
key = advisory_lock_key(tenant_id, environment)
if pg_try_advisory_xact_lock(key):
    # projection (le lock se libère en fin de transaction)
    ...
else:
    # un POST tient le lock, skip ce tenant/env, on le verra au prochain tick
    continue
```

Justifications :
- POST bloque pour garantir une réponse HTTP cohérente
- Worker skip pour ne pas faire la queue derrière les POST sous charge
- `project_to_db()` est de toute façon transactionnel et idempotent, donc skip = aucune perte de cohérence

### 6.8 Mapping UAC → table `apis`

Le contrat HTTP figé impose :
```
GET /v1/tenants/{tid}/apis/{id} → {id, name, backend_url, ...}
```

Mapping figé pendant ce cycle (Phase 3 confirmera l'alignement avec le modèle existant) :

| Champ DB | Source UAC |
|---|---|
| `apis.id` | `compute_api_id(tenant_id, environment, contract.name)` |
| `apis.tenant_id` | `contract.tenant_id` (validé identique au path) |
| `apis.name` | `contract.name` (validé identique au filename stem) |
| `apis.display_name` | `contract.name` (cf. §6.10) |
| `apis.version` | `contract.version` |
| `apis.backend_url` | `contract.endpoints[0].backend_url` |
| `apis.spec_hash` | `compute_spec_hash(contract)` |
| `apis.source_commit_sha` | `git log -n1 --format=%H -- {path}` |

**Restriction figée pour ce cycle** :
> Tous les endpoints d'un même contrat UAC doivent partager le même `backend_url`.
> - **Côté writer (POST)** : refus pré-Git en 422 (cf. §6.5 étape 4). Aucun commit Git.
> - **Côté reconciler (commit Git manuel)** : `status='failed'`, `last_error="multiple backend_url"`, aucune projection.

### 6.9 Validation cohérence path ↔ contract

Le reconciler et le writer refusent les incohérences entre le chemin Git et le contenu UAC :

| Vérification | Règle | Action si violée |
|---|---|---|
| Tenant | `path.tenant_id == contract.tenant_id` | `status='failed'`, last_error="tenant mismatch" |
| Filename | `path.api_name == contract.name` | `status='failed'`, last_error="name mismatch" |
| Environment | `path.environment ∈ {"demo"}` | `status='failed'`, last_error="env not allowed" |
| Slug | `api_name`, `tenant_id` matchent `[a-z0-9-]+` | rejet écriture côté writer (422), rejet projection côté reconciler |

Ces validations s'appliquent aussi bien :
- côté writer (avant commit)
- côté reconciler (à chaque scan, en défense en profondeur — un humain peut commit à la main un fichier mal placé)

### 6.10 `api_name` est un identifiant stable, `display_name` est dérivé

Conséquence directe du choix `api_id = uuid5(NS, "tenant:env:name")` :

> Pendant ce cycle et les cycles suivants, `api_name` est un identifiant stable.
> Renommer une API = `delete + create`, jamais un update silencieux du nom.

**`display_name` : pas de champ DB-only mutable**

Pour préserver l'invariant de reconstructibilité (§2.5), aucun champ métier persistant de `apis` ne peut exister uniquement en DB de manière mutable pour les APIs créées via GitOps. Donc :

```
apis.display_name = contract.name
```

Pour ce cycle, `display_name` n'est pas un champ libre. Si plus tard on veut un `display_name` indépendant, il devra être ajouté au schéma UAC v1 (cycle séparé qui touche la parité Python/Rust, cf. §4.2 out-of-scope), pas hacké en DB-only.

Toute future tentative de rename in-place ou de `display_name` DB-only mutable demandera une ADR explicite, car elle invalide la reconstructibilité.

### 6.11 Isolation des working trees Git

Le lock Postgres protège la section métier mais **pas le filesystem du `.git/`**. Si writer et worker partagent le même répertoire Git, des opérations concurrentes (`checkout`, `reset`, `clean`) provoquent des collisions filesystem indépendantes du lock applicatif.

**Règle non négociable** :
> Aucun process ne partage un writable working tree Git avec un autre process.

Implémentation pour ce cycle (MVP) :

```
/var/lib/stoa/gitops/
  catalog-mirror/                       # bare clone, fetch-only, partagé en lecture
  writer/
    {tenant_id}--{environment}/         # worktree dédié writer, par tenant/env
  reconciler/
    worker.work/                        # worktree dédié worker, scan complet
```

- `gitops_writer` ouvre/réutilise un worktree par `(tenant_id, environment)`. Pendant qu'il y travaille, il tient déjà le lock Postgres advisory de ce scope (§6.7), donc deux POST simultanés sur le même tenant/env attendent le lock, pas le filesystem.
- `catalog_reconciler` utilise un worktree distinct, jamais le même que le writer. Aucune commande destructive (`reset --hard`, `checkout -B`, `clean -fd`) n'est exécutée sur un worktree partagé.
- Le bare mirror central est rafraîchi via `git fetch` par les deux processus, mais aucun ne checkout dedans.

Alternative acceptable (MVP simplifié) : un seul clone partagé protégé par un **file lock OS-level** (`flock(2)`) sur un fichier sentinelle. Plus simple à implémenter, plus lent sous charge. Choix exact figé en Phase 3 selon la complexité d'intégration.

Test Phase 5 : lancer en parallèle 1 worker et 5 POST sur des tenants distincts → aucune erreur Git, aucune corruption de worktree.

### 6.12 Compatibilité avec `demo-scope.md` et démo locale

Cette spec est **une décision écrite de rewrite ciblé**. Elle ne remplace pas [`demo-scope.md`](./demo-scope.md) ni [`demo-acceptance-tests.md`](./demo-acceptance-tests.md) tant que Christophe n'a pas explicitement décidé que GitOps create API entre dans le smoke minimal provider/runtime.

`demo-scope.md` §4 dit explicitement que le « GitOps E2E (sync `stoa-catalog` ↔ DB) » est out-of-scope du smoke provider, et que `GIT_SYNC_ON_WRITE=false` est le comportement par défaut. Cette spec crée une **exception contrôlée** à cette règle, sans la révoquer.

**Pendant Phases 1-7** :
- `./scripts/demo-smoke-test.sh` sans flag GitOps reste compatible avec le chemin démo existant
- `GIT_SYNC_ON_WRITE=false` reste le comportement du smoke provider historique
- `GITOPS_CREATE_API_ENABLED=false` reste le défaut sur le tenant `demo` historique
- L'activation GitOps se fait uniquement sur tenant `demo-gitops` (créé propre pour ce cycle, sans collision legacy) ou via flag explicite par appel

**Validation GitOps additionnelle** :

```bash
GITOPS_CREATE_API_ENABLED=true \
DEMO_UAC_CONTRACT=specs/uac/demo-httpbin.uac.json \
./scripts/demo-smoke-test.sh
```

Cette commande prouve que GitOps fonctionne, sans remplacer la commande historique.

**Démo locale sans GitHub externe** :

`architecture-rules.md` §4 impose que la démo « Tourne offline une fois les dépendances pulled ». Cette spec respecte cette règle :
- Le remote `stoa-catalog` peut être un bare repository local : `STOA_CATALOG_REMOTE_URL=file:///var/lib/stoa/gitops/catalog-remote.git`
- Aucun accès GitHub externe n'est requis pour exécuter le test §7 localement
- Les tests GitHub réels (push vers github.com) restent des tests d'intégration séparés, non requis pour le smoke local

**Bascule Phase 10** :

La bascule Phase 10 ne s'applique qu'aux **tenants GitOps-initialized**, pas à tous les tenants existants (cf. §6.14). Une migration legacy → GitOps des tenants historiques fait l'objet d'une spec séparée, hors de ce cycle.

`demo-scope.md` ne change que si Christophe décide explicitement, au moment de la bascule, que GitOps create API devient partie du smoke minimal.

### 6.13 Mapping payload HTTP → UACContract

Le payload AT-1 du smoke (`demo-acceptance-tests.md`) est un format legacy qui n'est pas un UAC contract :

```json
{
  "name": "demo-httpbin",
  "display_name": "demo-httpbin",
  "version": "1.0.0",
  "protocol": "http",
  "backend_url": "http://mock-backend:9090",
  "paths": [{"path": "/get", "methods": ["GET"]}]
}
```

La conversion vers `UACContract` est **figée et déterministe** :

| Champ UAC | Source payload HTTP |
|---|---|
| `contract.name` | `slug(payload.name)` |
| `contract.tenant_id` | `tenant_id` du path param `/v1/tenants/{tid}/apis` |
| `contract.version` | `payload.version` |
| `contract.status` | `"published"` (constant pour ce cycle) |
| `contract.classification` | `"H"` par défaut, sauf si `payload.classification ∈ {"H","VH","VVH"}` |
| `contract.endpoints[i].path` | `payload.paths[i].path` |
| `contract.endpoints[i].methods` | `payload.paths[i].methods` |
| `contract.endpoints[i].backend_url` | `payload.backend_url` (le même pour tous les endpoints, cf. §6.8 single-backend) |
| `contract.endpoints[i].operation_id` | `f"{contract.name}_{method.lower()}_{normalize_path(path)}"` (stable, déterministe) |
| `contract.endpoints[i].input_schema` | `{"type":"object","additionalProperties":false}` par défaut |
| `contract.endpoints[i].output_schema` | `{"type":"object","additionalProperties":true}` par défaut |
| `contract.spec_hash` | `compute_spec_hash(contract)` (calculé en dernier, après remplissage de tous les autres champs) |

**Champs payload ignorés comme source de vérité métier** (mais acceptés pour compatibilité AT-1) :
- `payload.display_name` — ignoré ; `apis.display_name = contract.name` (cf. §6.10)
- `payload.protocol` — ignoré pour ce cycle ; le UAC v1 actuel ne porte pas de champ `protocol` au top-level

**Fonction de normalisation** :
```python
def normalize_path(path: str) -> str:
    """Convertit '/get' → 'get', '/users/{id}' → 'users_id'."""
    return path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
```

Exemple complet — payload AT-1 → UACContract dérivé :
```python
# input
payload = {
    "name": "demo-httpbin",
    "display_name": "demo-httpbin",
    "version": "1.0.0",
    "protocol": "http",
    "backend_url": "http://mock-backend:9090",
    "paths": [{"path": "/get", "methods": ["GET"]}]
}
tenant_id = "demo"

# output (avant calcul spec_hash)
contract = UACContract(
    name="demo-httpbin",
    tenant_id="demo",
    version="1.0.0",
    status="published",
    classification="H",
    endpoints=[
        Endpoint(
            path="/get",
            methods=["GET"],
            backend_url="http://mock-backend:9090",
            operation_id="demo-httpbin_get_get",
            input_schema={"type": "object", "additionalProperties": False},
            output_schema={"type": "object", "additionalProperties": True},
        )
    ],
)
contract.spec_hash = compute_spec_hash(contract)
```

Ce mapping est testé en Phase 5 contre le payload AT-1 exact, et le `spec_hash` résultant doit être stable cross-runs.

### 6.14 Politique de collision avec les APIs legacy

**Problème** : pendant la transition, `apis` peut contenir des lignes créées par l'ancien chemin avec un `id` aléatoire et `spec_hash IS NULL`. Si on active GitOps sur un tenant qui a une API legacy `demo-httpbin`, le calcul `compute_api_id("demo", "demo", "demo-httpbin") = d5844819-...` produit un `id` différent. Selon les contraintes uniques de la table (à confirmer Phase 1), trois scénarios :
- contrainte unique `(tenant_id, name)` → INSERT échoue
- pas de contrainte → doublon logique avec deux ids
- contrainte `id` PRIMARY KEY → l'ancien id reste, le nouveau ne peut pas être inséré

**Politique pour ce cycle** :

> **Pendant Phases 6-9, le flag GitOps n'est activé que sur des tenants GitOps-initialized**, c'est-à-dire :
> - tenants nouveaux créés pour ce cycle (typiquement `demo-gitops`)
> - tenants dont les APIs legacy conflictuelles ont été manuellement nettoyées avant activation
>
> Aucune migration automatique legacy → GitOps n'est faite par cette spec.

**Détection writer** (§6.5 étape 7) :
```python
def legacy_collision_exists(tenant_id: str, name: str, expected_api_id: uuid.UUID) -> bool:
    row = SELECT id, spec_hash FROM apis
          WHERE tenant_id = %s AND name = %s AND id != %s
    return row is not None  # toute ligne avec même (tenant, name) mais id ≠ deterministic
```

Si `legacy_collision_exists()` retourne `True` :
- POST retourne **409 Conflict** avec `last_error="legacy api name collision"`
- aucune écriture Git
- aucune mutation DB destructive
- le tenant doit être nettoyé manuellement avant activation GitOps, ou rester sur l'ancien chemin

**Détection reconciler** (§6.6 étape 5) — défense en profondeur si quelqu'un commit à la main dans `stoa-catalog` un fichier qui collisionne avec une legacy :
- `status='failed'`, `last_error="legacy api name collision"`
- aucune mutation `apis`

**Phase 10 — bascule limitée** :
- Le flag passe à `true` par défaut **uniquement sur les tenants GitOps-initialized**
- Les tenants legacy non migrés continuent d'utiliser l'ancien chemin (`GITOPS_CREATE_API_ENABLED=false`)
- Une spec séparée traitera la migration legacy → GitOps quand le besoin métier sera concret

## 7. Critère de succès final

Test binaire — le rewrite est validé si et seulement si :

```bash
# 0. Pré-condition : tenant GitOps-initialized propre (sans collision legacy)
TENANT=demo-gitops

# 1. Construire un contrat UAC à la main avec spec_hash correct
#    (helper en in-scope §4.1, implémenté Phase 4)
python -m control_plane_api.services.uac.write_canonical_contract \
  --tenant ${TENANT} \
  --name manual-test \
  --version 1.0.0 \
  --backend http://mock-backend:9090 \
  --output /tmp/manual-test.uac.json

# 2. Couper l'UI, push direct dans stoa-catalog
#    Note : remote local file:// suffit, pas besoin de GitHub (cf. §6.12)
mkdir -p stoa-catalog/tenants/${TENANT}/environments/demo/apis/
cp /tmp/manual-test.uac.json stoa-catalog/tenants/${TENANT}/environments/demo/apis/
git -C stoa-catalog add .
git -C stoa-catalog commit -m "manual: add manual-test API"
git -C stoa-catalog push  # vers le remote local file://

# 3. Attendre le reconcile (intervalle worker = 10s, marge × 3)
sleep 30

# 4. Vérifier que la DB reflète le commit avec api_id déterministe
EXPECTED_ID=$(python -c "
import uuid
ns = uuid.UUID('c276f996-0520-5de1-ab27-83ab8749e086')
print(uuid.uuid5(ns, '${TENANT}:demo:manual-test'))
")
curl -s ${API_URL}/v1/tenants/${TENANT}/apis/${EXPECTED_ID}
# → doit retourner l'API avec name=manual-test

# 5. Vérifier que apis.spec_hash et apis.source_commit_sha sont écrits
psql $DATABASE_URL -c "SELECT id, name, spec_hash, source_commit_sha FROM apis WHERE id='${EXPECTED_ID}';"
# → spec_hash et source_commit_sha non NULL

# 6. Vérifier la détection de drift par projection complète :
#    UPDATE manuel hostile sur backend_url (champ projeté, pas le hash)
psql $DATABASE_URL -c "UPDATE apis SET backend_url='http://hijack:9999' WHERE id='${EXPECTED_ID}';"
sleep 30
psql $DATABASE_URL -c "SELECT backend_url FROM apis WHERE id='${EXPECTED_ID}';"
# → doit être revenu à http://mock-backend:9090
#   (reconciler a comparé expected_row vs actual_row, détecté le drift,
#    et reprojetté depuis Git)

# 7. Vérifier que le smoke complet reste vert avec le flag ON
GITOPS_CREATE_API_ENABLED=true \
TENANT_ID=${TENANT} \
DEMO_UAC_CONTRACT=specs/uac/demo-httpbin.uac.json \
./scripts/demo-smoke-test.sh
# → Verdict: REAL_PASS — DEMO READY
```

Si ces 4 vérifications passent (étapes 4, 5, 6, 7), Git est vraiment la source de vérité. Si l'une échoue, le rewrite n'est pas terminé.

## 8. Risques identifiés et mitigations

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| Git remote unavailable pendant un POST API | Moyen | Haut | Retry exponentiel 3×, puis fail-fast 503 avec erreur claire. Ne jamais dégrader vers DB-only silencieusement. Pour la démo, remote local `file://` (cf. §6.12). |
| Conflits Git multi-agents (HEGEMON parallèle) | Haut | Moyen | Lock distribué Postgres advisory (§6.7). Push rejected → fetch/reset + **réévaluation Case A/B/C** + retry borné. |
| Collision filesystem Git (`.git/` partagé) | Moyen | Haut | Worktrees isolés writer/worker (§6.11). Test de charge Phase 5. |
| `spec_hash` différent Python vs Rust | Faible | Critique | Test de parité cross-langage en Phase 5, calcul figé §6.2.1. |
| `spec_hash` embarqué falsifié dans Git | Faible | Haut | Reconciler recalcule et refuse projection si mismatch (§6.2.1). |
| Drift DB invisible parce que hash inchangé | Moyen | Critique | Comparaison `expected_row vs actual_row` complète, pas seulement hash (§6.6). Test §7 étape 6 vérifie. |
| Régression AT-1 pendant Phase 6 | Moyen | Critique | Flag par tenant. Activation uniquement sur `demo-gitops` jusqu'à Phase 7. |
| Crash entre commit Git et projection DB | Moyen | Moyen | Worker reconciler tourne en boucle 10s, rattrape automatiquement (Case B idempotent). |
| Push local OK mais push remote KO | Moyen | Haut | Aucune projection avant push remote réussi. Reset worktree en cas d'échec définitif (§6.5 étape 12). |
| Push rejected = écraser un changement concurrent | Moyen | Haut | Retry réévalue Case A/B/C depuis l'étape 10, jamais re-push aveugle (§6.5 étape 12). |
| Fichier UAC mal placé dans Git | Moyen | Moyen | Validation cohérence path ↔ contract refuse la projection (§6.9). |
| Worker et POST projettent en parallèle la même API | Moyen | Faible | Worker en `try_advisory_xact_lock`, skip si POST tient le lock. `project_to_db` transactionnel idempotent. |
| Contrat multi-backend commité dans Git | Faible | Moyen | Refus pré-commit côté writer 422 (§6.5 étape 4). Refus projection côté reconciler (§6.6). |
| `display_name` mutable casse la reconstructibilité | Moyen | Haut | `apis.display_name = contract.name` figé pour ce cycle (§6.10). Toute mutation DB-only refusée. |
| `advisory_lock_key` randomisée (`hash()` Python) | Haut sans patch | Critique | Fonction stable basée sur SHA-256 (§6.7). Test stabilité Phase 5. |
| Collision avec API legacy (même tenant+name, id différent) | Haut | Critique | `legacy_collision_exists()` côté writer ET reconciler (§6.14). 409 Conflict. Bascule Phase 10 limitée aux tenants GitOps-initialized. |
| Mapping payload→UAC sous-spécifié | Moyen | Moyen | Mapping figé §6.13. Test cross-run de stabilité du `spec_hash` résultant en Phase 5. |
| Démo dépend de GitHub externe | Faible | Moyen | Remote local `file://` supporté, pas de dépendance externe en local (§6.12). |
| Le rewrite déborde sur update/delete sous pression | Haut | Haut | Règle §4.3. Tickets out-of-scope refusés automatiquement. |
| Quelqu'un branche le worker sur `GIT_SYNC_ON_WRITE` par habitude | Moyen | Haut | §9.6 interdit explicitement. Test de scaffold Phase 3 vérifie l'absence du flag dans le nouveau code. |
| Cette spec interprétée comme remplacement de `demo-scope.md` | Moyen | Haut | §6.12 explicite l'exception contrôlée. `demo-scope.md` reste source de vérité du smoke minimal. |

## 9. Garde-fous spécifiques à ce rewrite

En complément des règles génériques de [`rewrite-guardrails.md`](./rewrite-guardrails.md) :

1. **Aucune ADR créée pendant Phases 0-7** sauf décision irréversible. Si une décision irréversible apparaît (ex: « UAC en Git devient canonique en prod »), elle est ouverte en ADR à ce moment-là, pas avant.
2. **Aucun fix pendant Phases 1-2.** Tout bug observé va dans le backlog. Les fix arrivent en Phase 8.
3. **Aucun refactor cosmétique.** Si pendant l'audit Phase 1 on remarque du code moche, il reste moche.
4. **Smoke = gate démo non négociable + tests GitOps = gates de merge.** Le smoke `REAL_PASS` est obligatoire pour ne pas dégrader la démo. Mais il ne suffit pas seul : des tests dédiés couvrent la parité `spec_hash`, le lock distribué stable, les trois cas idempotents, la détection de drift par projection complète, l'atomicité push remote, la validation path↔content, l'isolation des worktrees Git, le mapping payload→UAC déterministe, la legacy collision rejection. Un PR qui passe le smoke mais casse un test GitOps reste NO-GO.
5. **Pas de skill Claude Code créée avant Phase 4.** La skill `stoa-gitops-writer` n'est utile que quand le module existe. Phase 3 produit le squelette à la main pour bien comprendre.
6. **Interdiction d'utiliser `GIT_SYNC_ON_WRITE` dans le nouveau chemin.** Ce flag porte le modèle mental de l'ancien dual-write. Le nouveau pipeline GitOps utilise exclusivement `GITOPS_CREATE_API_ENABLED` et n'a aucune dépendance au flag legacy. Quand `GITOPS_CREATE_API_ENABLED=true`, l'ancien chemin est complètement court-circuité, pas appelé en parallèle.
7. **Le payload HTTP ne projette jamais.** Toute fonction qui prend un payload HTTP en entrée et écrit en DB sans passer par un commit Git **poussé sur le remote** intermédiaire est interdite dans le périmètre de ce rewrite. Test de scaffold Phase 3 enforce cette règle structurellement (le code de projection accepte uniquement un type `CommittedContract` qui ne peut être obtenu que via `git show`).
8. **Aucun champ métier DB-only mutable** pour les APIs GitOps-created. Tout champ persistant de `apis` doit être dérivé du UAC ou déterministe (cf. §6.10).
9. **Cette spec ne remplace pas `demo-scope.md`.** Elle crée une exception contrôlée (cf. §6.12). Tant que Christophe n'a pas explicitement décidé que GitOps create API devient partie du smoke minimal, le smoke historique reste la source de vérité du contrat démo provider/runtime.

## 10. Liens avec l'écosystème specs

- Source de vérité du scope démo : [`demo-scope.md`](./demo-scope.md)
- Tests d'acceptance qui ne doivent pas régresser : [`demo-acceptance-tests.md`](./demo-acceptance-tests.md) AT-1
- Contrats HTTP figés : [`architecture-rules.md`](./architecture-rules.md) §2.1
- Garde-fous transverses : [`rewrite-guardrails.md`](./rewrite-guardrails.md)
- Format UAC et doctrine : [`uac/README.md`](./uac/README.md)
- Commandes de validation : [`validation-commands.md`](./validation-commands.md)
- Démo client/prospect (cycle séparé, ne pas mélanger) : [`client-prospect-demo-scope.md`](./client-prospect-demo-scope.md)
- Flow de déploiement runtime (cycle séparé) : [`api-deployment-flow.md`](./api-deployment-flow.md)

## 11. Sortie de ce rewrite

Conditions pour clôturer cette spec et la passer en statut *Référence* :

1. Phases 0 à 10 toutes terminées avec critère de fin validé
2. Le test §7 complet (commit Git manuel + drift hostile + smoke) passe en CI sur 5 runs consécutifs
3. Le flag `GITOPS_CREATE_API_ENABLED` est `true` par défaut sur tous les **tenants GitOps-initialized** depuis ≥ 7 jours (les tenants legacy non migrés conservent l'ancien chemin, cf. §6.14)
4. Aucun rollback déclenché pendant ces 7 jours
5. Le backlog `api-creation-rewrite-backlog` est à zéro
6. La table `api_sync_status` est cohérente : pour chaque API en table `apis` créée via GitOps, il existe une ligne `target='db'` avec `status='synced'`

Une fois clôturée, cette spec sert de pattern de référence pour les rewrites GitOps suivants (update, publish, promote, delete, target=`gateway`, target=`portal`).

## 12. Révisions

| Date | Version | Auteur | Delta |
|---|---|---|---|
| 2026-04-26 | v0.1 DRAFT | Claude (session rewrite GitOps) | Création initiale |
| 2026-04-26 | v0.2 DRAFT | Claude après revue ChatGPT round 1 | Doctrine étendue, api_id déterministe, layout avec env, worker séparé, polling 10s, target dans api_sync_status, 3 cas idempotents, commit-first projection, interdiction GIT_SYNC_ON_WRITE, smoke + tests gates, lock distribué, flow détaillé |
| 2026-04-26 | v0.3 DRAFT | Claude après revue ChatGPT round 2 | UUID `STOA_API_NAMESPACE` valide figé, `spec_hash` canonique défini, drift detection via colonnes `apis.spec_hash`/`source_commit_sha`, `desired_commit_sha` = commit du fichier, atomicité push remote, relire depuis Git uniquement, mapping UAC→`apis` figé avec single-backend, validation path↔contract, worker `pg_try_advisory_xact_lock`, `api_name` identifiant stable |
| 2026-04-26 | v0.3.1 DRAFT | Claude après revue ChatGPT round 3 | Drift detection par projection complète, workspace Git isolation §6.11, push rejected retry réévalue Case A/B/C, helper `write_canonical_contract` in-scope, validation multi-backend pré-commit, `display_name = contract.name`, `advisory_lock_key` stable SHA-256, `varchar(64)` pour SHA |
| 2026-04-26 | v1.0 | Claude après revue ChatGPT round 4 | (1) §6.12 nouveau : compatibilité explicite avec `demo-scope.md`, exception contrôlée au out-of-scope GitOps E2E historique, support remote Git local `file://` pour démo offline ; (2) §6.13 nouveau : mapping figé payload HTTP → UACContract avec table de correspondance, defaults, fonction `normalize_path`, exemple complet AT-1 ; (3) §6.14 nouveau : politique de collision avec APIs legacy, `legacy_collision_exists()` côté writer (§6.5 étape 7) ET reconciler (§6.6 étape 5), bascule Phase 10 limitée aux tenants GitOps-initialized ; (4) Note multi-env dans §6.4 : `api_id env-scoped` figé pour ce cycle uniquement, décision multi-env reportée au cycle promotion ; (5) Risques §8 enrichis : remote unavailable au lieu de GitHub down, mapping sous-spécifié, démo GitHub externe, spec interprétée comme remplacement de `demo-scope.md` ; (6) Garde-fou §9.9 nouveau : cette spec ne remplace pas `demo-scope.md` ; (7) Out-of-scope §4.2 : migration legacy, décision multi-env ; (8) Statut DRAFT enlevé. **Spec exécutable Phase 1 GO.** |
