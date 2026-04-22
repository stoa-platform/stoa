# REWRITE-PLAN — Git Provider config (CP-2) — v2 (amended after review)

**Scope** : `src/config.py` (section Git), tous les consommateurs qui lisent la config Git provider, `.env.example`, `k8s/configmap.yaml`, tests liés.

**Métriques binaires de succès** :
1. **Un seul point d'entrée** côté consommateurs : `settings.git.*` (3 modèles internes — `GitHubConfig`, `GitLabConfig`, `GitProviderConfig` — agrégés via le champ `settings.git`).
2. Au startup, `ENVIRONMENT=production` + config incohérente → `Settings()` lève `pydantic.ValidationError`. App refuse de démarrer.
3. `grep -rn 'settings\.\(GIT_PROVIDER\|GITHUB_\|GITLAB_\)' src/` → **zéro occurrence** en dehors de `src/config.py` (toutes passent par `settings.git.*`).
4. `.env.example` expose `GIT_PROVIDER`, `GITHUB_TOKEN`, `GITHUB_ORG`, `GITHUB_CATALOG_REPO`, `GITHUB_WEBHOOK_SECRET`, `GITLAB_URL`, `GITLAB_TOKEN`, `GITLAB_PROJECT_ID`, `GITLAB_WEBHOOK_SECRET`.

**Hors scope** (flaggés risques, ne seront PAS corrigés ici) :
- Le singleton `git_service = GitLabService()` dans `src/services/git_service.py:1111` (voir Risque R-1).
- Aucun changement de comportement observable API.
- Aucun rename de variable d'env (backward compat déploiement K8s garantie).
- Suppression des champs plats actifs de `Settings` (ils restent comme ingestion interne, `exclude=True`). Si on veut un jour les vraiment supprimer, ça passera par un `settings_customise_sources` custom — ticket ultérieur, pas nécessaire pour atteindre les 4 métriques.

---

## A. Matrice actuelle

### A.1 Variables GitHub

| Var env (config.py:line) | Default | Lue par (hors config.py) | Statut |
|---|---|---|---|
| `GIT_PROVIDER` (:105) | `"github"` | `git_provider.py:232` (fallback `"gitlab"`), `:389`, `:403`; `routers/mcp_gitops.py:300`; `workers/git_sync_worker.py:84` (commentaire seul) | **CONTRADICTOIRE** — 3 defaults diff (voir A.3) |
| `GITHUB_TOKEN` (:106) | `""` | `github_service.py:115,137` | OK, mais empty accepté silencieusement |
| `GITHUB_ORG` (:107) | `"stoa-platform"` | `github_service.py:576`, `git_provider.py:234`, `routers/mcp_gitops.py:301` | OK |
| `GITHUB_CATALOG_REPO` (:108) | `"stoa-catalog"` | `github_service.py:576`, `git_provider.py:234`, `routers/mcp_gitops.py:301` | OK |
| `GITHUB_GITOPS_REPO` (:109) | `"stoa-gitops"` | **aucun runtime caller** (seulement `tests/test_git_provider.py:115` qui asserte le default) | **DEAD** |
| `GITHUB_WEBHOOK_SECRET` (:110) | `""` | `routers/webhooks.py:252` | OK, mais empty accepté silencieusement |

### A.2 Variables GitLab

| Var env (config.py:line) | Default | Lue par (hors config.py) | Statut |
|---|---|---|---|
| `GITLAB_URL` (:79) | `"https://gitlab.com"` | `git_service.py:106` | OK |
| `GITLAB_TOKEN` (:80) | `""` | `git_service.py:106,148` | OK, empty accepté silencieusement |
| `GITLAB_WEBHOOK_SECRET` (:81) | `""` | `routers/webhooks.py:172` (via `getattr` redondant) | OK, `getattr` à supprimer |
| `GITLAB_DEFAULT_BRANCH` (:82) | `"main"` | **aucun caller** | **DEAD** |
| `GITLAB_PROJECT_ID` (:88) | `""` | `git_service.py:110`, `git_provider.py:236`, `routers/mcp_gitops.py:303` | OK |
| `GITLAB_CATALOG_PROJECT_PATH` (:89) | `"cab6961310/stoa-catalog"` | **aucun caller** (property alias `GITLAB_PROJECT_PATH` non plus) | **DEAD** |
| `GITLAB_GITOPS_PROJECT_ID` (:92) | `"77260481"` | **aucun caller** | **DEAD** |
| `GITLAB_GITOPS_PROJECT_PATH` (:93) | `"cab6961310/stoa-gitops"` | **aucun caller** | **DEAD** |
| `GITLAB_CATALOG_PROJECT_ID` (:97, property alias) | alias sur `GITLAB_PROJECT_ID` | **aucun caller** | **DEAD** |
| `GITLAB_PROJECT_PATH` (:101, property alias) | alias sur `GITLAB_CATALOG_PROJECT_PATH` | **aucun caller** | **DEAD** |
| `LOG_DEBUG_GITLAB_API` (:315) | `False` | **aucun caller** | **DEAD** (flag logging orphelin) |

