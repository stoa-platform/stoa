# STOA GitOps Repository

Source of Truth pour les configurations GitOps de la plateforme STOA.

## Structure

```
stoa-gitops/
├── environments/           # Configurations par environnement
│   ├── dev/
│   ├── staging/
│   └── prod/
├── tenants/               # Configurations par tenant
│   └── {tenant-id}/
│       ├── dev/
│       ├── staging/
│       └── prod/
└── argocd/                # ArgoCD ApplicationSets
    ├── projects/
    └── appsets/
```

## Workflow

1. Control Plane UI → GitLab (commit YAML)
2. ArgoCD détecte les changements
3. ArgoCD synchronise vers Kubernetes

## Liens

- **GitHub (code source)**: https://github.com/PotoMitan/stoa
- **Documentation**: Voir README dans le repo GitHub
