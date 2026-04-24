# BUG-REPORT-CP-1

> **CP-1 CLOSED (2026-04-23 pm)** — 21 findings / 21 fixed (6 P0 + 9 P1 +
> 5 P2 + L.2 already-closed in P1). P0 landed as PR #2496
> (squash `4ed80850b`), P1 as PR #2499 (squash `b58bdca40`), P2 on
> `fix/cp-1-p2-batch` rebased on top of origin/main.
> All three regression-guard invariants hold:
>
> - `grep -rn "self\._project\." src/ --include="*.py"` → 0 (CP-1 P0 C.1)
> - `grep -rn "contextlib.suppress(Exception)"` inside `_sync_api_from_git`
>   → 0 (CP-1 P1 H.2; the one remaining match is an unrelated
>   `adapter.disconnect()` cleanup in `deploy_api_to_env`)
> - `grep -rn 'ref="main"\|branch="main"'` across provider services and
>   ancillary catalog callers → 0 (CP-1 P2 M.4)
>
> Regression tests: 88 across 9 files
> (`test_regression_cp1_sync_in_async.py`,
> `test_regression_cp1_token_leak.py`,
> `test_regression_cp1_webhook_auth_first.py`,
> `test_regression_cp1_p1_service_contracts.py`,
> `test_regression_cp1_p1_router_errors.py`,
> `test_regression_cp1_p1_webhook_dedup.py`,
> `test_regression_cp1_p1_worker_reliability.py`, plus 5 P2 files listed
> below).
>
> Archive path: `stoa-docs/audits/2026-04-23-cp-1/` (post-merge).

> **Document status**: audit artifact produced post-rewrite of CP-1
> (GitProvider abstraction, CAB-1889). **Revision 2** (2026-04-23 pm) —
> incorporates editorial feedback on provider-library defaults (PyGithub
> throttle/retry/timeout par défaut, python-gitlab `obey_rate_limit` +
> `max_retries=10` par défaut). Lifetime: reviewable until the P0/P1/P2
> batches ship, then archive in `stoa-docs/audits/2026-04-23-cp-1/`.
> Owner: @PotoMitan.

> **P0 batch status (2026-04-23)** — all six P0 findings fixed on
> branch `fix/cp-1-p0-batch`:
>
> | Bug | Commit | Fix |
> |---|---|---|
> | C.1 | `96bee87f9` | services/git_executor.py + GitLab/GitHub migration |
> | C.2 | `b957768d6` | GIT_ASKPASS helper + logging filter |
> | C.4 | `96bee87f9` | GITLAB_SEMAPHORE now uniform via run_sync |
> | C.5 | `96bee87f9` | GitHub semaphores read=10 / contents-write=1 / meta=5 |
> | C.6 | `96bee87f9` | write_file create-first + GitLab last_commit_id |
> | C.7 | `672267d63` | gitlab_webhook: verify token before DB write |
>
> Plus `b0ab0620b` (connect closure hardening) and `eb5984259` (lint
> cleanup). Regression guards: 29 new tests across
> `test_regression_cp1_sync_in_async.py`,
> `test_regression_cp1_token_leak.py`,
> `test_regression_cp1_webhook_auth_first.py`.

> **P1 batch status (2026-04-23 pm)** — all nine P1 findings fixed on
> branch `fix/cp-1-p1-batch` (4 atomic commits):
>
> | Bug | Commit | Fix |
> |---|---|---|
> | H.1 | `52ba19012` | webhook_dedup.py claim/process/done state machine, Idempotency-Key priority |
> | H.2 | `4818b023a` | narrow `except FileNotFoundError` in `_sync_api_from_git`, keep provider-agnostic |
> | H.3 | `71f646f33` | router `_map_provider_exception` → stable generic detail, no `str(e)` leak |
> | H.4 | `71f646f33` | `delete_file` tri-state mapping: FileNotFoundError→404, TimeoutError→504, other→502 |
> | H.5 | `71f646f33` | listing routes surface 502/504 instead of silent `[]` (get_tree keeps FNF→[]) |
> | H.6 | `4818b023a` | `github_service.list_tree` returns `[]` on file path (no singleton blob) |
> | H.7 | `65abd37e1` | Kafka `enable_auto_commit=False` + manual commit after handler success |
> | H.8 | `65abd37e1` | discriminate ValueError by "already exists"/"not found" — unknown = error |
> | H.10 | `71f646f33` | `_validate_file_path` rejects `..`, absolute, backslash, ASCII control chars |
>
> Regression guards: 49 new tests across
> `test_regression_cp1_p1_service_contracts.py` (7),
> `test_regression_cp1_p1_router_errors.py` (17),
> `test_regression_cp1_p1_webhook_dedup.py` (18),
> `test_regression_cp1_p1_worker_reliability.py` (7).
>
> **P1-adjacent bonus**: L.2 (webhook 500 leaks str(e)) closed
> alongside H.1 in `52ba19012` — same class of bug as H.3.

