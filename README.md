# STOA GitOps Repository

Source of Truth for STOA platform GitOps configurations.

## Structure

```
stoa-gitops/
├── environments/              # Environment configurations
│   ├── dev/
│   ├── staging/
│   └── prod/
├── tenants/                   # Tenant configurations
│   └── {tenant-id}/
│       ├── dev/
│       ├── staging/
│       └── prod/
├── argocd/                    # ArgoCD ApplicationSets
│   ├── projects/
│   └── appsets/
├── webmethods/                # webMethods Gateway GitOps
│   ├── apis/                  # API definitions
│   ├── policies/              # Policy definitions
│   ├── aliases/               # Backend endpoints per environment
│   └── schema/                # JSON Schema for validation
├── ansible/                   # AWX playbooks
│   └── reconcile-webmethods/  # webMethods reconciliation
│       ├── reconcile-webmethods.yml
│       ├── awx-job-template.yml
│       └── tasks/
├── mcp-gateway/               # MCP Gateway configurations
├── stoa-portal/               # Developer Portal configurations
└── scripts/                   # CI/CD scripts
    └── validate-webmethods.py
```

## Workflow

### Standard GitOps Flow
1. Control Plane UI -> GitLab (commit YAML)
2. ArgoCD detects changes
3. ArgoCD syncs to Kubernetes

### webMethods Reconciliation Flow
1. Git Push (PR merge)
2. ArgoCD PostSync hook
3. AWX executes `ansible/reconcile-webmethods/reconcile-webmethods.yml`
4. webMethods Gateway updated

## Components

### Ansible Playbooks (`ansible/`)

#### reconcile-webmethods
Automatically synchronizes APIs from Git to webMethods Gateway:
- Load APIs/policies/aliases from `webmethods/`
- Fetch current state from Gateway
- Compute diff and apply changes (create/update/delete)
- Send notifications

See [ansible/reconcile-webmethods/README.md](ansible/reconcile-webmethods/README.md) for details.

**Usage:**
```bash
# Local execution
ansible-playbook ansible/reconcile-webmethods/reconcile-webmethods.yml -e "env=dev"

# Via AWX
# Import job template from awx-job-template.yml
```

### webMethods GitOps (`webmethods/`)
Declarative API definitions for webMethods Gateway:
- **apis/**: REST/SOAP/GraphQL API definitions
- **policies/**: Rate limiting, JWT validation, etc.
- **aliases/**: Backend endpoints per environment (dev/staging/prod)

See [webmethods/README.md](webmethods/README.md) for details.

### Tenants (`tenants/`)
Multi-tenant configurations managed by Control Plane:
- Tenant metadata
- API subscriptions
- User/application assignments

### ArgoCD (`argocd/`)
ArgoCD ApplicationSets for GitOps deployment:
- **projects/**: AppProjects for RBAC
- **appsets/**: ApplicationSets for dynamic app generation

## CI/CD Validation

```yaml
validate-webmethods:
  stage: validate
  script:
    - pip install jsonschema pyyaml
    - python scripts/validate-webmethods.py --dir webmethods
  rules:
    - changes:
        - webmethods/**/*
```

## Links

- **GitHub (source code)**: https://github.com/PotoMitan/stoa
- **GitHub (public templates)**: https://github.com/stoa-platform/stoa
- **Documentation**: See README in GitHub repo
