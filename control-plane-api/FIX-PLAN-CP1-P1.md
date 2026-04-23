# FIX-PLAN-CP1-P1

> **Scope** : the 9 High-priority findings from `BUG-REPORT-CP-1.md` Rev 2.
> **Branch** : `fix/cp-1-p1-batch` (cut from `fix/cp-1-p0-batch`; rebase on
> `main` once the P0 batch is merged).
> **Method** : Phase 1 plan (this doc) → STOP for human validation → Phase 2
> atomic commits with per-bug regression guards → Phase 3 global validation.
> **Owner** : @PotoMitan. Date : 2026-04-23.

---

## 1. Bug roster (9 findings)

### H.1 — Webhook replay: no dedup on delivery headers

- **File/line** : `src/routers/webhooks.py` (entier — GitLab handler L.93 onward, GitHub handler L.239 onward)
- **Cause racine** : **Group B** (webhook surface hardening)
- **Résumé** : aucun des deux handlers ne lit `X-GitHub-Delivery` ou
  `X-Gitlab-Webhook-UUID` / `X-Gitlab-Event-UUID`. GitHub/GitLab rejouent sur
  timeout → pipeline exécuté 2×: Kafka publish × 2, trace × 2, retry sur
  `already exists` compté comme erreur (ou faux-positif via H.8).
- **Approche** : cache TTL in-memory (stdlib, pas de Redis en P1) indexé
  sur `(source, delivery_id)`, capacité 10 000 entrées, TTL 24h (fenêtre GitHub
  redelivery standard). Au hit → 200 + `status="duplicate"` sans publish Kafka
  ni trace DB.
- **API publique** : réponse existante (`WebhookProcessedResponse`) conservée
  ; un nouveau `status="duplicate"` s'ajoute. Le status code reste 200.
- **Régression guards** : 3 tests
  - `test_gitlab_webhook_dedup_on_repeated_uuid`
  - `test_github_webhook_dedup_on_repeated_delivery_id`
  - `test_missing_delivery_header_still_processes_but_logs_warning`

### H.2 — `contextlib.suppress(Exception)` in `_sync_api_from_git`

- **File/line** : `src/services/deployment_orchestration_service.py:115-124`
- **Cause racine** : **Group D** (service-layer contract hardening)
- **Résumé** : deux blocs `with contextlib.suppress(Exception):` avalent
  timeout, rate-limit, YAML parse errors, auth failures. `_upsert_api` reçoit
  `None` sans distinguer "pas de spec" de "provider injoignable".
- **Approche** : remplacer par `except FileNotFoundError` (fichier absent =
  None attendu) ; laisser `TimeoutError`, `GitlabGetError` quand c'est un 429 /
  5xx, et `GithubException` avec `status != 404` remonter. Logger WARNING
  pour le cas inattendu au lieu de tout swallow.
- **API publique** : non (méthode privée `_sync_api_from_git`). Callers
  actuels consomment déjà le `None` comme "pas trouvé" — on conserve ce
  contrat pour le cas `FileNotFoundError`. Les vraies pannes remontent en
  exception, cohérent avec le reste du service.
- **Régression guards** : 3 tests
  - `test_sync_api_suppresses_missing_openapi_spec`
  - `test_sync_api_propagates_rate_limit_error`
  - `test_sync_api_propagates_timeout_error`

### H.3 — Router leaks `str(e)` in HTTPException `detail`

- **File/line** : `src/routers/git.py:185, 209-210, 254-255, 273-274, 310-311`
- **Cause racine** : **Group A** (router error mapping)
- **Résumé** : `f"Failed to ...: {e}"` dans `detail` remonte PyGithub /
  python-gitlab error strings : URL API, headers, request IDs, fragments de
  stack. Post-C.2, le risque de fuite de token est fermé mais d'autres
  éléments de diagnostic exposés restent.