> **P2 batch status (2026-04-23 pm)** — all 5 P2 findings fixed on branch
> `fix/cp-1-p2-batch` (1 atomic commit):
>
> | Bug | Fix |
> |---|---|
> | M.2 | `merge_merge_request` short-circuits on `pr.merged` / `mr.state=="merged"` only; closed-unmerged still raises. No double-fetch on idempotent path (GitHub), reuse mutated MR on GitLab. |
> | M.4 | New `settings.git.default_branch` (env `GIT_DEFAULT_BRANCH`, default `"main"`). Provider method signatures switched to `ref: str \| None = None` / `branch: str \| None = None` with resolution at the method boundary. 50+ internal `"main"` literals swept. Ancillary callers (`iam_sync`, `deployment_orchestration`, `routers/traces`) drop explicit refs. |
> | M.5 | `connect()` retries transient failures (network, `TimeoutError`, 5xx, 429) with **3 attempts / 2 sleeps (1s → 2s)**, 15s per-attempt timeout. Fails fast on 401/403 and other non-transient errors. Helpers `_is_transient_gitlab_error` / `_is_transient_github_error` at module scope. |
> | M.6 | `list_all_mcp_servers` fans out per-tenant listings via `asyncio.gather` on both providers; platform-scope fetch runs concurrently with the tenant enumeration. Provider semaphores (`GITLAB_SEMAPHORE` / `GITHUB_READ_SEMAPHORE`) keep the overall concurrency bounded. |
> | L.1 | GitLab `list_branches` and `list_merge_requests` pass `get_all=True`; `list_commits` uses `iterator=True` + `per_page=min(limit,100)` + `itertools.islice(..., limit)` so the `limit` contract survives while full pagination is restored. |
>
> Regression guards: 10 new tests across
> `test_regression_cp1_p2_merge_idempotent.py` (2),
> `test_regression_cp1_p2_default_branch.py` (2),
> `test_regression_cp1_p2_connect_retry.py` (2),
> `test_regression_cp1_p2_list_all_mcp_gathered.py` (2),
> `test_regression_cp1_p2_gitlab_pagination.py` (2).
>
> Also updated `test_regression_cab_1889_external_git_leaks.py`,
> `test_git_service.py::TestListCommits`,
> `test_deployment_orchestration_service.py::TestRegressionCab1889`,
> `test_iam_sync_service.py::TestRegressionCab1889` to assert the new
> "caller drops explicit ref" contract.

**Module**: CP-1 — GitProvider abstraction in `control-plane-api`
**Path**: `control-plane-api/src/services/git_provider.py`, `git_service.py`, `github_service.py`, `src/routers/git.py`, `src/routers/webhooks.py`, `src/services/iam_sync_service.py`, `src/services/deployment_orchestration_service.py`, `src/workers/git_sync_worker.py`
**Scope**: ~3 200 LOC across 8 files
**Method**: categorised walkthrough A–G (concurrency / error-handling / contract drift / business logic / perf / observability / security), cross-checking the rewrite artefact `REWRITE-BUGS.md` (6 known bugs, 1 closed, 5 pending)
**Date**: 2026-04-23 (Rev 2)
**Prior art**: 6 bugs dans `REWRITE-BUGS.md`. Cet audit expand BUG-03 et surface 15 bugs net additionnels après consolidation.

---

## Executive summary

**21 findings** (après dedup : M.1 retiré, M.3 fusionné dans C.5, M.7 fusionné dans C.6, H.9 absorbé dans C.1/C.5) :

- **6 Critical (P0)** — concurrence architecturale + sécurité
- **9 High (P1)** — error-handling + contract drift + observabilité + hardening
- **4 Medium (P2)** — robustesse + perf
- **2 Low** — hygiène

**Top 3 risques confirmés** :