**Bilan** : 7 variables dead + 1 flag log dead. À supprimer en C.1 (pas de backward compat à préserver — aucun caller, aucun ConfigMap prod, aucune mention Helm).

### A.3 Chemins de lecture dispersés

| Fichier:ligne | Pattern | Nature |
|---|---|---|
| `config.py:105-110` | Déclaration `Settings` | source de truth déclarée |
| `git_provider.py:232-236` | `getattr(settings, "GIT_PROVIDER", "gitlab")` + résolution `project_id` provider-aware | **leak** — base ABC lit `GIT_PROVIDER` directement (BUG-04 déjà tracé dans `REWRITE-BUGS.md`) |
| `git_provider.py:389-403` | `git_provider_factory()` — `settings.GIT_PROVIDER.lower()` | OK (point d'entrée légitime du factory, à migrer vers `settings.git.provider`) |
| `routers/mcp_gitops.py:300-303` | `if settings.GIT_PROVIDER.lower() == "github"` → calcule `project_id` | **leak** — duplique la logique du factory dans un router |
| `routers/webhooks.py:172` | `getattr(settings, "GITLAB_WEBHOOK_SECRET", "")` | redondant (champ déjà déclaré avec `""` default) |
| `conftest.py:40` | `os.environ.setdefault("GIT_PROVIDER", "gitlab")` | OK pour les tests, mais default **différent** de `config.py` |
| `stoa-infra/charts/control-plane-api/values.yaml:11` | `GIT_PROVIDER: gitlab` | prod tourne effectivement en GitLab (!= default code) |
| `k8s/configmap.yaml:30` | `GIT_PROVIDER: "github"` | manifest K8s du repo — **non utilisé en prod** (Helm override) |
| `.env.example:81-83` | mentionne uniquement `GITLAB_*`, pas de `GIT_PROVIDER` ni de `GITHUB_*` | **incomplet** |

### A.4 Startup / lifespan

- `main.py:196` appelle `await git_service.connect()` avec `git_service = GitLabService()` importé du module `services/git_service.py:1111`.
- Quel que soit `GIT_PROVIDER`, le lifespan **tente toujours** une connexion GitLab. Échec → `warning` log, app démarre quand même.
- Aucun endpoint `/ready` ne valide la cohérence de la config Git provider.
- `/health` ne check pas le provider (sauf l'endpoint dédié `routers/mcp_gitops.py:290` "health git provider", protégé `cpi-admin`).

**Conclusion** : l'app démarre avec n'importe quelle combinaison d'env vars. Le premier appel API catalogue provoque l'erreur à distance de la cause.

---

## B. Config cible

### B.1 Architecture — ingestion plate + hydration (amendée après review)

**Décision design** : Pydantic Settings ne lit pas les env vars via les aliases déclarés sur un `BaseModel` imbriqué dans `BaseSettings` sans un `env_nested_delimiter` explicite. Une variable d'env `GIT_PROVIDER=gitlab` ne populera pas `settings.git.provider` même avec `alias="GIT_PROVIDER"` sur le sous-modèle. (Reproduit sur Pydantic 2.13 / pydantic-settings 2.12.)

Deux voies propres, la première retenue :

**Voie 1 (retenue) — Ingestion plate interne + hydration dans validator**

- Garder dans `Settings` les 9 champs plats **actifs** (`GIT_PROVIDER`, `GITHUB_TOKEN`, `GITHUB_ORG`, `GITHUB_CATALOG_REPO`, `GITHUB_WEBHOOK_SECRET`, `GITLAB_URL`, `GITLAB_TOKEN`, `GITLAB_PROJECT_ID`, `GITLAB_WEBHOOK_SECRET`) avec `exclude=True` (hors schéma de serialization).
- Ajouter `git: GitProviderConfig` — agrégat de 3 sous-modèles (`GitHubConfig` + `GitLabConfig` + `provider`).
- Un `model_validator(mode="after")` hydrate `settings.git` depuis les champs plats, **puis** exécute la validation cohérence provider.
- Les consommateurs lisent **uniquement** `settings.git.*`. Les champs plats sont privés du module `config.py`.

**Voie 2 (écartée) — `settings_customise_sources` custom**

- Remappe les env vars plates vers un payload JSON `git={...}` via une source custom.
- Pydantic le supporte, mais c'est plus de code, plus de surface de test, et pas nécessaire pour atteindre la métrique 3 (qui se valide au niveau **consommateur**, pas au niveau déclaration `Settings`).
- Garder en réserve si on décide un jour de vraiment supprimer les champs plats.

**Fausse sortie écartée** — faire de `GitProviderConfig` un `BaseSettings` imbriqué : dans les tests, il lit `os.environ` mais pas le `.env` du parent. Pas déterministe.

### B.2 Code cible (extrait)

```python
# src/config.py (extrait cible — après C.1)

from typing import Literal

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class GitHubConfig(BaseModel):
    """GitHub provider config — hydrated from flat env vars by Settings validator."""
    token: SecretStr = Field(default=SecretStr(""))
    org: str = "stoa-platform"
    catalog_repo: str = "stoa-catalog"
    webhook_secret: SecretStr = Field(default=SecretStr(""))

    @property
    def catalog_project_id(self) -> str:
        """Provider-agnostic project identifier: 'org/repo'."""
        return f"{self.org}/{self.catalog_repo}"


class GitLabConfig(BaseModel):
    """GitLab provider config — hydrated from flat env vars by Settings validator."""
    url: str = "https://gitlab.com"
    token: SecretStr = Field(default=SecretStr(""))
    project_id: str = ""
    webhook_secret: SecretStr = Field(default=SecretStr(""))

    @property
    def catalog_project_id(self) -> str:
        return self.project_id


class GitProviderConfig(BaseModel):
    """Single entry point for Git provider config. Consumers use settings.git.*."""
    provider: Literal["github", "gitlab"] = "github"
    github: GitHubConfig = Field(default_factory=GitHubConfig)
    gitlab: GitLabConfig = Field(default_factory=GitLabConfig)

    @property
    def active_catalog_project_id(self) -> str:
        """Provider-agnostic 'project_id' for the currently selected provider."""
        if self.provider == "github":
            return self.github.catalog_project_id
        return self.gitlab.catalog_project_id


class Settings(BaseSettings):
    # ... other fields unchanged ...

    # ── Git Provider — legacy flat ingress (DO NOT READ from consumers) ────
    # These 9 fields exist only so Pydantic Settings can hydrate them from
    # env vars, .env and K8s ConfigMap. They are `exclude=True` so they
    # never appear in Settings().model_dump().
    # Consumers must read `settings.git.*` instead. A grep gate in CI
    # enforces this (see C.5).
    GIT_PROVIDER: Literal["github", "gitlab"] = Field(default="github", exclude=True)
    GITHUB_TOKEN: str = Field(default="", exclude=True)
    GITHUB_ORG: str = Field(default="stoa-platform", exclude=True)
    GITHUB_CATALOG_REPO: str = Field(default="stoa-catalog", exclude=True)
    GITHUB_WEBHOOK_SECRET: str = Field(default="", exclude=True)
    GITLAB_URL: str = Field(default="https://gitlab.com", exclude=True)
    GITLAB_TOKEN: str = Field(default="", exclude=True)
    GITLAB_PROJECT_ID: str = Field(default="", exclude=True)
    GITLAB_WEBHOOK_SECRET: str = Field(default="", exclude=True)

    # ── Git Provider — single source of truth for consumers ────────────────
    git: GitProviderConfig = Field(default_factory=GitProviderConfig)

    @model_validator(mode="after")
    def _hydrate_and_validate_git(self) -> "Settings":
        """CAB-1889 CP-2: hydrate settings.git from legacy flat env vars,
        then (C.3) fail fast in prod if the selected provider is misconfigured.
        """
        # Step 1 — hydration (always, wrapping SecretStr at the boundary).
        self.git = GitProviderConfig(
            provider=self.GIT_PROVIDER,
            github=GitHubConfig(
                token=SecretStr(self.GITHUB_TOKEN),
                org=self.GITHUB_ORG,
                catalog_repo=self.GITHUB_CATALOG_REPO,
                webhook_secret=SecretStr(self.GITHUB_WEBHOOK_SECRET),
            ),
            gitlab=GitLabConfig(
                url=self.GITLAB_URL,
                token=SecretStr(self.GITLAB_TOKEN),
                project_id=self.GITLAB_PROJECT_ID,
                webhook_secret=SecretStr(self.GITLAB_WEBHOOK_SECRET),
            ),
        )

        # Step 2 — validation (gated; flipped in C.3).
        if not _VALIDATE_GIT_CONFIG:
            return self

        git = self.git
        offender_msgs: list[str] = []

        if git.provider == "github":
            if not git.github.token.get_secret_value():
                offender_msgs.append("GIT_PROVIDER=github but GITHUB_TOKEN is empty")
            if git.gitlab.token.get_secret_value():
                _logger.warning(
                    "GIT_PROVIDER=github but GITLAB_TOKEN is also set. "
                    "Inactive provider credentials should be removed."
                )
        else:  # gitlab
            if not git.gitlab.token.get_secret_value():
                offender_msgs.append("GIT_PROVIDER=gitlab but GITLAB_TOKEN is empty")
            if not git.gitlab.project_id:
                offender_msgs.append("GIT_PROVIDER=gitlab but GITLAB_PROJECT_ID is empty")
            if git.github.token.get_secret_value():
                _logger.warning(
                    "GIT_PROVIDER=gitlab but GITHUB_TOKEN is also set. "
                    "Inactive provider credentials should be removed."
                )

        if not offender_msgs:
            return self

        joined = "; ".join(offender_msgs)
        if self.ENVIRONMENT == "production":
            raise ValueError(
                f"Refusing to boot: Git provider config is incoherent ({joined}). "
                f"Set the required env vars in your Helm override."
            )

        _logger.warning(
            "Git provider config incomplete (ENVIRONMENT=%s): %s. "
            "Catalog operations will fail at request time. Fix before prod.",
            self.ENVIRONMENT,
            joined,
        )
        return self
```

**Note test contract** : `raise ValueError(...)` à l'intérieur d'un `model_validator` est encapsulé par Pydantic en `pydantic.ValidationError` (qui hérite de `ValueError`). Les tests de C.3 doivent cibler `pytest.raises(ValidationError)` pour être explicites.

### B.3 Utilisation côté consommateurs

Avant :
```python
# routers/mcp_gitops.py
if settings.GIT_PROVIDER.lower() == "github":
    project_id = f"{settings.GITHUB_ORG}/{settings.GITHUB_CATALOG_REPO}"
else:
    project_id = settings.GITLAB_PROJECT_ID
```

Après :
```python
project_id = settings.git.active_catalog_project_id
```

Avant :
```python
# services/github_service.py
auth = Auth.Token(settings.GITHUB_TOKEN)
```

Après :
```python
auth = Auth.Token(settings.git.github.token.get_secret_value())
```

Avant :
```python
# services/git_service.py
self._gl = gitlab.Gitlab(settings.GITLAB_URL, private_token=settings.GITLAB_TOKEN)
self._project = self._gl.projects.get(settings.GITLAB_PROJECT_ID)
```

Après :
```python
gl_cfg = settings.git.gitlab
self._gl = gitlab.Gitlab(gl_cfg.url, private_token=gl_cfg.token.get_secret_value())
self._project = self._gl.projects.get(gl_cfg.project_id)
```

---

## C. Plan de migration (ordre amendé)

Ordre bottom-up. **Chaque commit consommateur embarque sa MAJ de tests** — pas de commit qui casse la suite.

### C.1 — Introduire `GitProviderConfig` + hydration en shadow
- Ajouter les 3 classes `GitHubConfig` / `GitLabConfig` / `GitProviderConfig` dans `config.py`.
- Ajouter le champ `git: GitProviderConfig = Field(default_factory=GitProviderConfig)` dans `Settings`.
- Ajouter `exclude=True` aux 9 champs plats actifs.
- Retirer les 7 champs dead + 1 flag log dead + 2 `@property` alias morts.
- Ajouter le `model_validator` avec **hydration active** mais **validation désactivée** via flag module-level `_VALIDATE_GIT_CONFIG = False` (C.3 le flippera).
- Tests affectés dans le même commit : `tests/test_git_provider.py:115` (retrait assertion `GITHUB_GITOPS_REPO`).
- `pytest` vert — aucune régression.

### C.2 — Migrer les consommateurs, un fichier par commit, tests inclus

| # | Fichier code | Tests à migrer dans le même commit |
|---|---|---|
| 1 | `routers/webhooks.py` (retire `getattr` redondant + migre les deux webhook secrets) | `tests/test_webhooks.py`, `tests/test_webhooks_router.py` |
| 2 | `routers/mcp_gitops.py:300-303` → `settings.git.active_catalog_project_id` | couverture indirecte via integration |
| 3 | `services/git_provider.py:232-236` (`get_api_override`) → `settings.git.active_catalog_project_id`. Ferme BUG-04. | `tests/test_git_provider.py` si couvre `get_api_override` |
| 4 | `services/git_provider.py:389,403` (factory) → `settings.git.provider`. Suppression du `.lower()` (`Literal` garantit la casse). | `tests/test_dual_provider_smoke.py`, `tests/test_git_provider.py` (patches `mock_settings.GIT_PROVIDER` → patcher `mock_settings.git`) |
| 5 | `services/github_service.py:115,137,576` → `settings.git.github.*` | `tests/test_github_service_catalog_parity.py`, `tests/test_regression_cab_1889_github_*` |
| 6 | `services/git_service.py:106,110,148` → `settings.git.gitlab.*` | `tests/test_git_service.py` |
| 7 | `workers/git_sync_worker.py:84` — commentaire seul, rien runtime | aucun |

`conftest.py:40` — mis à jour en **C.3**.

### C.3 — Activer la validation startup
- Flip `_VALIDATE_GIT_CONFIG = True`.
- Mettre à jour `conftest.py:40` pour set `GITLAB_TOKEN=test-token` + `GITLAB_PROJECT_ID=1` (évite le spam de warnings pendant la suite).
- Ajouter `tests/test_config_git_provider_validation.py` couvrant :
  - `ENVIRONMENT=production` + combos manquants → `ValidationError`
  - `ENVIRONMENT=dev` + combos manquants → warning via `caplog`
  - Tokens des deux providers set → warning sur l'inactif
  - `GIT_PROVIDER=invalid` → `ValidationError` (via `Literal`)
  - Défaut code (`GIT_PROVIDER=github`) + `GITHUB_TOKEN=""` + prod → `ValidationError` (couvre R-3)

### C.4 — Artefacts déploiement
- `.env.example` : section `# ── Git Provider ──` explicite (9 vars).
- `k8s/configmap.yaml` : retire les vars dead commentées + `GITHUB_GITOPS_REPO` + `GITLAB_DEFAULT_BRANCH`.
- `stoa-infra/charts/control-plane-api/values.yaml` : **pas modifié** (prod reste `GIT_PROVIDER=gitlab`, flip vers github = CAB-1890).

### C.5 — Grep gate CI
`scripts/check_git_config_access.sh` + step dans `.github/workflows/lint.yml`.

---

## D. Startup validation

`model_validator(mode="after")` sur `Settings` → exécuté dès l'instanciation `settings = Settings()` en tête de `config.py` (première ligne importée par `main.py:19`, avant DB/cache/Kafka).

- `ENVIRONMENT=production` + config incohérente → `ValueError` encapsulé en `ValidationError` Pydantic → crash process. K8s relance, readiness KO, alerte.
- `ENVIRONMENT=dev|staging` → `_logger.warning(...)`, app démarre.

Aligné sur `_gate_sensitive_debug_flags_in_prod` (config.py:420-445).

Webhooks non validés au startup (optionnels) — `webhooks.py:75,85` refuse déjà au runtime si secret absent.

---

## E. Chemins morts à supprimer (C.1)

| Var | Raison |
|---|---|
| `GITHUB_GITOPS_REPO` | Jamais câblée. Test `test_git_provider.py:115` retiré aussi. |
| `GITLAB_DEFAULT_BRANCH` | Constante `"main"` hard-codée ailleurs. |
| `GITLAB_CATALOG_PROJECT_PATH` | Non lu. |
| `GITLAB_GITOPS_PROJECT_ID` / `_PATH` | Non lus. |
| `GITLAB_CATALOG_PROJECT_ID` / `GITLAB_PROJECT_PATH` (properties) | Non lues. |
| `LOG_DEBUG_GITLAB_API` | Jamais référencé. |

Aucun ConfigMap prod ne les utilise non-commentées. `k8s/configmap.yaml` les liste en commentaires → nettoyage en C.4.

---

## F. Risques identifiés

### R-1 — Singleton `git_service = GitLabService()` ignore `GIT_PROVIDER`
`src/services/git_service.py:1111`. `main.py:196`, `iam_sync_service.py`, `deployment_orchestration_service.py`, `mcp_sync_service.py` utilisent ce singleton. La validation de CP-2 vérifie les creds du provider **déclaré** — sans résoudre le singleton. Hors scope CP-2, à reprendre en CP-3 (remplacer par `get_git_provider()` via `Depends` ou `app.state.git_provider`). Mitigation CP-2 : warning visible si les creds de l'inactif sont set.

### R-2 — Tests qui patchent `mock_settings.GITLAB_*` / `GITHUB_*`
Les attributs plats existent toujours (`exclude=True` exclut du dump, pas du getattr). Les patches ne crashent pas mais le code consommateur lit maintenant `settings.git.*` qui a été hydraté **une seule fois** à l'init. Chaque commit C.2 patche `mock_settings.git = GitProviderConfig(...)` ou équivalent.

### R-3 — `conftest.py:40` default `gitlab` vs code default `github`
Angle mort dans les tests. Mitigation : `test_default_git_provider_is_github_and_requires_github_token` en C.3.

### R-4 — `routers/webhooks.py` utilise `getattr` redondant
Supprimé en C.2 commit #1.

### R-5 — Stoa-infra `GIT_PROVIDER: gitlab` en prod — vérifier secret avant C.3
`kubectl get secret gitlab-secrets -n stoa-system -o yaml` pour confirmer que `GITLAB_TOKEN` + `GITLAB_PROJECT_ID` sont présents. Si `GITLAB_PROJECT_ID` manque, ajouter au secret/ConfigMap **avant** merge C.3, sinon la validation casse le rollout.

### R-6 — Double source Helm `charts/stoa-platform/` vs `stoa-infra/`
Source ArgoCD live = `stoa-infra/charts/control-plane-api/values.yaml`. Monorepo `k8s/configmap.yaml` = legacy non déployé. Cleanup C.4 uniquement cosmétique.

### R-7 — `exclude=True` n'empêche pas le getattr
Un caller qui continue `settings.GITHUB_TOKEN` aura une valeur vivante (hydratée depuis env). La grep gate de C.5 est **obligatoire** pour empêcher la régression consommateur.

---

## Livrables Phase 2 (après validation de ce plan)

- **Commit 1 (C.1)** : introduce `GitProviderConfig` shadow + hydration + retire les 7 vars dead + 1 flag log dead + 2 property alias. Validator présent mais validation désactivée (`_VALIDATE_GIT_CONFIG = False`).
- **Commits 2-8 (C.2)** : migrer chaque consommateur + ses tests (7 commits).
- **Commit 9 (C.3)** : flip `_VALIDATE_GIT_CONFIG = True`, mise à jour `conftest.py`, nouveau `tests/test_config_git_provider_validation.py`.
- **Commit 10 (C.4)** : `.env.example` + `k8s/configmap.yaml` cleanup + `REWRITE-BUGS.md` update (BUG-04 closed par C.2 commit #3).
- **Commit 11 (C.5)** : grep gate CI.

---

**Phase 2 en cours — ce plan est la v2 validée par le reviewer.**