- **Approche** : message générique (`detail="Failed to <action>"`) ; log
  serveur conserve l'exception complète avec `exc_info=True` et le
  `request_id` est déjà bindé en contextvars par `logging_config.py` donc
  inclus automatiquement dans chaque log. Le client récupère le `request_id`
  côté réponse via le header `X-Request-ID` (middleware
  `http_logging.py:111`).
- **API publique** : le `detail` devient stable ("Failed to save file",
  "Failed to merge", etc.). Les tests existants qui inspectent `detail` doivent
  être revus — on regarde au Phase 2.
- **Régression guards** : 2 tests (1 par pattern affecté)
  - `test_router_generic_detail_on_write_file_failure`
  - `test_router_generic_detail_on_merge_failure`

### H.4 — `delete_file` router converts ALL exceptions into 404

- **File/line** : `src/routers/git.py:205-212`
- **Cause racine** : **Group A** (router error mapping)
- **Résumé** : `except Exception: raise HTTPException(404)`. Timeout, 500
  provider, 401 déguisés en 404 "File not found" → le frontend affiche "fichier
  absent" sur une panne provider.
- **Approche** : `except FileNotFoundError: 404`, `except TimeoutError: 504`,
  `except Exception: 502` (Bad Gateway = dépendance amont HS). Même stratégie
  que la PR P0 sur `write_file` (create-first qui distingue create vs update).
- **API publique** : 404 cesse d'être le fourre-tout ; les clients qui
  traitaient 404 comme "file missing" continuent de marcher ; nouveaux status
  (502, 504) à communiquer côté UI — noter dans la PR description.
- **Régression guards** : 3 tests
  - `test_delete_missing_file_returns_404`
  - `test_delete_timeout_returns_504`
  - `test_delete_provider_5xx_returns_502`

### H.5 — `list_*` routes silently return `[]` on any error

- **File/line** : `src/routers/git.py:123-125, 160-161, 229-231, 290-292`
- **Cause racine** : **Group A** (router error mapping)
- **Résumé** : 4 routes (`list_commits`, `get_tree`, `list_merge_requests`,
  `list_branches`) avalent tout et rendent `[]`. UI affiche "aucun commit /
  branch / MR" au lieu de "provider injoignable".
