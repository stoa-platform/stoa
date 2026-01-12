# GitOps Templates

This folder contains **templates and models** for initializing the GitLab repository `stoa-gitops`.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│              GitHub: stoa (Development Repository)              │
│                   Application Source Code                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  control-plane-api/ <- FastAPI source code              │   │
│  │  control-plane-ui/  <- React source code                │   │
│  │  portal/            <- Developer Portal (React + Vite)  │   │
│  │  mcp-gateway/       <- MCP Gateway source code          │   │
│  │  gitops-templates/  <- Templates for GitLab             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Note: Infrastructure code is in a separate repo (stoa-infra)  │
└─────────────────────────────────────────────────────────────────┘
                             │
                             │ Initialization (one-time)
                             v
┌─────────────────────────────────────────────────────────────────┐
│         GitLab: stoa-gitops (Source of Truth - Runtime)         │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  _defaults.yaml        <- Global variables              │   │
│  │  environments/         <- Config per environment        │   │
│  │  tenants/              <- Tenant data                   │   │
│  │  webmethods/           <- webMethods Gateway GitOps     │   │
│  │  │   ├── apis/         <- API definitions               │   │
│  │  │   ├── policies/     <- Policy definitions            │   │
│  │  │   └── aliases/      <- Backend endpoints             │   │
│  │  ansible/playbooks/    <- AWX playbooks                 │   │
│  │  argocd/               <- ArgoCD configurations         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  All runtime operations go through this repo                    │
└─────────────────────────────────────────────────────────────────┘
        │              │                    │
        v              v                    v
  Control Plane   AWX Automation       ArgoCD (GitOps)
  - Webhooks      - provision-tenant   - Sync K8s
  - CRUD tenants  - register-api       - Auto-deploy
  - Events Kafka  - sync-gateway       - Rollback
```

## Separation of Concerns

| Component | Source | Role |
|-----------|--------|------|
| **GitHub (stoa)** | Source code | Development, CI/CD, Docker images |
| **GitHub (stoa-infra)** | Infrastructure | Terraform, Ansible, Helm charts |
| **GitLab (stoa-gitops)** | Runtime data | Tenants, APIs, users, AWX playbooks |
| **ArgoCD** | GitLab | K8s sync from GitLab |
| **AWX** | GitLab | Execute playbooks from GitLab |
| **Control Plane API** | GitLab | Read/write tenants in GitLab |

## Contents

### Structure

```
gitops-templates/
├── README.md                    # This file
├── _defaults.yaml               # Global variables template
├── templates/                   # Resource templates
│   ├── api-template.yaml
│   ├── application-template.yaml
│   └── tenant-template.yaml
├── environments/                # Environment configs
│   ├── dev/config.yaml
│   ├── staging/config.yaml
│   └── prod/config.yaml
├── argocd/                      # ArgoCD configurations
│   ├── chart/                   # Helm chart for ApplicationSets
│   ├── appsets/                 # Legacy ApplicationSets
│   └── projects/                # AppProjects
└── webmethods/                  # webMethods Gateway GitOps
    ├── README.md                # webMethods documentation
    ├── schema/api-schema.json   # JSON Schema for validation
    ├── apis/                    # API definition templates
    ├── policies/                # Policy templates
    ├── aliases/                 # Backend endpoint templates
    └── scripts/                 # Validation scripts
```

### Centralized Configuration (`_defaults.yaml`)

Central file containing all global variables:

```yaml
infrastructure:
  GITLAB_URL: "https://gitlab.com"
  GITLAB_PROJECT_PATH: "${YOUR_ORG}/stoa-gitops"
  K8S_NAMESPACE_PREFIX: "stoa"
  BASE_DOMAIN: "${YOUR_DOMAIN}"

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
- `api-template.yaml` - Template for new APIs with `${VAR:default}`
- `application-template.yaml` - Template for OAuth2 applications
- `tenant-template.yaml` - Template for new tenants with RBAC

### Environment Configurations (`environments/`)
- `dev/config.yaml` - DEV variables (relaxed, debug)
- `staging/config.yaml` - STAGING variables (moderate)
- `prod/config.yaml` - PROD variables (strict, alerting)

### webMethods GitOps (`webmethods/`)

Templates for declarative webMethods Gateway configuration:
- **apis/**: API definition templates
- **policies/**: JWT validation, rate limiting, etc.
- **aliases/**: Backend endpoints per environment
- **scripts/**: CI validation script

See [webmethods/README.md](webmethods/README.md) for details.

### ArgoCD Helm Chart (`argocd/chart/`)

Helm chart to deploy ApplicationSets:

```bash
# Installation
helm install argocd-appsets ./argocd/chart -n argocd

# With custom values
helm install argocd-appsets ./argocd/chart -n argocd \
  --set gitlab.repoUrl=https://gitlab.com/myorg/stoa-gitops.git \
  --set domain.base=mycompany.com
```

**Chart files:**
- `chart/values.yaml` - Centralized configuration
- `chart/templates/appset-tenant-apis.yaml` - ApplicationSet for APIs
- `chart/templates/appset-environments.yaml` - ApplicationSet for envs
- `chart/templates/project-platform.yaml` - AppProject platform

### ArgoCD Legacy (`argocd/appsets/`, `argocd/projects/`)

**DEPRECATED** - Kept for reference only.
Use the Helm chart `argocd/chart/` instead.

## GitLab Repository Initialization

```bash
# Automated script
./scripts/init-gitlab-gitops.sh

# Or manually:
cp _defaults.yaml <gitlab-repo>/
cp -r environments/ <gitlab-repo>/
cp -r webmethods/ <gitlab-repo>/
mkdir -p <gitlab-repo>/tenants
```

## Supported Variables

### Syntax

```yaml
# Required variable (error if undefined)
backend_url: ${BACKEND_URL}

# Variable with default value
timeout: ${BACKEND_TIMEOUT:30}

# Vault reference (resolved at runtime)
secret: vault:secret/data/path#key

# Nested variable
url: "https://gateway.${BASE_DOMAIN:example.com}"
```

### Resolution Order

1. `_defaults.yaml` - Global variables
2. `environments/{env}/config.yaml` - Environment override
3. `tenants/{tenant}/environments/{env}.yaml` - Tenant override
4. Inline values `${VAR:default}` - Fallback

## Control Plane API

The Control Plane API only accesses **GitLab**:
- Read/write tenants via `git_service.py`
- Receive GitLab webhooks (push, MR)
- Resolve variables via `variable_resolver.py`
- No access to this GitHub repo