1. **Les deux clients providers sont synchrones sous `async def`** (C.1, revu). PyGithub ET python-gitlab reposent sur `requests.Session`. Ils exposent des méthodes `def` ordinaires appelées depuis des `async def` handlers FastAPI sans `asyncio.to_thread()` — la boucle asyncio bloque pour toute la durée du round-trip HTTP provider. Les throttles/retries par défaut (PyGithub 2.1+ : 0.25s entre reads, 1s entre writes ; python-gitlab : `obey_rate_limit=True`, `max_retries=10`) s'exécutent DANS ce chemin synchrone, amplifiant le blocage.

2. **Token leak via `git clone`** (C.2). Le secret est passé dans **l'argv du process `git`** (URL HTTPS authentifiée). C'est ça le bug confirmé — l'argv d'un process est exposé à `ps`, aux logs process et à tout caller qui wrap l'exception. La fuite additionnelle par `stderr` est plausible mais non garantie.

3. **Webhook DoS amplification** (C.7). Le trace DB est inséré AVANT la vérification du token/signature. Un flood non-authentifié génère 1 insert + 2 updates par requête.

---

## Critical (6)

### C.1 — Les deux clients providers bloquent la boucle asyncio : sync-in-async — **FIXED (96bee87f9)**

**Files**: `control-plane-api/src/services/github_service.py` (toutes méthodes sauf `clone_repo`), `control-plane-api/src/services/git_service.py` (toutes méthodes sauf `clone_repo`)

**Nature** :
- `GitHubService` déclare `async def` partout et délègue à PyGithub. PyGithub expose des méthodes `def` synchrones (`repo.get_contents()`, `repo.create_file()`, `repo.get_commits()`, `repo.create_git_tree()`, etc.). Aucun `asyncio.to_thread()`.
- `GitLabService` même pattern avec `python-gitlab` : `self._project.repository_tree(...)`, `self._gl.projects.get(...)`, `self._project.files.create(...)`. `python-gitlab.Gitlab.http_request` utilise `requests.Session` (sync).

**Ce qui n'est PAS le bug** : PyGithub ≥ 2.1.0 a un throttle par défaut (`0.25 s` entre requests, `1.0 s` entre writes) et un retry par défaut ; python-gitlab a `obey_rate_limit=True` et `max_retries=10` par défaut. Ces protections existent — le rapport initial les sous-estimait.

**Ce qui EST le bug** : toutes ces protections s'exécutent dans un chemin `def` synchrone. Quand un handler FastAPI `async def get_tree` fait `await git.list_tree(...)`, le `await` revient immédiatement sur l'awaitable, mais à l'intérieur du `async def list_tree`, l'appel `repo.get_contents(...)` est synchrone : il bloque le thread de boucle asyncio pour la durée du round-trip HTTP + throttle. Toutes les autres requêtes FastAPI attendent.

**Reproduction** : 20 GET `/v1/tenants/*/git/files/*` concurrents → serialisation via event loop → latence × 20.

**Impact** : architectural — touche toute l'application, pas seulement les routes git (y compris health checks, keycloak sync, etc., qui partagent la même boucle).

**Fix direction** : `asyncio.to_thread(func, *args)` wrapper autour de chaque appel provider SDK. Ou migrer vers un client async-native (`ghapi`, `httpx` + REST GitHub/GitLab raw) — rewrite plus lourd mais résout proprement.

---

### C.2 — Token GitLab/GitHub exposé dans l'argv de `git clone` + stderr — **FIXED (b957768d6)**

**Files**: `src/services/git_service.py:148-164`, `src/services/github_service.py:136-152`

```python
# git_service.py:151
authed_url = repo_url.replace("https://", f"https://oauth2:{token}@")
proc = await asyncio.create_subprocess_exec("git", "clone", ..., authed_url, ...)
_, stderr = await proc.communicate()
if proc.returncode != 0:
    raise RuntimeError(f"git clone failed: {stderr.decode().strip()}")
```

**Confirmé** : le token est dans **l'argv du process** `git clone`. `ps aux` affiche l'argv pour tout user ayant accès au pod/hôte, les logs d'audit process capturent l'argv, et tout wrapper applicatif qui formatte `proc.args` le propage.

