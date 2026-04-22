# REWRITE-PLAN — Git Provider abstraction (CP-1 / CAB-1889)

**Scope** : `src/routers/git.py`, `src/services/git_provider.py`, `src/services/git_service.py`, `src/services/github_service.py`, tests associés.
**Métrique binaire de succès** : zéro accès `_project` ou `_gh` depuis `src/routers/git.py`.

---

## A. Carte des fuites (`src/routers/git.py`)

Fichier actuel : 388 LOC. 45 tests. **17 accès directs aux internals** (tous `_project`), regroupés en **6 domaines métier** :

| # | Ligne | Opération métier | Accès interne | Méthode ABC actuelle | Statut |
|---|-------|------------------|---------------|----------------------|--------|
| 1 | 115 | Lister les commits d'un chemin | `git.list_commits(...)` | ❌ absent de l'ABC (présent sur `GitLabService`, absent de `GitHubService`) | **ABSENT** |
| 2 | 135, 183 | Lire le contenu d'un fichier (None si absent) | `git.get_file(...)` | ❌ `get_file_content` existe mais **raise** FileNotFoundError | **MISMATCH sémantique** |
| 3 | 152, 156 | Vérifier connexion + lister un dossier | `git._project` + `repository_tree(path, ref)` | ❌ `list_files` existe mais retourne `list[str]` (pas `[{name, type, path}]`) | **ABSENT (tree shape)** |
| 4 | 176, 192-198 | Créer un fichier | `git._project.files.create({...})` | ✅ `create_file(project_id, path, content, msg, branch)` existe | **NON UTILISÉ** |
| 5 | 186-189 | Update via file object | `git._project.files.get(...).save(...)` | ✅ `update_file(...)` existe | **NON UTILISÉ** |
| 6 | 219, 226-228 | Supprimer un fichier | `git._project.files.delete(...)` | ✅ `delete_file(...)` existe | **NON UTILISÉ** |
| 7 | 246, 250 | Lister merge requests (state) | `git._project.mergerequests.list(state=...)` | ❌ absent | **ABSENT** |
| 8 | 281, 286-293 | Créer une merge request | `git._project.mergerequests.create({...})` | ❌ absent | **ABSENT** |
| 9 | 321, 325-326 | Merger une merge request (by iid) | `git._project.mergerequests.get(iid).merge()` | ❌ absent | **ABSENT** |
| 10 | 342, 346 | Lister les branches | `git._project.branches.list()` | ❌ absent | **ABSENT** |
| 11 | 370, 375-380 | Créer une branche | `git._project.branches.create({branch, ref})` | ❌ absent | **ABSENT** |

**Constat** :
1. L'ABC existante est inconsistante : `create_file`, `update_file`, `delete_file`, `get_file_content`, `list_files`, `batch_commit` sont définis mais **le router ne les utilise pas** pour les ops fichiers (3 contournements alors que l'API est dispo).
2. 8 opérations métier (tree, commits, get_file nullable, MRs x3, branches x2) ne sont **pas dans l'ABC** — c'est la fuite structurelle.
3. `is_connected()` existe déjà sur la base class (`git_provider.py:196-198`) — utilisable pour remplacer tous les `if not git._project`.
4. Semantic drift `get_file` vs `get_file_content` : l'un retourne `None`, l'autre `raise`. Les callers du router veulent la variante `None`.

**Hors périmètre strict, mais même pattern à documenter** : `src/services/iam_sync_service.py:205-209` et `src/services/deployment_orchestration_service.py:102,122` leak aussi `_project` → 4 accès à sortir dans un suivi (pas dans ce rewrite).