- **Approche** : identique à H.4 mais sur listings. `FileNotFoundError`
  (path n'existe pas côté GitLab) reste `[]` — c'est une vraie "liste vide".
  Timeout → 504. Autre exception → 502.
- **Cas particulier `list_tree`** : il appelle déjà `list_tree` du service
  qui normalise les 404 en `[]` (post-C.6 + H.6 à venir). Le try/except
  router au-dessus devient un filet pour 5xx provider uniquement.
- **API publique** : même remarque que H.4 — nouveaux codes à relier au
  frontend.
- **Régression guards** : 2 tests (pattern partagé avec H.4)
  - `test_list_commits_provider_5xx_returns_502`
  - `test_list_branches_timeout_returns_504`

### H.6 — `list_tree` contract drift: file vs directory across providers

- **File/line** : `src/services/github_service.py:1049-1072`,
  `src/services/git_service.py:1072-1082`
- **Cause racine** : **Group D** (service-layer contract hardening)
- **Résumé** : sur un `path` qui pointe un fichier (pas un dossier), GitHub
  renvoie un objet unique que le code wrap en `[contents]` et propage comme
  `TreeEntry(type="blob")`. GitLab renvoie `[]` ou 404 selon version. Le
  contrat ABC `list_tree` signifie "énumère les enfants" ; un fichier n'a pas
  d'enfants.
- **Approche** : dans `github_service.list_tree`, si `contents` n'est pas
  une `list` → retourner `[]`. Normalise le contrat inter-provider, supprime
  le piège côté caller.
- **API publique** : le comportement passe de "un entry blob pour un path
  fichier" à "`[]` pour un path fichier". Aucun caller dans cp-api ne dépend
  du comportement actuel (vérifier au Phase 2 via `grep list_tree`). Si un
  caller s'appuyait dessus, il devait déjà gérer les deux providers
  divergents — donc cast légitime.
- **Régression guards** : 2 tests
  - `test_github_list_tree_returns_empty_on_file_path`
  - `test_gitlab_list_tree_returns_empty_on_file_path`

### H.7 — Kafka `enable_auto_commit=True` — at-most-once loss

- **File/line** : `src/workers/git_sync_worker.py:150`
- **Cause racine** : **Group C** (worker reliability)
- **Résumé** : avec auto-commit, l'offset avance indépendamment du succès du
  handler async dispatché via `asyncio.run_coroutine_threadsafe`. Un crash
  entre auto-commit et exécution async → event perdu sans alerte → catalog
  divergent.
- **Approche** : `enable_auto_commit=False` + commit manuel **après**
  completion du future dans `_dispatch_event`. `future.result(timeout=60)`
  bloque le consumer thread jusqu'au succès du handler ; puis
  `self._consumer.commit()`. En cas d'exception → log error + PAS de commit
  → message re-livré au prochain poll (at-least-once, idempotence assurée par
  H.8 et par le GitHub API side).
- **Impact latence** : on sérialise par partition. Le topic `api-lifecycle`
  a peu de trafic (< 100 events/s en démo). Acceptable. Alternative future =
  committer async via callback + queue locale, hors scope P1.
- **API publique** : non (worker interne). Noter changement dans le commit
  message.
- **Régression guards** : 2 tests
  - `test_kafka_consumer_disables_auto_commit`
  - `test_commit_only_after_handler_success`

### H.8 — `ValueError` blanket-classified as success in retry loop

- **File/line** : `src/workers/git_sync_worker.py:242-246`
- **Cause racine** : **Group C** (worker reliability)
- **Résumé** : `except ValueError: status="success"` traite toute ValueError
  comme idempotent. Mais `batch_commit("unknown action")` raise ValueError —
  un bug fonctionnel compte comme success dans les métriques.
- **Approche** : discriminer par message :
  ```python
  except ValueError as e:
      msg = str(e).lower()
      if "already exists" in msg or "not found" in msg:
          status = "success"  # idempotent
          return
      # unknown ValueError — log + treat as error
      last_error = e
      # fall through to retry path
  ```
- **API publique** : métrique `catalog_git_sync_total{status=...}` devient
  plus précise ; alerting doit vérifier.
- **Régression guards** : 2 tests
  - `test_value_error_already_exists_counted_as_success`
  - `test_value_error_unknown_message_counted_as_error`

### H.10 — Path sanitization missing in `_tenant_path` (defensive hardening)

- **File/line** : `src/routers/git.py:98-101`
- **Cause racine** : **Group A** (router input validation)
- **Résumé** : le path ramassé par `{file_path:path}` accepte `..`, `\x00`,
  backslashes, paths absolus. Pas exploitable aujourd'hui (GitLab rejette
  `/../` côté serveur ; GitHub traite littéralement). Mais tout refactor
  introduisant `os.path.normpath` ouvre le trou.