**Plausible (non garanti)** : git CLI / libcurl n'affiche normalement PAS l'URL authenticated dans stderr sur failure standard. Mais avec `GIT_TRACE=1` / `GIT_CURL_VERBOSE=1` activés (y compris par erreur en prod), l'URL remonte dans stderr — et stderr remonte dans l'exception `RuntimeError`, qui peut atterrir dans les logs centralisés ou la réponse HTTP (cf. H.3 pour le leak via HTTPException).

**Impact** : divulgation de PAT GitLab/GitHub avec droits écriture catalog. Incident de sécurité à déclarer DORA-grade.

**Fix direction** : ne jamais passer le token dans l'argv. Alternatives :
- `GIT_ASKPASS` pointant vers un helper qui lit le secret depuis un fd temporaire
- Utiliser `git config credential.helper` au sein du tempdir
- Commande `git -c http.extraHeader="Authorization: bearer $TOKEN" clone <https_url>` (sans token dans l'URL, header privé à ce process)

---

### C.3 — ~~Path traversal~~ (déplacé en H.10 — security hardening, non exploitable aujourd'hui)

*Voir H.10. Downgrade justifié : GitLab Repository Files API rejette `/../` côté serveur et GitHub Git tree APIs traitent les paths comme littéraux. Le bug est réel comme défense-en-profondeur mais non-P0.*

---

### C.4 — `_fetch_with_protection` semaphore non appliqué uniformément — **FIXED (96bee87f9)**

**File**: `src/services/git_service.py:26-63`

**Nature** : `_fetch_with_protection` wrappe 3 protections applicatives :
1. `GITLAB_SEMAPHORE = asyncio.Semaphore(10)` — cap la concurrence applicative.
2. `asyncio.timeout(5.0)` — timeout par-appel.
3. Retry custom sur 429 avec backoff.

Le wrapper est appelé à **seulement 2 sites** : `list_apis_parallel` (ligne 514) et `get_all_openapi_specs_parallel` (ligne 529). Les 23+ autres méthodes de `GitLabService` l'ignorent.

**Correction du rapport initial** : le retry 429 et le backoff existent ALREADY au niveau `python-gitlab.Gitlab` (`obey_rate_limit=True`, `max_retries=10` par défaut). Donc "no 429 retry at all" est faux. Ce qui reste vrai :
- **Aucun cap applicatif de concurrence** : sans le semaphore, 50 requêtes concurrentes partent en 50 round-trips parallèles vers GitLab — c'est la fonction du semaphore 10.
- **Timeout applicatif non uniforme** : seul le `timeout` passé à `_fetch_with_protection` est appliqué. `python-gitlab` a son timeout par défaut (configurable au constructor) — pas exposé dans le code, donc défaut silencieux.

**Reproduction** : 50 requêtes concurrentes `GET /v1/tenants/*/git/files/*` sur GitLab → 50 calls parallèles (pas les 10 attendus) → risque de secondary rate limit GitLab.

**Impact** : le protocole CAB-688 obligation #1 (cap concurrence 10) n'est respecté qu'à 2 endroits sur 25+. Les retries 429 eux sont bien assurés par `python-gitlab` côté client ; le semaphore applicatif était là en défense supplémentaire mais ne protège quasi rien.

**Fix direction** : appliquer `_fetch_with_protection` (ou un décorateur équivalent) à chaque méthode publique de `GitLabService`. Alternative plus clean : wrapper le client `gitlab.Gitlab` à l'init avec un hook pre/post-request qui acquiert le semaphore.

---

### C.5 — Aucun cap applicatif de concurrence sur GitHub + sync-in-async amplifie — **FIXED (96bee87f9)**

**File**: `src/services/github_service.py` (entier)

**Nature** : zéro équivalent de `GITHUB_SEMAPHORE`. Les méthodes "parallèles" (`list_apis_parallel:333`, `list_mcp_servers:439`) font `asyncio.gather(*[...])` sans borne.

**Correction du rapport initial** : PyGithub ≥ 2.1.0 a un throttle par défaut (0.25s reads / 1s writes), un timeout par défaut (15 s), un retry par défaut. Donc "no protection at all" est faux. Ce qui reste vrai :
- **Aucun cap applicatif** : pour un tenant avec 500 APIs, `list_apis_parallel` spawn 500 tasks. PyGithub les sérialise de facto via son throttle — mais le buffer task + l'event loop pollué par C.1 rendent la chose pire que séquentiel pur.
- **Sync-in-async (C.1)** amplifie le problème : les 500 tasks sont crées en bulk, toutes blockantes, la boucle asyncio fait du ping-pong entre elles sans avancer réellement.

**M.3 absorbé ici** : `list_apis_parallel` + `list_mcp_servers` unbounded gather → symptôme du même bug.

**Reproduction** : tenant avec 500 APIs → `/v1/tenants/X/apis` avec GitHub backend → latence observable 50×-100× plus haute qu'attendu pour le "parallel" fetcher.

**Fix direction** : `GITHUB_SEMAPHORE = asyncio.Semaphore(10)` (reads) + `asyncio.Semaphore(5)` (writes), appliqué en wrapper sur chaque méthode publique. Combinable avec l'offload `asyncio.to_thread` de C.1 — le semaphore limite alors réellement la concurrence, pas juste la task count.

---

### C.6 — TOCTOU sur `write_file` + création/update/delete non-idempotents (both providers) — **FIXED (96bee87f9)**

**Files**: `src/services/git_service.py:1012-1031`, `src/services/github_service.py:947-955` + `github_service.py:672-673` (M.7 absorbé)

**Renforcement vs rapport initial** : GitHub documente explicitement dans la doc "Contents" que les endpoints create/update/delete file doivent être utilisés **sériellement** sur un même path car les requêtes parallèles **provoquent des conflits**. Le pré-check `_file_exists()` suivi de `create_file` ou `update_file` viole cette recommandation ET introduit une fenêtre TOCTOU en amont.

**Écho côté GitLab** : GitLab Repository Files API expose `last_commit_id` précisément pour permettre de la concurrence optimiste sur update/delete — jamais utilisé par le code actuel.

**Reproduction** : deux POST concurrents `/v1/tenants/X/git/files/foo.yaml` :
- Deux `_file_exists == False` → deux `create_file` → le 2e raise `ValueError("File already exists")` → remonté en 500 via H.3.
- Deux `_file_exists == True` → deux `update_file` → commits en course, GitHub peut reject "sha mismatch", GitLab peut accepter en silencieux avec perte du premier write.

**M.7 absorbé** : `create_api` GitHub (`github_service.py:672-673`) a la même structure `if _file_exists → raise; else → create`. Même TOCTOU.

**Impact** : silent data loss dans le catalog GitOps sous concurrence. Pour BDF qui audite le catalog pour DORA, fenêtre de désync non-traçable.

**Fix direction** :
- GitHub : rely sur 422 du `create_file` pour détection "already exists"; pour update, passer la `sha` en argument du router et vérifier matching.
- GitLab : utiliser `last_commit_id` dans `file.save()` pour optimistic concurrency; sur 409, renvoyer l'erreur au caller qui retry avec la version fraîche.

---

### C.7 — Webhook trace DB insert AVANT vérification token — DoS amplification — **FIXED (672267d63)**

**File**: `src/routers/webhooks.py:143 (GitLab), 279 (GitHub)`

**Nature** : l'insertion `service.create(trace, ...)` précède la validation `verify_gitlab_token` / `verify_github_signature`. Un attaquant non-auth flood l'endpoint → 1 insert + 1-2 updates par request sans coût d'authentification.

**Reproduction** : `for i in {1..10000}; do curl -X POST $CP/webhooks/gitlab -d '{"fake":true}'; done` → 10k inserts `traces` + 20k updates.

**Impact** : pression DB soutenue. Combiné avec C.1 (event loop bloqué durant chaque DB write sync-in-async), cascade vers les routes légitimes. Les headers nécessaires à une vérification précoce (`X-Gitlab-Token`, `X-Hub-Signature-256`) sont lus AVANT la signature mais utilisés APRÈS l'insert.

**Fix direction** : reordering. Le flow correct :
1. Lire `x_gitlab_token` / `x_hub_signature_256`
2. `verify_*` → si false, `raise HTTPException(401)` sans DB write
3. SEULEMENT alors `service.create(trace, ...)` et la suite

Coût : ~10 LOC de réorganisation par handler.

---

## High (9)

### H.1 — Webhook replay : aucune déduplication par `X-GitHub-Delivery` / `X-Gitlab-Webhook-UUID`

**File**: `src/routers/webhooks.py` (entier)

**Nature** : GitHub recommande explicitement d'utiliser `X-GitHub-Delivery` pour dédupliquer, avec nuance : une "redelivery" manuelle réutilise le même delivery ID mais une livraison automatique après timeout en génère un nouveau. GitLab expose `X-Gitlab-Webhook-UUID`, `X-Gitlab-Event-UUID`, et `Idempotency-Key`.

Aucun de ces headers n'est lu par le code actuel. Un webhook rejoué = deuxième exécution du pipeline.

**Impact** : 2× publish Kafka, 2× trace, 2× sync catalog. Pour events mutants (api-create), second échoue avec "already exists" → compté comme erreur (ou comme success faussement positif via H.8).

**Fix direction** : cache LRU in-memory ou Redis (10k entries × 24h TTL) sur delivery_id.

---

### H.2 — `contextlib.suppress(Exception)` swallow dans deployment_orchestration

**File**: `src/services/deployment_orchestration_service.py:116-124`

Rate limits, timeouts, parse YAML, auth failures — tous avalés silencieusement. `_upsert_api` reçoit `None` commit_sha et continue sans distinguer "pas de spec" de "impossible de fetch".

**Fix** : `except FileNotFoundError: None ; except (RateLimitError, TimeoutError) as e: raise` — distinguer récupérable vs attendu.

---

### H.3 — Router leak `str(e)` dans HTTPException detail

**File**: `src/routers/git.py:184, 209-210, 254-255, 273-274, 310-311`

```python
except Exception as e:
    raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")
```

`str(e)` sur exceptions PyGithub / python-gitlab contient URL API, headers, request IDs, parfois fragments de path internes. Amplifié par C.2 si le token est dans une URL partiellement masquée.

**Fix** : `detail="Internal error"` + log full error serveur + request_id dans response pour corrélation.

---

### H.4 — `delete_file` convertit TOUTES exceptions en 404

**File**: `src/routers/git.py:205-212`

Timeout, 500 provider, 401 → tous deviennent 404. Cache les pannes sous un résultat "normal".

**Fix** : `except FileNotFoundError: 404`, `except Exception: 500`.

---

### H.5 — `list_*` endpoints silencieusement `[]` sur toute erreur

**File**: `src/routers/git.py:123-125, 160-161, 229-231, 290-292`

4× pattern `except Exception: return []`. Auth errors, rate limits, 500s → tous deviennent liste vide. UI affiche "aucun commit/MR/branche" au lieu de signaler panne.

**Fix** : 502 Bad Gateway avec raison pour routes user-facing.

---

### H.6 — `list_tree` contract drift : fichier vs dossier entre providers

**Files**: `src/services/git_service.py:996-1003`, `src/services/github_service.py:905-922`

**Reformulation** : l'audit initial prétendait que GitLab renvoie `[]` sur `path=<fichier>`. Plus prudent : c'est un **contract drift inter-provider** sur l'abstraction CP-1.

- GitHub documente que "Get repository content" retourne **un objet unique** pour un fichier et **un tableau** pour un dossier. Le code ligne 914 wrappe l'objet unique en `[contents]` → propage comme `TreeEntry(type="blob", ...)` au caller.
- GitLab `repository_tree` est un endpoint de **listing de tree** exclusivement. Sur un path qui pointe un fichier, comportement mal documenté (vide ou 404 selon version).

La divergence existe et doit être normalisée dans l'abstraction, indépendamment du comportement exact de GitLab.

**Fix direction** : dans `github_service.list_tree`, si `contents` n'est pas une list → retourner `[]` (le contrat ABC dit "list children" et un fichier n'a pas de children).

