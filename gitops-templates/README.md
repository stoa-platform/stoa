# GitOps Templates

Ce dossier contient les **templates et modèles** pour initialiser le repository GitLab `apim-gitops`.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              GitHub: apim-aws (ce repo)                     │
│                   Infrastructure + Code                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  gitops-templates/  ← Templates uniquement           │   │
│  │  control-plane-api/ ← Code source API                │   │
│  │  control-plane-ui/  ← Code source UI                 │   │
│  │  terraform/         ← Infrastructure AWS             │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ Copier templates
                              ▼
┌─────────────────────────────────────────────────────────────┐
│            GitLab: apim-gitops (Source of Truth)            │
│                    Données des tenants                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  _defaults.yaml                                      │   │
│  │  environments/{dev,staging,prod}/config.yaml         │   │
│  │  tenants/                                            │   │
│  │  ├── acme/          ← Tenant réel                    │   │
│  │  │   ├── tenant.yaml                                 │   │
│  │  │   ├── apis/                                       │   │
│  │  │   └── iam/users.yaml                              │   │
│  │  ├── client-xyz/    ← Tenant réel                    │   │
│  │  └── ...                                             │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
   Control Plane API              ArgoCD (GitOps)
   - Lit/écrit tenants            - Sync automatique
   - Webhooks GitLab              - Deploy sur K8s
```

## Contenu

### Templates (`templates/`)
- `api-template.yaml` - Modèle pour nouvelles APIs
- `application-template.yaml` - Modèle pour applications
- `tenant-template.yaml` - Modèle pour nouveaux tenants

### Configurations environnements (`environments/`)
- `dev/config.yaml` - Variables pour DEV
- `staging/config.yaml` - Variables pour STAGING
- `prod/config.yaml` - Variables pour PROD

### ArgoCD (`argocd/`)
- `appsets/` - ApplicationSets pour auto-discovery
- `projects/` - AppProjects avec RBAC

### Defaults (`_defaults.yaml`)
Variables globales par défaut

## Initialisation du repo GitLab

```bash
# 1. Créer le repo GitLab apim-gitops
# 2. Copier les fichiers de base
cp _defaults.yaml <gitlab-repo>/
cp -r environments/ <gitlab-repo>/
# 3. Les templates restent ici comme référence
```

## Le Control Plane API

Le Control Plane API n'accède **qu'à GitLab**:
- Lecture/écriture des tenants via `git_service.py`
- Réception des webhooks GitLab (push, MR)
- Aucun accès à ce repo GitHub

## Variables supportées

```yaml
# Dans les templates
backend_url: ${BACKEND_URL}              # Variable requise
timeout: ${BACKEND_TIMEOUT:30}           # Avec valeur par défaut
secret: vault:secret/path#key            # Référence Vault
```
