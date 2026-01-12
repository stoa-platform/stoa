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
├── mcp-gateway/               # MCP Gateway configurations
├── stoa-portal/               # Developer Portal configurations
├── ansible/                   # AWX playbooks
│   └── playbooks/
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
3. AWX executes reconcile playbook
4. webMethods Gateway updated

## Components

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