---

### H.7 — Kafka `enable_auto_commit=True` → perte d'events au crash worker

**File**: `src/workers/git_sync_worker.py:150`

aiokafka/kafka-python documente explicitement que `enable_auto_commit=True` peut mener à perte de données au crash. Recommandation standard : `enable_auto_commit=False` + commit manuel APRÈS succès async.

**Impact** : API créé via Kafka event, worker crashe post-auto-commit pré-write GitHub → catalog divergent sans alerte.

**Fix** : `enable_auto_commit=False`, `self._consumer.commit()` après `_handle_event` OK.

---

### H.8 — `ValueError` classifié success dans retry loop

**File**: `src/workers/git_sync_worker.py:242-246`

`except ValueError: status="success"` — mais ValueError est une large catégorie. `batch_commit("unknown action")` raise ValueError (ligne 528) et compte comme success. Métriques biaisées.

**Fix** : discriminer `"already exists" in str(e)` ou `"not found" in str(e)` pour success ; reste = error.

---

### H.10 — Path sanitization manquante dans `_tenant_path` (hardening, security-adjacent)

**File**: `src/routers/git.py:98-101`

*Déplacé depuis C.3 (rapport v1) — non P0 car non exploitable aujourd'hui.*

```python
def _tenant_path(tenant_id: str, path: str = "") -> str:
    base = f"tenants/{tenant_id}"
    return f"{base}/{path}" if path else base
```