- **Approche** : centraliser la validation dans `_tenant_path` (et
  nouveau helper `_validate_file_path`) :
  ```python
  if ".." in path.split("/") or "\x00" in path or path.startswith("/"):
      raise HTTPException(status_code=400, detail="Invalid path")
  ```
  `\` backslash → rejet aussi (Windows-style reserved). Appliqué à
  `get_file`, `create_or_update_file`, `delete_file`, `get_tree`.
- **API publique** : paths déviants rejetés avec 400 (avant: 200 + effet
  indéterminé). Documenter dans la PR — théoriquement aucun path valide
  affecté.
- **Régression guards** : 4 tests
  - `test_path_traversal_rejected`
  - `test_null_byte_rejected`
  - `test_absolute_path_rejected`
  - `test_normal_nested_path_accepted`

---

## 2. Cause racine — mapping final

| Groupe | Bugs | Nature | Fichier principal |
|---|---|---|---|
| A — Router error mapping + input validation | H.3, H.4, H.5, H.10 | boundary defense | `src/routers/git.py` |
| B — Webhook surface hardening | H.1 | idempotence replay | `src/routers/webhooks.py` |
| C — Worker reliability | H.7, H.8 | at-least-once + metric precision | `src/workers/git_sync_worker.py` |
| D — Service contract hardening | H.2, H.6 | expected vs unexpected errors, list_tree normalization | `src/services/deployment_orchestration_service.py`, `src/services/github_service.py` |

---

## 3. Commit plan (4 atomic commits)

### Commit 1 — `fix(cp-api/git): tighten service contracts for list_tree + deploy_sync errors`

- **Closes** : H.2, H.6 (Group D)
- Ordre logique : commencé par la couche service car elle alimente les
  signaux que la couche router (Commit 2) va relayer proprement.
- **Diff** :
  - `github_service.list_tree` : return `[]` quand `contents` n'est pas
    une list.
  - `deployment_orchestration_service._sync_api_from_git` : remplacer les
    `contextlib.suppress(Exception)` par des `except FileNotFoundError`
    + log WARNING sur autres exceptions avant de les propager.
- **Régression tests** :
  `tests/test_regression_cp1_p1_service_contracts.py` (5 tests)
- **Risques** :
  - Si un caller historique consommait la sémantique "file as blob" pour
    un path fichier via `list_tree`, il cesse de le recevoir. Vérif
    grep-scope au Phase 2.
  - Les `with suppress` étaient peut-être là pour masquer un bug
    upstream (ex: adapter gateway 500 sur connect). À surveiller en CI.

### Commit 2 — `fix(cp-api/git): normalize router error mapping + sanitize tenant paths`

- **Closes** : H.3, H.4, H.5, H.10 (Group A)
- **Diff** :
  - `_tenant_path` + nouveau `_validate_file_path(path)` : reject
    `..`, `\x00`, `/abs`, `\`.
  - Helper `_map_provider_exception(e) -> HTTPException` centralise
    `FileNotFoundError → 404`, `TimeoutError → 504`, autre → 502 avec
    detail générique.
  - Remplacer chaque `detail=f"...: {e}"` par message stable
    (`"Failed to save file"`, etc.). Log serveur garde `exc_info=True`
    — `request_id` bindé via contextvars dans `logging_config.py:237`
    → remonte automatiquement dans les logs structlog. Client
    récupère `X-Request-ID` via header réponse (middleware existant).
  - `delete_file` : `except FileNotFoundError: 404 ; except TimeoutError:
    504 ; except Exception: 502`.
  - `list_commits`, `get_tree`, `list_merge_requests`, `list_branches`
    (routes listing) : même helper. `FileNotFoundError` → `[]`,
    timeout → 504, provider error → 502.
- **Arbitrage résolu** :
  - Code HTTP sur panne upstream : **502 Bad Gateway** (norme REST :
    dépendance HS). **504 Gateway Timeout** pour `TimeoutError`. Pas
    500 (500 = bug cp-api).
  - `request_id` exposition : via header `X-Request-ID` existant, pas
    dans `detail` (redondant).
- **Régression tests** :
  `tests/test_regression_cp1_p1_router_errors.py` (11 tests consolidés
  sur H.3/H.4/H.5/H.10)
- **Risques** :
  - Tests E2E existants peuvent asserter `detail` string → à adapter.
  - Clients UI qui lisaient "File not found" sur toute erreur delete
    verront 502/504 → owner UI à notifier via PR description. Pas de
    breaking change client-side si l'UI se fie au status code.

### Commit 3 — `fix(cp-api/webhooks): dedup webhook replays via delivery headers`

- **Closes** : H.1 (Group B)
- **Diff** :
  - Nouveau `src/services/webhook_dedup.py` : cache TTL in-memory
    indexé `(source, delivery_id)`. Capacité 10 000, TTL 24h. Thread-safe
    via `asyncio.Lock`. Pure-stdlib.
  - `gitlab_webhook` : lire `X-Gitlab-Webhook-UUID` (fallback
    `X-Gitlab-Event-UUID`). Si absent → log warning (compat ancien
    GitLab < 14.0) mais continuer. Si vu récemment → renvoyer
    `{"status": "duplicate", "event": ..., "trace_id": "<cached>"}` 200.
  - `github_webhook` : lire `X-GitHub-Delivery`. Même logique.
  - Position dans le pipeline : **après** l'auth (C.7 invariant),
    **avant** le trace DB insert → évite doublons en base.
- **Arbitrage résolu** :
  - **In-memory (stdlib) vs Redis** : in-memory OK en P1 car
    CP-API tourne en single-replica aujourd'hui (ArgoCD values.yaml à
    vérifier). Redis = P2/P3 quand HPA activé, noté dans commit body.
  - **Missing delivery header** : warn + process (pas reject) — compat
    ascendante, certains clients custom n'émettent pas ces headers.
- **Régression tests** :
  `tests/test_regression_cp1_p1_webhook_dedup.py` (3 tests)
- **Risques** :
  - Single-replica hypothesis : si 2 réplicas CP-API → dédup ne marche
    pas entre instances. Documenter en commit + issue follow-up Redis
    (backlog).
  - Capacité 10k : à 100 webhooks/s × 24h = 8.6M entries. Cap = éviction
    LRU ; rares faux négatifs sur redelivery > 24h OK (seuil GitHub).

### Commit 4 — `fix(cp-api/workers): at-least-once Kafka commit + precise idempotency classification`

- **Closes** : H.7, H.8 (Group C)
- **Diff** :
  - `_create_consumer` : `enable_auto_commit=False`.
  - `_dispatch_event` : après `run_coroutine_threadsafe`, attendre
    `future.result(timeout=60)`. Si succès → `self._consumer.commit()`.
    Exception → log + PAS de commit (re-livraison au prochain poll).
  - `_handle_event` : `except ValueError` n'est plus un passe-droit —
    discriminer `"already exists"`/`"not found"` in message. Autres
    ValueError → traiter comme erreur retriable.
- **Arbitrage résolu** :
  - **Sérialisation par partition** : acceptée — topic bas trafic en
    démo. Optimisation commit-batch = P3, hors scope.
  - **Timeout `future.result`** : 60s = 2× timeout HTTP provider
    (`DEFAULT_TIMEOUT_S=30`). Si dépassé → log + commit (on avance, sinon
    on bloque indéfiniment).
  - Actually no — si `future.result(60)` timeout, NE PAS committer
    (event non traité) et annuler le future. Documenter dans commit :
    "timeout treated as failure, message re-delivered".
- **Régression tests** :
  `tests/test_regression_cp1_p1_worker_reliability.py` (4 tests)
- **Risques** :
  - Si le topic remplit beaucoup de redelivery (mauvais handler), le
    consumer bloque par message. Monitoring prometheus `GIT_SYNC_RETRIES_TOTAL`
    à aligner.
  - Passage à manual commit : si le commit lui-même raise (broker
    injoignable), le message sera retraité. OK car les handlers
    catalog sont idempotents (create → "already exists" path).

---

## 4. Arbitrages transverses

1. **Déjà fixé par P0 ?** Vérifié bug par bug :
   - H.1/H.2/H.3/H.4/H.5/H.6/H.8/H.10 : **non couverts** par P0 (C.1→C.7 ne
     touchent ni le router `git.py` ni `deployment_orchestration_service` ni
     `list_tree` ni le worker). OK à commiter.
   - H.7 (Kafka auto-commit) : P0 n'a pas touché `git_sync_worker.py`.
     Confirmé.

2. **Retry/timeout policy unifiée ?** **Non**. P0 a déjà introduit
   `run_sync` + semaphores + timeout dans `git_executor.py`. Dupliquer un
   RETRY_POLICY ici fight les SDK retries (PyGithub / python-gitlab). Les
   fixes H restent localisés : H.4/H.5 consomment les exceptions qui
   remontent du wrapper existant, H.7 durcit Kafka seul. Pas de nouvelle
   abstraction.

3. **Observabilité consolidée ?** Partiellement :
   - H.3 → log `exc_info=True` + `request_id` via contextvars (déjà
     en place dans middleware `http_logging.py`).
   - H.5 → même strat.
   - H.7/H.8 → métriques Prometheus existent déjà (`GIT_SYNC_TOTAL`,
     `GIT_SYNC_RETRIES_TOTAL`) ; H.8 les rend plus précises.
   - Pas de commit obs-only : c'est intégré dans chaque commit concerné.

4. **H.10 fix maintenant ou backlog ?** **Fix maintenant**. Coût 5 LOC
   + 4 tests. Défense en profondeur requise par attentes DORA BDF. Tout
   refactor futur introduisant `os.path.normpath` ouvre la fenêtre — le
   garde-fou doit être côté router, pas côté provider.

5. **Dépendance inter-commit ?** Non — les 4 commits sont indépendants :
   - Commit 1 (services) et Commit 2 (router) partagent la sémantique
     `FileNotFoundError → 404` mais ne dépendent pas l'un de l'autre
     (la normalisation existe déjà post-C.6).
   - Commit 3 (webhooks) et Commit 4 (worker) sont isolés.
   - Ordre de commit suggéré : 1 → 2 → 3 → 4 (services → router →
     webhooks → worker) par cohérence de revue.

---

## 5. Risques globaux identifiés

| Risque | Commit | Mitigation |
|---|---|---|
| Tests existants asserting `detail` string cassent | 2 | Recherche `assert.*detail.*Failed to.*:` pendant Phase 2, ajustement ciblé |
| Dedup in-memory ne tient pas en multi-replica | 3 | Vérifier `replicas: 1` dans chart + backlog P2/P3 pour Redis |
| Consumer block sur `future.result(60s)` en boucle si handler HS | 4 | Log `GIT_SYNC_TOTAL{status="error"}` + alerte Prometheus |
| Normalisation list_tree casse un caller silencieux | 1 | `grep -rn "list_tree\(.*\)\." src/` avant commit pour recenser les callers |
| 502/504 surprise le frontend | 2 | Note explicite dans PR description, tag `@frontend-owner` |

---

## 6. Validation Phase 3 (à exécuter après les 4 commits)

1. `pytest tests/ --asyncio-mode=auto -x -v`
2. `ruff check src/`
3. `mypy src/services/git*.py src/routers/git.py src/routers/webhooks.py src/services/deployment_orchestration_service.py src/workers/git_sync_worker.py src/services/webhook_dedup.py`
4. `grep -rn "self._project\." src/ --include="*.py" | grep -v "_test"` → toujours 0
5. `grep -rn "contextlib.suppress(Exception)" src/services/ --include="*.py"` → toujours 0 sur deployment_orchestration
6. Smoke manuel : 3 scénarios
   - POST `/webhooks/gitlab` avec même `X-Gitlab-Webhook-UUID` 2× → 2e réponse `status="duplicate"`
   - DELETE `/v1/tenants/X/git/files/doesnotexist.yaml` → 404 (inchangé)
   - DELETE `/v1/tenants/X/git/files/valid.yaml` avec provider down → 502 (nouveau)
7. Mettre à jour `BUG-REPORT-CP-1.md` : marquer H.1-H.8, H.10 avec commit SHA dans l'encadré "P1 batch status".

---

**Phase 1 complete. STOP for validation before implementing.**

---

## 7. Amendments post-review (2026-04-23, green-light)

Human reviewer approved with 3 mandatory changes + 1 follow-up note.

### 7.1 Commit 3 / H.1 — dedup key priority + claim lifecycle

- **GitLab key priority** : `Idempotency-Key` **first** (stable across retries
  per GitLab webhooks doc) ; fallback `X-Gitlab-Webhook-UUID` (per-webhook
  unique). **Never** use `X-Gitlab-Event-UUID` as primary key — it is shared
  across recursive webhooks, so deduping on it swallows legitimate events.
- **GitHub key** : `X-GitHub-Delivery` stays the right one.
- **Claim lifecycle** : not a simple "seen" flag. Three-state:
  - `claim` (inserted when entering the pipeline, after auth, before any
    side effect).
  - `done` (set after the pipeline completes successfully).
  - on exception → **release the claim** so the next retry is not
    answered with `status="duplicate"` (which would lose the event).
- **Contract** : a delivery with an existing `done` entry → 200 +
  `status="duplicate"`, no side effect. A delivery with an in-flight `claim`
  → 200 + `status="in-flight"` (GitHub re-delivers only after 10s timeout,
  so this is a real collision between replicas or slow handlers). A delivery
  with no entry → normal flow + `claim` set.
- **Ordering** : still after auth (C.7 + GitHub doc on signature-before-
  process). Implemented entirely in-memory for P1 — single-replica
  assumption documented, Redis-backed version = P2/P3 follow-up issue.

### 7.2 Commit 2 / H.5 — tighten `FileNotFoundError → []` scope

- Keep `FileNotFoundError → []` **only** for `get_tree` (path doesn't exist
  = empty listing, natural contract).
- `list_commits` — `FileNotFoundError` on a path-scoped call can still mean
  "no such path" → treat as `[]` when `path` is set ; otherwise 502.
- `list_branches`, `list_merge_requests` — **no** natural "file missing"
  notion. A missing repo = upstream misconfig, not empty list. Must return
  502 (provider/config) or 504 (timeout) instead of silent `[]`.

### 7.3 Commit 2 / H.10 — control chars, not just `\x00`

- Reject: any segment == `..`, absolute path (`/...`), backslash, **any
  ASCII control character** (range `\x00`–`\x1f` plus `\x7f`).
- Implementation: single regex or `any(ord(c) < 0x20 or ord(c) == 0x7f for c
  in path)` guard in `_validate_file_path`.

### 7.4 Commit 1 / H.2 — keep deployment_orchestration provider-agnostic

- `_sync_api_from_git` : catch **only** `FileNotFoundError`. Let
  `TimeoutError`, `GitlabGetError`, `GithubException`, `GitLabRateLimitError`
  propagate untouched. Do **not** import provider-specific exception
  classes in this layer — that couples the orchestration service to the
  PyGithub / python-gitlab implementations, defeating the CAB-1889
  `GitProvider` abstraction.
- Log message on the caught `FileNotFoundError` stays (expected path).
- Comment in the except clause to document why we do NOT widen it.

### 7.5 Commit 4 follow-up — rebalance / partition revoke note

- Our worker uses `kafka-python` (sync, not `aiokafka`). Manual-commit +
  rebalance corner case still applies: between `future.result()` success
  and `consumer.commit()`, a rebalance can reassign the partition → the
  next consumer re-reads the same offset → duplicate delivery. Current
  handlers are idempotent by design (create → "already exists" path), so
  this is acceptable for P1.
- Follow-up (backlog, not P1) : add `on_partitions_revoked` hook that
  commits pending offsets before yielding the partition. Documented in
  the commit body so future investigators see the reasoning.

### 7.6 Final commit ordering (unchanged)

1. Commit 1 (services) → 2 (router) → 3 (webhook) → 4 (worker).

