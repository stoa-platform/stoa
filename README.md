# APIM Platform - UI RBAC + GitOps + Kafka

Plateforme de gestion d'APIs multi-tenant avec Control-Plane UI, GitOps et Event-Driven Architecture.

## Architecture

```
UTILISATEURS (CPI Admin, Tenant Admin, DevOps, Viewer)
                    |
                    v
    +-------------------------------+
    |    UI RBAC Control-Plane      |
    |    (React + Keycloak OIDC)    |
    +---------------+---------------+
                    |
                    v
    +-------------------------------+
    |      Control-Plane API        |
    |          (FastAPI)            |
    +---------------+---------------+
                    |
    +---------------+---------------+---------------+
    |               |               |               |
    v               v               v               v
+-------+     +---------+     +-------+     +-------+
|GitLab |     | Kafka   |     |  AWX  |     |Keycloak|
|(GitOps)|    |(Redpanda)|    |       |     | (OIDC) |
+-------+     +---------+     +-------+     +-------+
                    |               |
                    v               v
    +-------------------------------+
    |         RUNTIME LAYER         |
    |  +-------------------------+  |
    |  | webMethods Gateway DEV  |  |
    |  +-------------------------+  |
    |  | webMethods Gateway STG  |  |
    |  +-------------------------+  |
    |  |   Developer Portal      |  |
    |  +-------------------------+  |
    +-------------------------------+
```

## Composants

| Composant | Description | Technologie |
|-----------|-------------|-------------|
| UI Control-Plane | Interface RBAC pour gestion des APIs | React + TypeScript |
| Control-Plane API | Backend REST avec RBAC | FastAPI (Python) |
| Keycloak | Identity Provider (OIDC) | Keycloak |
| GitLab | Source de verite GitOps | GitLab |
| Kafka | Event streaming | Redpanda |
| AWX | Automation/Orchestration | AWX/Ansible |
| webMethods Gateway | API Gateway runtime | webMethods |
| Developer Portal | Portal consommateurs | webMethods Portal |

## Roles RBAC

| Role | Tenants | APIs | Apps | Deploy | Users |
|------|---------|------|------|--------|-------|
| CPI Admin | CRUD | CRUD | CRUD | All | All |
| Tenant Admin | Read own | CRUD | CRUD | All | Own tenant |
| DevOps | Read own | CRU | CRU | All | - |
| Viewer | Read own | Read | Read | - | - |

## Structure GitOps

```
apim-gitops/
├── tenants/
│   ├── tenant-finance/
│   │   ├── tenant.yaml
│   │   ├── apis/
│   │   │   └── payment-api/
│   │   │       ├── api.yaml
│   │   │       ├── openapi.yaml
│   │   │       └── deployments/
│   │   ├── applications/
│   │   └── users/
│   └── tenant-hr/
├── policies/
│   ├── global/
│   └── templates/
└── environments/
    ├── dev/
    └── staging/
```

## Deploiement

```bash
# Infrastructure
cd terraform/environments/dev
terraform init && terraform apply

# Helm charts
helm upgrade --install apim-platform ./charts/apim-platform -n apim-system
```

## URLs

| Service | DEV | STAGING |
|---------|-----|---------|
| Console UI | https://console.dev.apim.cab-i.com | https://console.staging.apim.cab-i.com |
| API | https://api.dev.apim.cab-i.com | https://api.staging.apim.cab-i.com |
| Gateway | https://gateway.dev.apim.cab-i.com | https://gateway.staging.apim.cab-i.com |
| Keycloak | https://keycloak.dev.apim.cab-i.com | https://keycloak.staging.apim.cab-i.com |

## Couts Estimes

- DEV: ~$127/mois
- STAGING: ~$155/mois
- **Total: ~$282/mois**