`file_path` capturé via `{file_path:path}` FastAPI accepte `..`, `\x00`, backslashes, paths absolus. Aucune sanitisation.

**Non exploitable aujourd'hui** : GitLab Repository Files API documente `/../` comme rejeté côté serveur ; GitHub Git tree APIs traitent les paths comme littéraux (pas de normalisation).

**Pourquoi le garder en P1** :
- Tout refactor introduisant `os.path.normpath()` ou `Path().resolve()` ouvre le trou.
- Défense en profondeur (DORA expectations BDF).
- Coût du fix dérisoire (5 LOC + 3 tests).

**Fix** : `if ".." in path.split("/") or "\x00" in path or path.startswith("/"): raise HTTPException(400)`.

---

## Medium (4)

### M.2 — `merge_merge_request` GitHub : pas d'idempotence + double fetch

**File**: `src/services/github_service.py:1013-1017`

Si PR already merged / closed, `pr.merge()` raise. Aucun pre-check. Double `get_pull` (avant + après même iid).

**Fix** : check `pr.merged` / `pr.state` avant merge, retourner ref existant si déjà merged.

---

### M.4 — `ref="main"` hardcodé dans dizaines d'endroits

**Files**: `git_service.py`, `github_service.py` — multiples

Pas de `settings.git.default_branch`. Repo avec `master` ou branche custom silent-fail.