**Responsabilités mélangées dans `git.py`** :
- Routing FastAPI + décorateurs RBAC
- Construction du `scoped_path` (préfixe tenant) — **à garder dans le router** (c'est une règle de scoping tenant)
- Mapping objet provider → Pydantic response (MR, Branch, Commit) — **à descendre dans l'interface** (retour d'objets déjà normalisés)
- Error fallback (return `[]`, return `503`, return `500`) — **à garder dans le router** (c'est la politique HTTP)

---

## B. Nouvelle interface `GitProvider`

Méthodes ajoutées (toutes `async`, type hints complets). Les modèles de retour sont des `dataclass` frozen (colocalisés dans `git_provider.py`) pour éviter le leak PyGitLab/PyGithub.

### Nouveaux types valeur (colocalisés dans `git_provider.py`)

```python
@dataclass(frozen=True)
class TreeEntry:
    name: str
    type: Literal["tree", "blob"]
    path: str

@dataclass(frozen=True)
class CommitRef:
    sha: str
    message: str
    author: str
    date: str

@dataclass(frozen=True)
class BranchRef:
    name: str
    commit_sha: str
    protected: bool

@dataclass(frozen=True)
class MergeRequestRef:
    id: int
    iid: int              # GitLab iid / GitHub pr_number
    title: str
    description: str
    state: str            # opened | merged | closed
    source_branch: str
    target_branch: str
    web_url: str
    created_at: str
    author: str
```

### Méthodes ajoutées à `GitProvider` (ABC)

```python
# Connectivity
def is_connected(self) -> bool: ...   # déjà présent, on s'appuie dessus

# Reads
async def list_tree(self, path: str, ref: str = "main") -> list[TreeEntry]: ...
async def read_file(self, path: str, ref: str = "main") -> str | None:
    """Return file content or None if missing. Does not raise on 404."""
async def list_path_commits(self, path: str | None, limit: int = 20) -> list[CommitRef]: ...

# Files (already exist — use them, kill the _project.files.* leak)
# create_file / update_file / delete_file existent déjà — à signature près (project_id arg).
# → nouvelle surcharge sans project_id qui tape le repo "catalog par défaut" du provider.
async def write_file(self, path: str, content: str, commit_message: str, branch: str = "main") -> None:
    """Create-or-update file on the provider's default catalog repo. Implemented on top of existing create_file/update_file."""
async def remove_file(self, path: str, commit_message: str, branch: str = "main") -> None: ...

# Branches
async def list_branches(self) -> list[BranchRef]: ...
async def create_branch(self, name: str, ref: str = "main") -> BranchRef: ...

# Merge requests / Pull requests
async def list_merge_requests(self, state: str = "opened") -> list[MergeRequestRef]: ...
async def create_merge_request(
    self, title: str, description: str, source_branch: str, target_branch: str = "main"
) -> MergeRequestRef: ...
async def merge_merge_request(self, iid: int) -> MergeRequestRef: ...
```

Contrat sémantique :
- `iid` pour GitLab = `iid`, pour GitHub = `pr.number`. Mapping documenté dans chaque impl.
- Les nouvelles méthodes opèrent sur **le repo catalog du provider** (GitLab `GITLAB_PROJECT_ID`, GitHub `GITHUB_ORG/GITHUB_CATALOG_REPO`). Le router n'a jamais besoin de passer un `project_id`.
- Ne raise pas de 404 implicite → le router ne fait plus le mapping. `read_file` renvoie `None`, `list_tree` renvoie `[]` si le chemin est absent.

### Ce qui ne change pas

- `connect` / `disconnect` / `clone_repo` / `get_file_content` / `list_files` / `create_webhook` / `delete_webhook` / `get_repo_info` / `create_file` / `update_file` / `delete_file` / `batch_commit` / catalog methods (`get_tenant`, `list_tenants`, `get_api`, `list_apis`, `get_api_openapi_spec`, `list_mcp_servers`, …) — **inchangés** (utilisés par `git_sync_worker`, `catalog_admin`, `mcp_gitops`, `tenants`, `deployments`, `apis`, `portal`, `health`, `iam_sync_service`).

---

## C. Découpage fichier

État actuel (LOC) :

| Fichier | LOC | Split dans CP-1 ? |
|---------|-----|-------------------|
| `src/routers/git.py` | 388 | **NON** — sous seuil après cleanup attendu ~280 LOC |
| `src/services/git_provider.py` | 303 | **NON** — grossit ~+80 LOC (types + méthodes ABC) → ~380 |
| `src/services/git_service.py` (GitLab) | 992 | **DIFFÉRÉ** — Phase 2 séparée |
| `src/services/github_service.py` | 898 | **DIFFÉRÉ** — Phase 2 séparée |

**Décision** : le split des deux services est un rewrite à part entière (restructuration fichiers + mixins + backcompat imports). Il n'appartient pas au noyau CP-1 « fermer la fuite d'abstraction ». Il est **sorti de ce plan** et tracé comme Phase 2 CAB-1889 dédiée (voir section **Phase 2 (séparée, hors CP-1)** plus bas).

Dans CP-1 on accepte temporairement que `git_service.py` et `github_service.py` dépassent 500 LOC — ils grossissent un peu plus (les nouvelles méthodes d'interface s'y ajoutent). C'est le prix pour garder CP-1 focalisé sur le contrat.

**Schemas du router** : `git.py` garde ses Pydantic inline (on ne touche pas au shape OpenAPI). Pas de déplacement.

---

## D. Plan d'exécution (bottom-up)

### Étape 0 — baseline (ne code rien)
- [ ] Snapshot OpenAPI : `python -c "from src.main import app; import json; print(json.dumps(app.openapi(), indent=2, sort_keys=True))" > /tmp/openapi-before.json`
- [ ] `pytest tests/test_git_router.py tests/test_git_provider.py tests/test_git_service.py tests/test_github_service.py -q` — note les compteurs (255 tests total, 45 router).
- [ ] `wc -l src/routers/git.py src/services/git_provider.py src/services/git_service.py src/services/github_service.py` — note les tailles.
- **Commit 0** : rien (baseline, outputs archivés dans `/tmp/`).

### Étape 1 — enrichir l'ABC
- [ ] Dans `git_provider.py` : ajouter les dataclasses (`TreeEntry`, `CommitRef`, `BranchRef`, `MergeRequestRef`).
- [ ] Ajouter les méthodes `list_tree`, `read_file`, `list_path_commits`, `write_file`, `remove_file`, `list_branches`, `create_branch`, `list_merge_requests`, `create_merge_request`, `merge_merge_request` — chacune `async` abstraite (raise `NotImplementedError` côté base pour éviter l'ABCError forçant toutes les impls à bouger d'un coup ; `@abstractmethod` seulement sur ce qui est hard-required).
- [ ] Tests : **Étape 1.5** on ajoute `tests/test_git_provider_contract.py` qui fait tourner un contrat minimal (chaque impl doit produire les mêmes dataclasses).
- [ ] `pytest tests/test_git_provider.py -q` : pass.
- **Commit 1** : `refactor(git): extend GitProvider with tree/branches/MR interface (CAB-1889)`.

### Étape 2 — implémenter côté `GitLabService`
- [ ] Ajouter dans `git_service.py` (monolithe toujours) les implémentations des nouvelles méthodes, en mappant sur `self._project.branches/mergerequests/files/commits/repository_tree`. Utiliser les dataclasses pour le retour.
- [ ] `read_file` = wrap de `get_file` existant (déjà nullable).
- [ ] `list_path_commits` = wrap de `list_commits` existant.
- [ ] Unit tests : `tests/test_git_service.py` — ajouter les cas mismatch (`read_file` returns None, `list_tree` returns `[]`).
- [ ] `pytest tests/test_git_service.py -q` : pass.
- **Commit 2** : `feat(git): GitLab impl for tree/branches/MR abstraction (CAB-1889)`.

### Étape 3 — implémenter côté `GitHubService`
- [ ] Ajouter dans `github_service.py` les implémentations (PyGithub). `MergeRequestRef.iid` ← `pr.number`. `list_tree` via `repo.get_contents(path)`. `read_file` = wrap de `get_file_content` qui catch `FileNotFoundError` → `None`. `list_path_commits` via `repo.get_commits(path=...)`.
- [ ] Unit tests : `tests/test_github_service.py` — mêmes cas.
- [ ] `pytest tests/test_github_service.py -q` : pass.
- **Commit 3** : `feat(git): GitHub impl for tree/branches/MR abstraction (CAB-1889)`.

### Étape 4 — réécrire le router `git.py`
- [ ] Remplacer tous les `if not git._project` par `if not git.is_connected()`.
- [ ] Remplacer chaque bloc `_project.xxx` par l'appel interface correspondant :
  - tree → `git.list_tree(scoped_path, ref)`
  - create/update file → `git.write_file(scoped_path, ...)` (consolide les 2 endpoints POST)
  - delete file → `git.remove_file(scoped_path, ...)`
  - MRs → `git.list_merge_requests / create_merge_request / merge_merge_request`
  - branches → `git.list_branches / create_branch`
  - commits → `git.list_path_commits(...)` (remplace `list_commits`)
  - get_file → `git.read_file(...)` (remplace `get_file`)
- [ ] Le mapping dataclass → Pydantic (`BranchInfo(**asdict(b))`) est fait au niveau du router → aucun champ de response model ne bouge.
- [ ] Vérifier que chaque endpoint conserve status code + response schema identique.
- [ ] `grep -n "\._project\|\._gh\|\._repo" src/routers/git.py` → attendu **0**.
- **Commit 4** : `refactor(git): route git.py through GitProvider interface only (CAB-1889)`.

### Étape 5 — rewriter `tests/test_git_router.py`
- [ ] Les tests existants mockent `_project.*` — invalides désormais. Réécrire chaque test pour mocker la méthode d'interface (`mock_git.list_tree.return_value = [...]`, etc.).
- [ ] Les tests de **comportement** (status codes, RBAC, response shape) restent **identiques dans leurs assertions** — seules les setups changent.
- [ ] Compteur de tests ≥ 45 (ajouter 2-3 cas : `is_connected=False`, provider-agnostic GitHub-like MR via `iid`).
- [ ] `pytest tests/test_git_router.py -q` : pass.
- **Commit 5** : `test(git): mock GitProvider interface instead of internals (CAB-1889)`.

### Étape 6 — validation finale
- [ ] `grep -n "\._project\|\._gh\|\._repo\|_internal\|_private" src/routers/git.py` → **0**.
- [ ] `grep -rn "github_service\|gitlab_service" src/routers/git.py` → **0**.
- [ ] `pytest --cov=src --cov-fail-under=70 -q` → green, coverage ≥ 70.
- [ ] `ruff check src/` → 0 issue.
- [ ] `mypy src/services/git_provider.py src/services/git_service.py src/services/github_service.py src/routers/git.py` → 0 nouvelle erreur.
- [ ] `wc -l src/routers/git.py src/services/git_provider.py` → tous les **fichiers touchés dans le périmètre CP-1** < 500. `git_service.py` / `github_service.py` restent > 500 → tracé Phase 2.
- [ ] OpenAPI diff : `diff /tmp/openapi-before.json /tmp/openapi-after.json` → **vide**.

---

## E. Risques identifiés

| # | Risque | Impact | Mitigation |
|---|--------|--------|------------|
| R1 | `test_git_router.py` actuel asserte `_project.xxx.assert_called_once()` → 30+ tests à réécrire | Moyen — dette visible, invalide la "non-régression" des tests actuels | Étape 5 dédiée. Les **assertions sur response body + status code** restent des specs. Les **assertions sur `_project.xxx`** sont reconnues comme testant l'implémentation et légitimement réécrites. |
| R2 | GitHub PR vs GitLab MR : sémantique `iid` ≠ `pr.number` | Moyen | Mapping explicite `iid ← pr.number` documenté dans `GitHubService`. Tests contrat dans `test_git_provider_contract.py`. |
| R3 | `GitHubService` n'a pas de `_project` → `test_git_router.py` mocks casseront en dev local si on switch GIT_PROVIDER=github | Faible | `is_connected()` abstrait cette bifurcation. Les tests n'utilisent plus `_project` après étape 5. |
| R4 | Les callers externes (`iam_sync_service`, `deployment_orchestration_service`) leakent aussi `_project` | Faible (hors périmètre strict) | Documenter dans `REWRITE-BUGS.md`, ticket suivi CAB-1889-follow-up. Ne pas fixer dans ce rewrite. |
| R5 | La méthode `GitLabService._gl.projects.get(project_id)` dans `create_file`/`update_file`/`delete_file` ignore la semaphore `_fetch_with_protection` | Moyen (déjà présent — pas introduit par le rewrite) | Documenter dans `REWRITE-BUGS.md`. Le rewrite n'aggrave pas. |
| R6 | Le bootstrap `git_service = git_provider_factory()` au module-load (`git.py:43`) est un workaround pour le patching de tests (conftest `_git_di_bridge`). Il peut casser si on change l'ordre d'import | Faible | Garder le shim tant que conftest l'utilise. Vérifier à l'étape 4. |
| R7 | `git_service.py` / `github_service.py` dépassent déjà 500 LOC et grossissent encore (~+80 LOC / fichier) dans CP-1 | Faible | Accepté — traité dans Phase 2 séparée. Documenté ici pour que le dépassement soit conscient et borné. |
| R8 | `get_api_override` (git_provider.py:175) a une logique provider-aware dans la base class (regarde `settings.GIT_PROVIDER`) — smell. | Très faible | Hors périmètre. Noter dans `REWRITE-BUGS.md`. |

**Budget estimé CP-1** : 5-7h IA (revu à la baisse — le split était le gros morceau). Étape 5 (rewrite tests) = le plus long (~3h).

---

## Livrables à chaque commit

Chaque commit a un message conventionnel + référence `CAB-1889`. Tests verts entre chaque. Ruff/mypy verts entre chaque. Aucun changement de comportement observable (OpenAPI spec identique). Les tests de comportement restent des specs de non-régression ; les tests implementation-detail sont réécrits explicitement.

---

## Phase 2 (séparée, hors CP-1)

**Objectif** : découper `git_service.py` (~1070 LOC après CP-1) et `github_service.py` (~980 LOC après CP-1) en modules par domaine.

**Prérequis** : CP-1 mergé. Interface `GitProvider` stable. Tous les callers router passent par l'interface.

**Esquisse du split** (ré-évaluation au moment du kick-off — à ne pas graver ici) :
```
src/services/git/
├── gitlab/  { client, rate_limit, reads, writes, branches, merge_requests, catalog, mcp }
├── github/  { structure identique }
└── schemas.py  # dataclasses déjà créées en CP-1
```
Pattern : mixins composés dans `GitLabService` / `GitHubService`. `git_service.py` et `github_service.py` deviennent des shims backcompat (re-export) — on ne casse pas les imports `iam_sync_service`, `git_sync_worker`, `main.py`, `apis.py`, `tenants.py`, `deployments.py`, `portal.py`, `health.py`, `catalog_admin.py`, `mcp_gitops.py`.

**Livrable attendu** : un `PHASE2-SPLIT-PLAN.md` dédié au moment où on ouvre la Phase 2 (pas maintenant).

**STOP CP-1 ici — attends validation avant d'exécuter les étapes 1-6.**
