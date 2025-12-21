# GitOps Templates

Ce dossier contient les **templates et modèles** pour initialiser le repository GitLab `apim-gitops`.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│              GitHub: apim-aws (Development Repository)          │
│                   Infrastructure + Code Source                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  control-plane-api/ ← Code source FastAPI               │   │
│  │  control-plane-ui/  ← Code source React                 │   │
│  │  ansible/           ← Playbooks Ansible (référence)     │   │
│  │  terraform/         ← Infrastructure AWS                │   │
│  │  gitops-templates/  ← Templates pour GitLab             │   │
│  │  charts/            ← Helm charts                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ⚠️ Ce repo sert UNIQUEMENT au développement et déploiement    │
│     initial. Une fois déployé, tout fonctionne via GitLab.     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Initialisation (une seule fois)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│         GitLab: apim-gitops (Source of Truth - Runtime)         │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  ansible/playbooks/  ← Playbooks exécutés par AWX       │   │
│  │  _defaults.yaml      ← Variables globales               │   │
│  │  environments/       ← Config par environnement         │   │
│  │  tenants/            ← Données des tenants              │   │
│  │  ├── apim/           ← Tenant admin (platform)          │   │
│  │  │   ├── tenant.yaml                                    │   │
│  │  │   ├── apis/control-plane/                            │   │
│  │  │   └── iam/users.yaml (APIMAdmin)                     │   │
│  │  ├── acme/           ← Tenant client                    │   │
│  │  └── ...                                                │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ✅ Toutes les opérations runtime passent par ce repo          │
└─────────────────────────────────────────────────────────────────┘
         │              │                    │
         ▼              ▼                    ▼
   Control Plane   AWX Automation       ArgoCD (GitOps)
   - Webhooks      - provision-tenant   - Sync K8s
   - CRUD tenants  - register-api       - Auto-deploy
   - Events Kafka  - sync-gateway       - Rollback
```

## Séparation des responsabilités

| Composant | Source | Rôle |
|-----------|--------|------|
| **GitHub (apim-aws)** | Code source | Développement, CI/CD, images Docker |
| **GitLab (apim-gitops)** | Données runtime | Tenants, APIs, users, playbooks AWX |
| **ArgoCD** | GitLab | Sync K8s depuis GitLab |
| **AWX** | GitLab | Exécute playbooks depuis GitLab |
| **Control Plane API** | GitLab | Lit/écrit tenants dans GitLab |

## Contenu

### Configuration centralisée (`_defaults.yaml`)

Fichier central contenant toutes les variables globales:

```yaml
infrastructure:
  GITLAB_URL: "https://gitlab.com"
  GITLAB_PROJECT_PATH: "PotoMitan1/apim-gitops"
  GITLAB_REPO_URL: "https://gitlab.com/PotoMitan1/apim-gitops.git"
  K8S_CLUSTER_URL: "https://kubernetes.default.svc"
  K8S_NAMESPACE_PREFIX: "apim"
  BASE_DOMAIN: "apim.cab-i.com"

services:
  GATEWAY_URL: "https://gateway.${BASE_DOMAIN}"
  KEYCLOAK_URL: "https://auth.${BASE_DOMAIN}"
  # ...

variables:
  BACKEND_TIMEOUT: "30"
  RATE_LIMIT_REQUESTS: "100"
  # ...
```

### Templates (`templates/`)
- `api-template.yaml` - Modèle pour nouvelles APIs avec `${VAR:default}`
- `application-template.yaml` - Modèle pour applications OAuth2
- `tenant-template.yaml` - Modèle pour nouveaux tenants avec RBAC

### Configurations environnements (`environments/`)
- `dev/config.yaml` - Variables DEV (relaxées, debug)
- `staging/config.yaml` - Variables STAGING (modérées)
- `prod/config.yaml` - Variables PROD (strictes, alerting)

### ArgoCD Helm Chart (`argocd/chart/`)

Chart Helm pour déployer les ApplicationSets:

```bash
# Installation
helm install argocd-appsets ./argocd/chart -n argocd

# Avec valeurs personnalisées
helm install argocd-appsets ./argocd/chart -n argocd \
  --set gitlab.repoUrl=https://gitlab.com/myorg/apim-gitops.git \
  --set domain.base=mycompany.com
```

**Fichiers du chart:**
- `chart/values.yaml` - Configuration centralisée
- `chart/templates/appset-tenant-apis.yaml` - ApplicationSet pour APIs
- `chart/templates/appset-environments.yaml` - ApplicationSet pour envs
- `chart/templates/project-platform.yaml` - AppProject platform

### ArgoCD Legacy (`argocd/appsets/`, `argocd/projects/`)

⚠️ **DEPRECATED** - Conservés pour référence uniquement.
Utilisez le chart Helm `argocd/chart/` à la place.

## Initialisation du repo GitLab

```bash
# Script automatisé
./scripts/init-gitlab-gitops.sh

# Ou manuellement:
cp _defaults.yaml <gitlab-repo>/
cp -r environments/ <gitlab-repo>/
mkdir -p <gitlab-repo>/tenants
```

## Variables supportées

### Syntaxe

```yaml
# Variable requise (erreur si non définie)
backend_url: ${BACKEND_URL}

# Variable avec valeur par défaut
timeout: ${BACKEND_TIMEOUT:30}

# Référence Vault (résolu au runtime)
secret: vault:secret/data/path#key

# Variable imbriquée
url: "https://gateway.${BASE_DOMAIN:apim.cab-i.com}"
```

### Ordre de résolution

1. `_defaults.yaml` - Variables globales
2. `environments/{env}/config.yaml` - Override par environnement
3. `tenants/{tenant}/environments/{env}.yaml` - Override par tenant
4. Valeurs inline `${VAR:default}` - Fallback

## Le Control Plane API

Le Control Plane API n'accède **qu'à GitLab**:
- Lecture/écriture des tenants via `git_service.py`
- Réception des webhooks GitLab (push, MR)
- Résolution des variables via `variable_resolver.py`
- Aucun accès à ce repo GitHub