**Fix** : expose default_branch dans settings.

---

### M.5 — `connect()` GitLab sans retry au startup

**File**: `src/services/git_service.py:103-116`

Si GitLab lent/500 au boot CP-API, `connect()` échoue → service démarre en état not-connected → routes 503.

**Fix** : retry exponentiel au connect (3 tentatives, backoff 1/2/4s).

---

### M.6 — `list_all_mcp_servers` GitHub : séquentiel par tenant (N+1)

**File**: `src/services/github_service.py:442-447`

100 tenants × 1 appel list_mcp_servers = 100 calls séquentiels. Avec C.1 (sync PyGithub), ~50s cumulées.

**Fix** : `asyncio.gather` avec semaphore.

---

*Supprimés par rapport à v1 du rapport :*

- ~~M.1 batch_commit delete mode/sha~~ — **REMOVED**. GitHub Git Data API documente `sha: null` comme signal de delete, et PyGithub `InputGitTreeElement(sha=None)` supporte ce cas. Le commentaire de code est trompeur (mode "000000" mentionné alors que "100644" est utilisé) mais le comportement est correct per la doc.
- ~~M.3 list_apis_parallel unbounded~~ — **fusionné dans C.5**.
- ~~M.7 create_api TOCTOU~~ — **fusionné dans C.6**.

---

## Low (2)

### L.1 — Pagination : split par provider

**PyGithub side** : `repo.get_branches()` / `repo.get_pulls()` / `repo.get_commits()` retournent des `PaginatedList`. L'itération est **transparente** — le code qui fait `for b in repo.get_branches()` récupère bien toutes les pages, pas la première seulement. Donc PyGithub n'a PAS le bug de troncation à 30.

**python-gitlab side** : `project.branches.list()` / `project.mergerequests.list()` sans paramètre retourne la **première page seulement** (par défaut 20 items) sauf si `get_all=True` ou `iterator=True` est passé. Le code actuel :
- `list_branches:1042` — `self._project.branches.list()` → **tronqué à 20**
- `list_merge_requests:1081` — `self._project.mergerequests.list(state=state)` → **tronqué à 20**
- `list_commits:697` — `self._project.commits.list(path=path, per_page=limit)` → limite explicite mais pas de all=True

**Impact GitLab** : catalog repo avec >20 branches ou >20 MRs open → liste tronquée silencieusement.

**Fix** : passer `get_all=True` (ou `iterator=True` + boucle) sur chaque `list()` GitLab qui attend une énumération complète.

---

### L.2 — Webhook handler fuit `str(e)` dans HTTPException 500

**File**: `src/routers/webhooks.py:235`

Même pattern que H.3, côté endpoint webhook. Attacker qui trigger exception interne récolte debug info.

**Fix** : `detail="Internal error"` + log interne.

---

## Scope hors bugs — notes de design

- **BUG-01, BUG-02 fixés silencieusement** (iam_sync, deployment_orchestration) mais REWRITE-BUGS.md les liste encore ouverts. Divergence doc/code à clarifier.
- **`MergeRequestRef.iid`** : mapping GitLab iid vs GitHub pr.number correct, contract consistent.
- **`read_file` vs `get_file_content` semantics** : divergence intentionnelle documentée ; piège latent pour refactors.
- **`clone_repo` crée `tempfile.mkdtemp` jamais nettoyé** : fuite `/tmp/stoa-{gl,gh}-*` sur error ET success. Pollution disque, pas exploitable.
- **M.1 removed** : voir section Medium. GitHub API documente `sha: null = delete`, PyGithub supporte — le code est probablement correct même si le commentaire est trompeur.

---

## Priorité de fix (recommandation)

**P0 — avant démo juin** :
- **C.2** (token leak dans argv `git clone`) — security incident grade
- **C.4** (semaphore non uniforme) — fiabilité sous charge
- **C.5** (no GitHub cap + sync-in-async amplifié) — perf + reliability
- **C.6** (TOCTOU write) — silent data loss
- **C.7** (webhook DoS amplification) — surface exposée

**P0 conditionnel (si GitHub provider activé) OU P0 tout court vu que GitLab a le même problème** :
- **C.1** (sync-in-async both providers) — architectural

**P1 — stabilité démo** :
- H.1 (webhook replay), H.6 (list_tree drift), H.7 (Kafka at-most-once), H.10 (path sanitization hardening)
- H.3/H.4/H.5 (error handling router + info disclosure) — groupable

**P2 — hygiène** :
- M.2, M.4, M.5, M.6, L.1 (pagination GitLab), L.2

---

## Références aux suspects du brief

| Suspect | Status | Bug |
|---|---|---|
| R5 semaphore bypass (`_gl.projects.get` writes) | **Confirmé + reformulé** | C.4 (uniformité applicative, pas "no retry") |
| `MergeRequestRef.iid` GitLab iid vs GitHub pr.number | **Correct** | Pas de bug — mapping consistent |
| `list_tree()` GitLab `[]` vs GitHub `[]` | **Contract drift** | H.6 — GitHub renvoie le fichier comme blob si path=file |
| `read_file()` None vs `get_file_content()` raise | **OK intentionnel** | Piège latent documenté |
| Bugs fonctionnels au-delà du leak `_project` (R4 hors-scope) | **Partiel** | iam_sync + deployment_orchestration fixés silencieusement ; nouveaux bugs (H.2) |

---

## Changelog Rev 2 (2026-04-23 pm)

**Corrections après feedback éditorial** :

- **C.1** : étendu à GitLab (python-gitlab aussi sync via requests.Session, vérifié par inspection du code client).
- **C.4** : reformulé. Les retries 429 existent au niveau `python-gitlab` (`obey_rate_limit=True`, `max_retries=10` par défaut). Le bug restant = non-uniformité applicative du semaphore + timeout, pas absence de retry.
- **C.5** : reformulé. PyGithub ≥ 2.1 a throttle/retry/timeout par défaut. Le bug restant = no cap applicatif + sync-in-async amplification. M.3 absorbé ici.
- **C.3 → H.10** : downgrade vers P1 hardening. Non exploitable aujourd'hui (Git APIs traitent les paths littéralement).
- **C.6 renforcé** : référence à GitHub doc "serial usage required", M.7 absorbé.
- **H.9 retiré** : fusionné dans C.1/C.5 (la couverture timeout était déjà présente dans ces sections).
- **M.1 retiré** : GitHub API + PyGithub supportent `sha=None` comme delete signal.
- **M.3, M.7 retirés** : fusionnés respectivement dans C.5 et C.6.
- **L.1 splitté par provider** : PyGithub PaginatedList transparent, seul python-gitlab `list()` tronque par défaut.

**Compte final** : 21 findings solides (vs 25 prétendus en v1). 6 P0 consolidés + 9 P1 + 4 M + 2 L.
