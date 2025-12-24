# APIM Platform - UI RBAC + GitOps + Kafka

Plateforme de gestion d'APIs multi-tenant avec Control-Plane UI, GitOps et Event-Driven Architecture.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CLIENTS                                      │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │   UI React   │    │  Tiers/M2M   │    │  Partenaires │          │
│  │  (Keycloak)  │    │   (OAuth2)   │    │   (OAuth2)   │          │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘          │
└─────────┼───────────────────┼───────────────────┼───────────────────┘
          │                   │                   │
          │                   │                   │
          ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    webMethods GATEWAY                                │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  /control-plane/v1/*  →  Control Plane API                     │ │
│  │  ├── Rate Limiting (100 req/min standard, 1000 premium)        │ │
│  │  ├── JWT Validation (Keycloak)                                 │ │
│  │  ├── Throttling (50 concurrent)                                │ │
│  │  ├── Analytics & Monitoring                                    │ │
│  │  └── CORS                                                      │ │
│  ├────────────────────────────────────────────────────────────────┤ │
│  │  /apis/*  →  Business APIs (deployed by tenants)               │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    CONTROL PLANE (Internal)                          │
│  ┌─────────────────┐                                                │
│  │ Control-Plane   │──────┬────────┬────────┬────────┐              │
│  │ API (FastAPI)   │      │        │        │        │              │
│  └─────────────────┘      ▼        ▼        ▼        ▼              │
│                      ┌────────┐┌────────┐┌─────┐┌────────┐          │
│                      │ GitLab ││ Kafka  ││ AWX ││Keycloak│          │
│                      │(GitOps)││(Events)││     ││ (IAM)  │          │
│                      └────────┘└────────┘└─────┘└────────┘          │
└─────────────────────────────────────────────────────────────────────┘
```

### Flux d'accès

| Client | Chemin | Auth |
|--------|--------|------|
| UI React | `gateway.apim.cab-i.com/control-plane/v1/*` | Keycloak OIDC (user) |
| Tiers/M2M | `gateway.apim.cab-i.com/control-plane/v1/*` | OAuth2 Client Credentials |
| APIs métier | `gateway.apim.cab-i.com/apis/{tenant}/*` | API Key / OAuth2 |

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

## Structure du Projet

```
apim-aws/
├── control-plane-api/       # FastAPI backend
│   ├── src/
│   │   ├── auth/            # RBAC & Keycloak
│   │   ├── routers/         # API endpoints (+ gateway.py pour admin proxy)
│   │   └── services/        # Business logic (GitLab, Kafka, Gateway, etc.)
│   ├── Dockerfile
│   └── requirements.txt
├── control-plane-ui/        # React frontend
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── contexts/
│   │   └── services/
│   ├── Dockerfile
│   └── package.json
├── ansible/                 # Ansible playbooks (Phase 2.5)
│   ├── playbooks/
│   │   ├── provision-tenant.yaml      # Keycloak + K8s namespaces
│   │   ├── register-api-gateway.yaml  # Import API, OIDC, activation
│   │   ├── configure-gateway-oidc.yaml
│   │   ├── deploy-api.yaml
│   │   ├── sync-gateway.yaml
│   │   ├── promote-portal.yaml
│   │   └── rollback.yaml
│   └── vars/
│       └── secrets.yaml     # Centralized secrets config (no hardcoding)
├── gitops-templates/        # Templates GitOps (Phase 2)
│   ├── _defaults.yaml       # Variables globales centralisées
│   ├── environments/        # Config par environnement (dev/staging/prod)
│   ├── templates/           # Templates API, Tenant, Application
│   └── argocd/
│       ├── chart/           # Helm chart pour ApplicationSets
│       ├── appsets/         # ApplicationSets (deprecated, use chart/)
│       └── projects/        # AppProjects templates
├── charts/                  # Helm charts
│   ├── control-plane-api/
│   ├── control-plane-ui/
│   └── argocd/              # ArgoCD chart
├── scripts/                 # Scripts d'installation
│   ├── install-argocd.sh
│   ├── init-gitlab-gitops.sh
│   └── setup-argocd-gitlab.sh
├── terraform/               # Infrastructure as Code
│   ├── modules/
│   │   ├── vpc/
│   │   ├── eks/
│   │   ├── rds/
│   │   ├── ecr/
│   │   └── secrets/         # AWS Secrets Manager (Phase 2.5)
│   └── environments/
│       └── dev/
├── keycloak/                # Keycloak config
│   └── realm-export.json
└── CLAUDE.md                # Claude Code instructions
```

### GitOps Architecture

```
┌─────────────────────────────┐     ┌─────────────────────────────┐
│  GitHub: apim-aws           │     │  GitLab: apim-gitops        │
│  (Infrastructure + Code)    │     │  (Source of Truth)          │
│  ├── gitops-templates/      │────▶│  ├── _defaults.yaml         │
│  ├── control-plane-api/     │     │  ├── environments/          │
│  ├── terraform/             │     │  └── tenants/               │
│  └── charts/                │     │      ├── acme/              │
└─────────────────────────────┘     │      └── client-xyz/        │
                                    └──────────────┬──────────────┘
                                                   │
                                    ┌──────────────▼──────────────┐
                                    │      ArgoCD                  │
                                    │  (GitOps Sync)               │
                                    │  ├── ApplicationSets         │
                                    │  └── AppProjects per tenant  │
                                    └──────────────┬──────────────┘
                                                   │
                                    ┌──────────────▼──────────────┐
                                    │      Kubernetes (EKS)        │
                                    │  ├── apim-system             │
                                    │  ├── apim-{tenant}-dev       │
                                    │  └── apim-{tenant}-prod      │
                                    └─────────────────────────────┘
```

## Deploiement

### 1. Infrastructure AWS

```bash
# Creer le backend S3/DynamoDB (une seule fois)
aws s3 mb s3://apim-terraform-state-dev --region eu-west-1
aws dynamodb create-table \
  --table-name apim-terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST

# Deployer l'infrastructure
cd terraform/environments/dev
terraform init
terraform plan
terraform apply
```

### 2. Configuration kubectl

```bash
aws eks update-kubeconfig --name apim-dev-cluster --region eu-west-1
```

### 3. Deploiement Helm

```bash
# Namespace
kubectl create namespace apim

# Secrets ECR
kubectl create secret docker-registry ecr-secret \
  --docker-server=848853684735.dkr.ecr.eu-west-1.amazonaws.com \
  --docker-username=AWS \
  --docker-password=$(aws ecr get-login-password) \
  -n apim

# Control Plane API
helm upgrade --install control-plane-api ./charts/control-plane-api \
  --namespace apim \
  --set secrets.KEYCLOAK_CLIENT_SECRET=xxx

# Control Plane UI
helm upgrade --install control-plane-ui ./charts/control-plane-ui \
  --namespace apim
```

### 4. Build et Push des images

```bash
# Login ECR
aws ecr get-login-password --region eu-west-1 | docker login --username AWS --password-stdin 848853684735.dkr.ecr.eu-west-1.amazonaws.com

# Build et push API
cd control-plane-api
docker build -t control-plane-api .
docker tag control-plane-api:latest 848853684735.dkr.ecr.eu-west-1.amazonaws.com/control-plane-api:latest
docker push 848853684735.dkr.ecr.eu-west-1.amazonaws.com/control-plane-api:latest

# Build et push UI
cd ../control-plane-ui
npm install && npm run build
docker build -t control-plane-ui .
docker tag control-plane-ui:latest 848853684735.dkr.ecr.eu-west-1.amazonaws.com/control-plane-ui:latest
docker push 848853684735.dkr.ecr.eu-west-1.amazonaws.com/control-plane-ui:latest
```

## URLs

### Environnement DEV

| Service | URL | Description |
|---------|-----|-------------|
| Control Plane UI | https://devops.apim.cab-i.com | Interface de gestion des APIs |
| Control Plane API | https://api.apim.cab-i.com | Backend REST API |
| Keycloak (Auth) | https://auth.apim.cab-i.com | Identity Provider (OIDC) |
| Keycloak Admin | https://auth.apim.cab-i.com/admin/ | Console admin Keycloak |
| API Gateway UI | https://gateway.apim.cab-i.com/apigatewayui/ | Console Gateway (admin: Administrator/manage) |
| **ArgoCD** | https://argocd.apim.cab-i.com | GitOps CD (admin/demo) |
| **AWX (Ansible)** | https://awx.apim.cab-i.com | Automation (admin/demo) |
| Redpanda Console | `kubectl port-forward svc/redpanda-console 8080:8080 -n apim-system` | Administration Kafka (interne) |
| **GitLab GitOps** | https://gitlab.com/PotoMitan1/apim-gitops | Source of Truth (tenants)

### Environnement STAGING (à venir)

| Service | URL |
|---------|-----|
| Control Plane UI | https://devops.staging.apim.cab-i.com |
| Control Plane API | https://api.staging.apim.cab-i.com |
| Keycloak | https://auth.staging.apim.cab-i.com |
| API Gateway | https://gateway.staging.apim.cab-i.com |

## Utilisateurs par défaut (Instance DEMO)

### Keycloak Admin Console

| Utilisateur | Mot de passe | Rôle | Description |
|-------------|--------------|------|-------------|
| `admin` | `demo` | Super Admin | Accès complet à la console Keycloak |

### Control Plane UI

| Utilisateur | Mot de passe | Rôle | Description |
|-------------|--------------|------|-------------|
| `admin@apim.local` | `demo` | CPI Admin | Accès complet à la plateforme |

> **Note**: Ces credentials sont pour l'instance de démonstration. En production, utiliser des mots de passe forts stockés dans AWS Secrets Manager.

## Coûts Estimés AWS

### Architecture avec OpenSearch partagé (DEV + STAGING)

| Service | Type | Coût mensuel |
|---------|------|-------------|
| EKS Cluster | 1 cluster | ~$72 |
| EC2 (Nodes) | 3x t3.large | ~$180 |
| RDS PostgreSQL | db.t3.small | ~$25 |
| ALB (Ingress) | 1 Load Balancer | ~$20 |
| **OpenSearch** | t3.small.search (1 node, partagé DEV+STAGING) | **~$35** |
| ECR | Storage images | ~$5 |
| Route 53 | DNS | ~$1 |
| Secrets Manager | 5 secrets | ~$2 |
| Bandwidth | Estimation | ~$10 |
| **TOTAL** | | **~$350/mois** |

> **Note**: Upgrade t3.medium → t3.large nécessaire pour Redpanda (Kafka) qui requiert ~1.5GB RAM par broker.

### Architecture Elasticsearch / OpenSearch

```
┌──────────────────────────────────────────────────────────────────┐
│                    GATEWAY / PORTAL                               │
│    ┌─────────────────────────────────────────────────────────┐   │
│    │  Elasticsearch Embarqué (usage interne)                  │   │
│    │  - Configuration, sessions, cache                        │   │
│    │  - webMethods 10.15 requiert ES 8+ (incompatible OS 2.x) │   │
│    └─────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
                              │
                    Global Policies (par tenant)
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│              Amazon OpenSearch (t3.small.search)                  │
│                 Analytics Multi-tenant par tenant                 │
├──────────────────────────────────────────────────────────────────┤
│  Configuré via Global Policy sur la Gateway                      │
│  Index Pattern: {env}-{tenant}-{type}                            │
│                                                                   │
│  DEV:                           STAGING:                         │
│  ├── dev-tenant-a-analytics    ├── staging-tenant-a-analytics   │
│  ├── dev-tenant-b-analytics    ├── staging-tenant-b-analytics   │
│  └── ...                        └── ...                          │
└──────────────────────────────────────────────────────────────────┘
```

### Note sur la compatibilité ES/OpenSearch

webMethods API Gateway 10.15 (image lean) nécessite **Elasticsearch 8+** pour son usage interne.
Amazon OpenSearch 2.x est compatible ES 7.x, donc **non compatible**.

**Solution actuelle**:
- **Elasticsearch 8.11** déployé sur EKS (StatefulSet custom, xpack.security.enabled: false)
- Gateway et Portal connectés à ES 8 interne
- **OpenSearch** disponible pour analytics multi-tenant via Global Policies

### Services de connexion (URLs internes)

| Service | URL Interne | Notes |
|---------|-------------|-------|
| Elasticsearch | `elasticsearch-master:9200` | Pas d'auth (xpack.security.enabled: false) |
| Redpanda (Kafka) | `redpanda.apim-system.svc.cluster.local:9092` | Pas d'auth |
| Keycloak | `https://auth.apim.cab-i.com` | Realm: `apim`, Client: `control-plane-api` |

### Configuration Control Plane UI - Tenant Mapping

L'UI Control Plane récupère les informations du tenant depuis le jeton JWT Keycloak.

**Informations disponibles en lecture seule**:
- Nom du tenant
- CPI Admin associé
- DevOps assigné

**Fichier de configuration Git** (mapping CPI/DevOps/Tenant):
```yaml
# apim-gitops/config/tenant-mapping.yaml
tenants:
  tenant-finance:
    name: "Finance Corp"
    cpi_admin: "admin-finance@company.com"
    devops:
      - "devops1@company.com"
      - "devops2@company.com"
  tenant-hr:
    name: "HR Department"
    cpi_admin: "admin-hr@company.com"
    devops:
      - "devops3@company.com"
```

> **Note**: Le matching CPI/DevOps/Tenant se fait via fichier de configuration dans le repo GitOps. Une future version pourra intégrer cette config directement dans Keycloak (custom claims).

### Keycloak comme Identity Provider (IdP)

Keycloak est configuré comme IdP central pour l'authentification OIDC:

**Realm Configuration**:
- **Realm**: `apim`
- **URL**: `https://auth.apim.cab-i.com/realms/apim`
- **Discovery**: `https://auth.apim.cab-i.com/realms/apim/.well-known/openid-configuration`

**Clients Configurés**:
| Client ID | Type | Usage |
|-----------|------|-------|
| `control-plane-api` | Confidential | Backend API authentication |
| `control-plane-ui` | Public | Frontend SPA (PKCE) |
| `api-gateway` | Confidential | Gateway JWT validation (futur) |

**Roles par Realm**:
| Rôle | Description |
|------|-------------|
| `cpi-admin` | Administrateur plateforme complet |
| `tenant-admin` | Admin de son propre tenant |
| `devops` | Déploiement et promotion APIs |
| `viewer` | Lecture seule |

**Custom Claims JWT** (à implémenter):
```json
{
  "sub": "user-uuid",
  "preferred_username": "admin@apim.local",
  "realm_access": { "roles": ["cpi-admin"] },
  "tenant_id": "tenant-finance",
  "tenant_role": "admin"
}
```

### Estimation Ressources - Architecture Finale

**Configuration actuelle (DEV)**: 3x t3.large (2 vCPU / 8GB RAM chacun)

**Ressources par composant**:
| Composant | CPU Request | Memory Request | Replicas | Total CPU | Total RAM |
|-----------|-------------|----------------|----------|-----------|-----------|
| Elasticsearch 8 | 250m | 1Gi | 1 | 250m | 1Gi |
| API Gateway | 250m | 1Gi | 1 | 250m | 1Gi |
| Redpanda (Kafka) | 1000m | 2Gi | 1 | 1000m | 2Gi |
| Keycloak | 200m | 512Mi | 1 | 200m | 512Mi |
| Control-Plane API | 100m | 256Mi | 2 | 200m | 512Mi |
| Control-Plane UI | 50m | 64Mi | 1 | 50m | 64Mi |
| AWX (Web) | 100m | 512Mi | 1 | 100m | 512Mi |
| AWX (Task + EE) | 200m | 768Mi | 1 | 200m | 768Mi |
| Ingress Controller | 100m | 256Mi | 2 | 200m | 512Mi |
| Cert-Manager | 50m | 64Mi | 1 | 50m | 64Mi |
| EBS CSI Driver | 50m | 128Mi | 2 | 100m | 256Mi |
| **TOTAL** | | | | **~2.7 vCPU** | **~7.8Gi** |

**Réserve système K8s**: ~600m CPU, ~1Gi RAM par node

**Capacité disponible** (3x t3.large = 6 vCPU / 24GB):
- CPU: 6000m - 1800m (système 3 nodes) = 4200m disponible → ✅ 2700m utilisé (64%)
- RAM: 24GB - 3GB (système) = 21GB disponible → ✅ 7.8GB utilisé (37%)

**Options pour scaling futur**:
| Option | Coût mensuel | Capacité | Recommandation |
|--------|--------------|----------|----------------|
| Actuel: 3x t3.large | ~$180 | 6 vCPU / 24GB | ✅ DEV (actuel avec AWX) |
| 3x t3.xlarge | ~$360 | 12 vCPU / 48GB | ✅ STAGING + replicas |
| 4x t3.large | ~$240 | 8 vCPU / 32GB | ✅ PROD HA |

> **Configuration DEV actuelle**: 3x t3.large avec AWX inclus. Les pods restent en standalone (replicas=1).
>
> **Recommandation STAGING**: Passer à 3x t3.xlarge pour supporter replicas=2 sur les composants critiques.
>
> **Note Gateway Cluster**: Pour scaler la Gateway au-delà de 1 replica, il faut configurer Ignite pour le clustering.

### Sécurité Réseau

Les pods Gateway et Portal sont isolés du réseau externe via NetworkPolicies:
- Accès bloqué vers Internet (metering.softwareag.cloud, etc.)
- Communication autorisée uniquement au sein du cluster (VPC CIDR)

### Comparaison des options

| Configuration | Coût/mois | Avantages |
|--------------|-----------|-----------|
| ES 7.2.0 sur EKS + OpenSearch analytics | ~$220 | Multi-tenant analytics, compatibilité assurée |
| Production (ES 7 cluster + OpenSearch) | ~$280 | Haute disponibilité complète |

## Références webMethods

- [webMethods API Gateway](https://github.com/ibm-wm-transition/webmethods-api-gateway) - Documentation officielle
- [webMethods API Gateway DevOps](https://github.com/SoftwareAG/webmethods-api-gateway-devops) - Scripts CI/CD et déploiement
- [Docker Compose Samples](https://github.com/ibm-wm-transition/webmethods-api-gateway/tree/master/samples/docker/deploymentscripts) - Exemples Docker

---

## État Actuel vs Architecture Cible

### Composants Déployés ✅

| Composant | Status | Notes |
|-----------|--------|-------|
| EKS Cluster | ✅ Déployé | apim-dev-cluster |
| VPC / Subnets | ✅ Déployé | 10.0.0.0/16 |
| RDS PostgreSQL | ✅ Déployé | db.t3.micro |
| ECR Repositories | ✅ Déployé | control-plane-api, control-plane-ui, apim/* |
| Nginx Ingress | ✅ Déployé | avec cert-manager |
| Cert-Manager | ✅ Déployé | Let's Encrypt prod |
| Keycloak | ✅ Déployé | https://auth.apim.cab-i.com |
| Control-Plane API | ✅ Déployé | FastAPI backend |
| Control-Plane UI | ✅ Déployé | React frontend |
| Elasticsearch 8.11 | ✅ Déployé | Sur EKS, cluster SAG_EventDataStore (ES 8+ requis pour Gateway 10.15) |
| webMethods Gateway | ✅ Déployé | Image lean trial 10.15 |
| NetworkPolicies | ✅ Déployé | Bloque accès Internet (metering.softwareag.cloud) |
| EBS CSI Driver | ✅ Déployé | Pour volumes persistants |
| **Redpanda (Kafka)** | ✅ Déployé | Event streaming, 1 broker, Redpanda Console |
| **Kafka Topics** | ✅ Déployé | api-created/updated/deleted, deploy-requests/results, audit-log, notifications |
| **Kafka Producer** | ✅ Déployé | Intégré dans Control-Plane API (émission events sur CRUD) |
| **AWX (Ansible Tower)** | ✅ Déployé | AWX 24.6.1 via Operator, https://awx.apim.cab-i.com |

### Composants À Déployer 🔲

| Composant | Priorité | Description |
|-----------|----------|-------------|
| AWX Job Templates | Haute | Jobs pour déploiement APIs (deploy-api, sync-gateway, etc.) |
| GitLab (GitOps) | Haute | Source de vérité pour configs |
| **ArgoCD** | Haute | GitOps operator, sync automatique K8s |
| Vault | Moyenne | Gestion des secrets (clientSecret, apiKey) |
| Grafana + Prometheus | Moyenne | Monitoring et alerting |
| OpenSearch Analytics | Basse | Analytics multi-tenant (Global Policies) |

### Next Steps - Roadmap

#### Phase 1 : Event-Driven Architecture ✅ COMPLÉTÉ (21 Déc 2024)

> **Infrastructure**: Nodes scalés à 3x t3.large (2 CPU / 8GB RAM chacun) pour supporter Redpanda + AWX.

1. **Redpanda Déployé** ✅
   - Kafka-compatible, 1 broker sur EKS
   - Redpanda Console pour administration
   - Storage: 10GB persistant (EBS gp2)
   - Endpoint interne: `redpanda.apim-system.svc.cluster.local:9092`

2. **Topics Kafka Créés** ✅
   - `api-created` - Événements création API
   - `api-updated` - Événements modification API
   - `api-deleted` - Événements suppression API
   - `deploy-requests` - Demandes de déploiement
   - `deploy-results` - Résultats de déploiement
   - `audit-log` - Logs d'audit
   - `notifications` - Notifications temps réel

3. **Kafka Producer Intégré** ✅
   - Control-Plane API émet des événements Kafka sur chaque opération CRUD
   - Topics utilisés: `api-created`, `api-updated`, `api-deleted`, `notifications`
   - Événements d'audit automatiques sur `audit-log`
   - Connection: `redpanda.apim-system.svc.cluster.local:9092`

   **Dashboard End-to-End Pipeline**:
   ```
   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
   │ Control-Plane│ → │   Kafka    │ → │   AWX/Ansible│ → │   Gateway   │
   │   (CRUD)    │    │  (Events)   │    │  (Deploy)   │    │  (Runtime)  │
   └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
         ✅                 ✅                  ✅                 ✅
   ```

4. **AWX (Ansible Tower)** ✅ DÉPLOYÉ + CONFIGURÉ
   - AWX 24.6.1 via AWX Operator 2.19.1
   - URL: https://awx.apim.cab-i.com
   - Login: admin / demo
   - Base de données: RDS PostgreSQL (partagée avec Keycloak)

   **Job Templates Configurés** ✅:
   - `Deploy API` (id: 8) - Déploie une API sur la Gateway
   - `Sync Gateway` (id: 9) - Synchronise config Gateway
   - `Rollback API` (id: 11) - Rollback en cas d'échec

   **Intégration Kafka** ✅:
   - Deployment Worker dans Control-Plane API
   - Consumer sur topic `deploy-requests`
   - Monitoring des jobs AWX avec publish sur `deploy-results`

5. **GitLab Webhook** ✅ CONFIGURÉ
   - Endpoint: `POST /webhooks/gitlab`
   - Events supportés: Push, Merge Request, Tag Push
   - Auto-deploy sur push vers `main` branch
   - Configuration: voir [docs/GITOPS-SETUP.md](docs/GITOPS-SETUP.md)

6. **Control-Plane UI** ✅ FONCTIONNEL
   - Interface React avec authentification Keycloak (PKCE)
   - Pages: Dashboard, Tenants, APIs, Applications, Deployments, Monitoring
   - URL: https://devops.apim.cab-i.com

7. **Configuration Variabilisée** ✅ (21 Déc 2024)
   - **UI** ([config.ts](control-plane-ui/src/config.ts)): Toutes les URLs et configs via `VITE_*` env vars
   - **API** ([config.py](control-plane-api/src/config.py)): Settings centralisés avec pydantic-settings
   - **Dockerfiles**: Build args pour personnalisation par environnement

   **Variables UI disponibles**:
   | Variable | Description | Défaut |
   |----------|-------------|--------|
   | `VITE_BASE_DOMAIN` | Domaine de base | `apim.cab-i.com` |
   | `VITE_API_URL` | URL API backend | `https://api.{domain}` |
   | `VITE_KEYCLOAK_URL` | URL Keycloak | `https://auth.{domain}` |
   | `VITE_KEYCLOAK_REALM` | Realm Keycloak | `apim` |
   | `VITE_GATEWAY_URL` | URL Gateway | `https://gateway.{domain}` |
   | `VITE_AWX_URL` | URL AWX | `https://awx.{domain}` |
   | `VITE_ENABLE_*` | Feature flags | `true` |

   **Variables API disponibles**:
   | Variable | Description | Défaut |
   |----------|-------------|--------|
   | `BASE_DOMAIN` | Domaine de base | `apim.cab-i.com` |
   | `KEYCLOAK_URL` | URL Keycloak | `https://auth.{domain}` |
   | `KEYCLOAK_REALM` | Realm | `apim` |
   | `KAFKA_BOOTSTRAP_SERVERS` | Brokers Kafka | `redpanda:9092` |
   | `AWX_URL` | URL AWX | `https://awx.{domain}` |
   | `CORS_ORIGINS` | Origins CORS autorisées | `https://devops.{domain}` |
   | `LOG_LEVEL` | Niveau de log | `INFO` |

8. **Authentification PKCE** ✅ (21 Déc 2024)
   - Keycloak 25+ requiert PKCE pour clients publics
   - Configuration `oidc-client-ts` avec `response_type: 'code'` et `pkce_method: 'S256'`
   - Login fonctionnel via https://devops.apim.cab-i.com

#### Phase 2 : GitOps + Variables d'Environnement (Priorité Haute)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         GITOPS ARCHITECTURE                                   │
│                                                                               │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐   │
│  │Control-Plane│ →  │   GitLab    │ →  │   ArgoCD    │ →  │ Kubernetes  │   │
│  │   (CRUD)    │    │  (Source)   │    │   (Sync)    │    │  (Deploy)   │   │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘   │
│        ↑                  ↑                  ↓                  ↓            │
│        │                  │            ┌─────────────┐    ┌─────────────┐   │
│        │                  └────────────│   Webhooks  │    │  Gateway    │   │
│        │                               └─────────────┘    │  + Portal   │   │
│        └───────────────────────────────────────────────   └─────────────┘   │
└──────────────────────────────────────────────────────────────────────────────┘
```

1. **Configurer GitLab**
   - Repository `apim-gitops`
   - Structure: `tenants/{tenant}/apis/{api}/`
   - Branches: `main` (prod), `staging`, `dev`

2. **Déployer ArgoCD** 🔲
   - Helm chart: `argo/argo-cd`
   - ApplicationSets pour multi-tenant
   - Sync automatique sur push GitLab
   - Health checks personnalisés pour Gateway
   ```yaml
   # ArgoCD Application example
   apiVersion: argoproj.io/v1alpha1
   kind: Application
   metadata:
     name: apim-tenant-finance
   spec:
     source:
       repoURL: https://gitlab.com/apim/apim-gitops
       path: tenants/tenant-finance
     destination:
       server: https://kubernetes.default.svc
     syncPolicy:
       automated:
         prune: true
         selfHeal: true
   ```

3. **Intégrer Git dans Control-Plane API**
   - Commit automatique sur CRUD
   - Sync bidirectionnel
   - Git clone/pull via GitPython

4. **Webhooks GitLab → Control-Plane**
   - Synchronisation des changements externes
   - Trigger ArgoCD sync

5. **Gestion des Variables d'Environnement** 🔲

   **Problématique**: Une API doit pointer vers des backends différents par environnement, sans secrets dans Git.

   ```
   ┌─────────────────────────────────────────────────────────────────────┐
   │  payment-api doit pointer vers :                                     │
   │    DEV     → https://payment-dev.internal.cab-i.com                  │
   │    STAGING → https://payment-staging.internal.cab-i.com              │
   │    PROD    → https://payment.internal.cab-i.com                      │
   │                                                                       │
   │  ✅ Solution : Templates avec placeholders + Vault pour secrets      │
   └─────────────────────────────────────────────────────────────────────┘
   ```

   **Structure GitOps étendue**:
   ```
   apim-gitops/
   ├── tenants/
   │   └── tenant-finance/
   │       └── apis/
   │           └── payment-api/
   │               ├── api.yaml              # Template avec ${PLACEHOLDERS}
   │               ├── openapi.yaml
   │               └── environments/         # Config par environnement
   │                   ├── _defaults.yaml    # Valeurs par défaut
   │                   ├── dev.yaml          # Overrides DEV
   │                   ├── staging.yaml      # Overrides STAGING
   │                   └── prod.yaml         # Overrides PROD
   │
   ├── environments/                         # Configuration globale par env
   │   ├── dev/
   │   │   ├── config.yaml
   │   │   └── secrets-refs.yaml             # Références Vault
   │   ├── staging/
   │   └── prod/
   │
   └── policies/
   ```

   **Exemple Template API (api.yaml)**:
   ```yaml
   apiVersion: apim.cab-i.com/v1
   kind: API
   metadata:
     name: payment-api
     tenant: tenant-finance
   spec:
     backend:
       url: "${BACKEND_URL}"                    # Résolu au déploiement
       timeout: "${BACKEND_TIMEOUT:30s}"        # Valeur par défaut: 30s
       authentication:
         type: "${BACKEND_AUTH_TYPE:oauth2}"
         credentials:
           clientIdRef: "${BACKEND_CLIENT_ID_REF}"      # Référence Vault
           clientSecretRef: "${BACKEND_CLIENT_SECRET_REF}"
   ```

   **Exemple Configuration Environnement (dev.yaml)**:
   ```yaml
   apiVersion: apim.cab-i.com/v1
   kind: APIEnvironmentConfig
   metadata:
     name: payment-api-dev
     environment: dev
   variables:
     BACKEND_URL: "https://payment-dev.internal.cab-i.com"
     BACKEND_TOKEN_URL: "https://auth-dev.internal.cab-i.com/oauth/token"
     BACKEND_CLIENT_ID_REF: "vault:secret/data/dev/payment-api#client_id"
     BACKEND_CLIENT_SECRET_REF: "vault:secret/data/dev/payment-api#client_secret"
     LOG_LEVEL: "DEBUG"
     RATE_LIMIT_RPS: "1000"
   ```

6. **Variable Resolver dans Control-Plane API** 🔲
   - Service Python pour résoudre les `${PLACEHOLDERS}`
   - Fusion: _defaults.yaml + {env}.yaml + global config
   - Résolution des références Vault au moment du déploiement

7. **Gestion des Tenants et Rôles (IAM)** 🔲

   **Architecture IAM** - Gestion des utilisateurs et leurs rôles par tenant:

   ```
   ┌─────────────────────────────────────────────────────────────────────────────────────┐
   │                              SOURCES D'IDENTITÉ                                      │
   │                                                                                      │
   │   PHASE 1 (Actuel)              PHASE 2 (Cible)                                     │
   │   ─────────────────             ────────────────                                     │
   │                                                                                      │
   │   ┌─────────────────┐           ┌─────────────────┐                                 │
   │   │   GitLab File   │           │   Référentiel   │                                 │
   │   │                 │           │   Entreprise    │                                 │
   │   │ iam/tenants.yaml│    →→→    │                 │                                 │
   │   │ - CPI           │           │ • LDAP / AD     │                                 │
   │   │ - DevOps        │           │ • API RH        │                                 │
   │   │ - Viewers       │           │ • SCIM          │                                 │
   │   └────────┬────────┘           └────────┬────────┘                                 │
   │            │                             │                                           │
   │            └──────────────┬──────────────┘                                          │
   │                           ▼                                                          │
   │            ┌──────────────────────────────┐                                         │
   │            │      Keycloak (IdP)          │                                         │
   │            │  • Sync users & groups       │                                         │
   │            │  • Map roles to tenants      │                                         │
   │            │  • Issue JWT with claims     │                                         │
   │            └──────────────┬───────────────┘                                         │
   │                           ▼                                                          │
   │            ┌──────────────────────────────┐                                         │
   │            │     Control-Plane API        │                                         │
   │            │  JWT: tenant_id, roles[]     │                                         │
   │            └──────────────────────────────┘                                         │
   └─────────────────────────────────────────────────────────────────────────────────────┘
   ```

   **Structure GitOps IAM**:
   ```
   apim-gitops/
   ├── iam/                              # Identity & Access Management
   │   ├── tenants.yaml                  # Définition tenants + membres
   │   ├── global-admins.yaml            # CPI Admins globaux
   │   └── service-accounts.yaml         # Comptes CI/CD, monitoring
   │
   └── tenants/
       └── ...
   ```

   **Exemple tenants.yaml**:
   ```yaml
   apiVersion: apim.cab-i.com/v1
   kind: TenantRegistry
   metadata:
     name: tenant-registry
     lastUpdated: "2024-12-21T10:00:00Z"

   tenants:
     - id: tenant-finance
       displayName: "Finance Department"
       status: active
       owner:
         email: "jean.dupont@cab-i.com"
         name: "Jean Dupont"
       quotas:
         maxApis: 50
         maxApplications: 20
       environments:
         - dev
         - staging
       members:
         cpi:                               # Tenant Admins
           - email: "jean.dupont@cab-i.com"
             name: "Jean Dupont"
             addedAt: "2024-01-15T10:00:00Z"
             addedBy: "admin@apim.local"
         devops:                            # Deploy & Promote
           - email: "pierre.durand@cab-i.com"
             name: "Pierre Durand"
             addedAt: "2024-01-20T14:00:00Z"
             addedBy: "jean.dupont@cab-i.com"
         viewers:                           # Read-only
           - email: "audit@cab-i.com"
             name: "Audit Team"
             addedAt: "2024-01-15T10:00:00Z"
             addedBy: "admin@apim.local"
   ```

   **Exemple global-admins.yaml**:
   ```yaml
   apiVersion: apim.cab-i.com/v1
   kind: GlobalAdminRegistry
   metadata:
     name: global-admins

   admins:
     - email: "admin@apim.local"
       name: "Platform Admin"
       role: "cpi-admin"
       permissions: ["tenants:*", "apis:*", "users:*"]
   ```

   **IAM Sync Service** (CronJob toutes les 5 min):
   - Parse `iam/tenants.yaml` depuis Git
   - Détecte les changements (diff)
   - Synchronise vers Keycloak (users, groups, roles)
   - Publie événement `iam-sync` sur Kafka

   **API Endpoints IAM**:
   | Endpoint | Description |
   |----------|-------------|
   | `GET /v1/iam/tenants/{id}/members` | Liste les membres d'un tenant |
   | `POST /v1/iam/tenants/{id}/members` | Ajoute un membre (commit Git + sync) |
   | `DELETE /v1/iam/tenants/{id}/members` | Retire un membre |
   | `POST /v1/iam/sync` | Force une synchronisation Git → Keycloak |

   **Workflow ajout membre**:
   ```
   1. CPI ajoute un membre via UI
            ↓
   2. API met à jour iam/tenants.yaml (Git commit)
            ↓
   3. CronJob IAM Sync (5 min) ou sync immédiat
            ↓
   4. Keycloak: User + Group + Role
            ↓
   5. User se connecte → JWT avec tenant_id + roles
   ```

   **Phase 2 (Cible) - Référentiel Entreprise**:
   - LDAP/AD Federation dans Keycloak
   - Groupes AD: `GRP_APIM_{TENANT}_{ROLE}` (ex: `GRP_APIM_FINANCE_CPI`)
   - Git = Override pour externes et service accounts
   - Mapping automatique département → tenant

#### Phase 2.5 : Validation E2E - COMPLÉTÉ ✅ (22 Déc 2024)

> **Objectif**: Valider le flow complet GitOps → Keycloak → Gateway avec tenant admin APIM.

1. **Gateway OIDC Configuration** ✅
   - External Authorization Server `KeycloakOIDC` configuré dans Gateway
   - OAuth2 Strategies par application avec JWT validation
   - Scope mappings standardisés: `{AuthServer}:{Tenant}:{Api}:{Version}:{Scope}`
   - APIs sécurisées: Control-Plane-API, Gateway-Admin-API

2. **Gateway Admin Service** ✅
   - Proxy OIDC vers Gateway administration (port 5555)
   - Token forwarding: JWT utilisateur transmis à Gateway pour audit trail
   - Fallback Basic Auth pour compatibilité legacy
   - Router `/v1/gateway/*` dans Control-Plane API
   - Config: `GATEWAY_USE_OIDC_PROXY=True` (défaut)

   **Endpoints disponibles**:
   | Endpoint | Description |
   |----------|-------------|
   | `GET /v1/gateway/apis` | Liste les APIs Gateway |
   | `POST /v1/gateway/apis` | Importe une API (OpenAPI spec) |
   | `GET /v1/gateway/applications` | Liste les applications |
   | `PUT /v1/gateway/apis/{id}/activate` | Active une API |
   | `POST /v1/gateway/configure-oidc` | Configure OIDC pour une API |

3. **Sécurisation des Secrets** ✅ (AWS Secrets Manager + K8s)

   **Stratégie de secrets**:
   ```
   ┌─────────────────────────────────────────────────────────────────────────┐
   │                    SECRETS MANAGEMENT STRATEGY                           │
   │                                                                          │
   │  AWS SECRETS MANAGER (Bootstrap)      K8s SECRETS / VAULT (Runtime)     │
   │  ─────────────────────────────────    ──────────────────────────────    │
   │  • gateway-admin                      • OAuth client secrets             │
   │  • keycloak-admin                     • Tenant API keys                  │
   │  • rds-master                         • Application tokens               │
   │  • opensearch-master                  • Service account credentials      │
   │  • gitlab-token                       • Rotated credentials              │
   │  • awx-token                                                             │
   │                                                                          │
   │  Path: apim/{env}/{secret-name}       Path: secret/data/{env}/{tenant}   │
   │  Managed by: Terraform                Managed by: Vault / K8s External   │
   └─────────────────────────────────────────────────────────────────────────┘
   ```

   **Module Terraform** (`terraform/modules/secrets/`):
   - Auto-génération de passwords sécurisés
   - Outputs pour External Secrets Operator
   - Recovery window: 0 (dev), 30 jours (prod)

   **Configuration Ansible** (`ansible/vars/secrets.yaml`):
   - Variables centralisées pour tous les playbooks
   - Validation obligatoire des secrets critiques
   - Support lookup env / Vault

4. **Tenant APIM Platform** ✅
   - Tenant administrateur avec accès cross-tenant
   - User: `apimadmin@cab-i.com` (role: cpi-admin)
   - Structure dans GitLab apim-gitops

5. **Playbooks Ansible** ✅
   - `provision-tenant.yaml` - Crée groupes Keycloak, users, namespaces K8s
   - `register-api-gateway.yaml` - Import OpenAPI, OIDC, rate limiting, activation
   - `configure-gateway-oidc.yaml` - Configuration OIDC complète
   - `deploy-api.yaml` - Import API avec conversion OpenAPI 3.1→3.0 + activation
   - Tous playbooks sécurisés avec `vars_files` (zéro hardcoding)

6. **AWX Job Templates** ✅
   - `Provision Tenant` (ID: 12) - Provisioning tenant complet
   - `Register API Gateway` (ID: 13) - Enregistrement API dans Gateway
   - `Deploy API` (ID: 8) - Import API via OIDC proxy avec conversion OpenAPI

7. **OpenAPI 3.1.0 Compatibility** ✅ (23 Déc 2024)
   - webMethods Gateway 10.15 ne supporte pas OpenAPI 3.1.0
   - Conversion automatique 3.1.x → 3.0.0 dans `deploy-api.yaml`
   - Support swagger 2.0 et OpenAPI 3.0.x natifs
   - POST /v1/gateway/apis - Endpoint proxy pour import API
   - Test validé: Control-Plane-API-E2E v2.2 déployée et activée

#### Phase 3 : Secrets & Gateway Alias (Priorité Moyenne)

**Approche Hybride : Git + Gateway Alias**

Les **Alias webMethods Gateway** permettent de stocker endpoints et credentials séparément des APIs. L'approche hybride combine Git comme source de vérité avec les Alias pour la gestion runtime.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    APPROCHE HYBRIDE : GIT + ALIAS                            │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         GIT (Source de Vérité)                       │    │
│  │                                                                      │    │
│  │  1. Définition API (api.yaml)                                        │    │
│  │     → backend_alias: "${BACKEND_ALIAS}"                              │    │
│  │                                                                      │    │
│  │  2. Config Environnement (environments/dev.yaml)                     │    │
│  │     → BACKEND_ALIAS: payment-backend-dev                             │    │
│  │                                                                      │    │
│  │  3. Définition Alias (aliases/dev/payment-backend.yaml)              │    │
│  │     → URL endpoint + Références Vault                                │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    AWX Jobs                                          │    │
│  │                                                                      │    │
│  │  sync-alias     → Crée/Update Alias sur Gateway (credentials Vault)  │    │
│  │  deploy-api     → Déploie API (référence alias existant)             │    │
│  │  rotate-creds   → Refresh credentials sans redeploy API              │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    GATEWAY (Runtime)                                 │    │
│  │                                                                      │    │
│  │  Alias: payment-backend-dev                                          │    │
│  │    ├── url: https://payment-dev.internal.cab-i.com                   │    │
│  │    ├── auth: oauth2                                                  │    │
│  │    └── credentials: *** (depuis Vault)                               │    │
│  │                                                                      │    │
│  │  API: payment-api → backend_alias: payment-backend-dev               │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

1. **Déployer HashiCorp Vault** 🔲
   - Secrets dynamiques pour clients OAuth2
   - API Keys rotation
   - AppRole par environnement
   - Structure: `secret/data/{env}/{api}#key`

2. **Structure GitOps avec Alias** 🔲
   ```
   apim-gitops/
   ├── tenants/
   │   └── tenant-finance/
   │       └── apis/
   │           └── payment-api/
   │               ├── api.yaml              # backend_alias: "${BACKEND_ALIAS}"
   │               └── environments/
   │                   ├── dev.yaml          # BACKEND_ALIAS: payment-backend-dev
   │                   ├── staging.yaml      # BACKEND_ALIAS: payment-backend-staging
   │                   └── prod.yaml         # BACKEND_ALIAS: payment-backend-prod
   │
   ├── aliases/                              # Définition des Alias Gateway
   │   ├── dev/
   │   │   ├── payment-backend.yaml
   │   │   └── invoice-backend.yaml
   │   ├── staging/
   │   │   └── payment-backend.yaml
   │   └── prod/
   │       └── payment-backend.yaml
   ```

3. **Définition Alias Gateway (aliases/dev/payment-backend.yaml)** 🔲
   ```yaml
   apiVersion: apim.cab-i.com/v1
   kind: GatewayAlias
   metadata:
     name: payment-backend-dev
     environment: dev
   spec:
     type: endpoint
     endpoint:
       url: https://payment-dev.internal.cab-i.com
       connectionTimeout: 30000
       readTimeout: 60000
     authentication:
       type: oauth2
       oauth2:
         tokenUrl: https://auth-dev.internal.cab-i.com/oauth/token
         clientIdRef: vault:secret/data/dev/payment-backend#client_id
         clientSecretRef: vault:secret/data/dev/payment-backend#client_secret
         scopes: ["read", "write"]
   ```

4. **Jobs AWX pour Gestion Alias** 🔲

   | Job | Trigger | Action |
   |-----|---------|--------|
   | `sync-alias` | Changement `aliases/**/*.yaml` | Crée/Update alias sur Gateway avec credentials Vault |
   | `deploy-api` | Changement `apis/**/api.yaml` | Deploy API (utilise alias existant) |
   | `rotate-credentials` | Planifié (cron) ou Manuel | Refresh credentials Vault → Gateway Alias |
   | `full-deploy` | Nouveau tenant/API | sync-alias + deploy-api |

5. **Intégrer Vault dans Control-Plane API** 🔲
   - VaultService pour récupérer secrets
   - Résolution des références `vault:path#key`
   - Cache avec TTL pour performances

6. **Avantages de l'Approche Hybride**

   | Aspect | Bénéfice |
   |--------|----------|
   | **Git = Source de Vérité** | Tout versionné, auditable, rollback Git possible |
   | **Alias = Abstraction** | API découplée du backend, promotion simplifiée |
   | **Rotation Credentials** | Update alias sans toucher à l'API déployée |
   | **Pas de Drift** | Git définit les alias, AWX synchronise sur Gateway |
   | **Promotion Zero-Change** | Même API.yaml, juste l'alias change par env |

7. **Workflow de Promotion DEV → STAGING**
   ```
   ┌─────────────────────────────────────────────────────────────────────────────┐
   │  1. API identique (api.yaml ne change pas)                                   │
   │  2. Seul environments/staging.yaml diffère: BACKEND_ALIAS: payment-backend-staging │
   │  3. L'alias payment-backend-staging existe déjà (provisionné par sync-alias) │
   │  4. AWX deploy-api résout ${BACKEND_ALIAS} → payment-backend-staging         │
   │  ✅ Promotion sans modification de code, credentials sécurisés              │
   └─────────────────────────────────────────────────────────────────────────────┘
   ```

#### Phase 4 : Observabilité avec OpenSearch (Priorité Moyenne)

Stack complète d'observabilité pour APIM Platform utilisant **Amazon OpenSearch** pour le stockage centralisé des traces et métriques.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      OBSERVABILITY STACK                                      │
│                                                                               │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │                     COLLECTORS                                        │    │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐          │    │
│  │  │  Control-Plane │  │    FluentBit   │  │  Prometheus    │          │    │
│  │  │  Trace Events  │  │ (Log Shipping) │  │   (Metrics)    │          │    │
│  │  └───────┬────────┘  └───────┬────────┘  └───────┬────────┘          │    │
│  └──────────┼───────────────────┼───────────────────┼────────────────────┘    │
│             │                   │                   │                          │
│             ▼                   ▼                   ▼                          │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │               Amazon OpenSearch (t3.small.search)                     │    │
│  │                                                                       │    │
│  │  Indices:                                                             │    │
│  │  ├── apim-traces-*       (Pipeline traces GitLab→Kafka→AWX→Gateway)  │    │
│  │  ├── apim-logs-*         (Application logs)                          │    │
│  │  ├── apim-metrics-*      (Time-series metrics)                       │    │
│  │  └── apim-analytics-*    (API usage analytics par tenant)            │    │
│  │                                                                       │    │
│  │  Features:                                                            │    │
│  │  ├── Full-text search sur commit messages, erreurs                   │    │
│  │  ├── Agrégations temps réel (stats pipelines)                        │    │
│  │  ├── Rétention automatique (30 jours traces, 7 jours logs)           │    │
│  │  └── Alerting intégré (anomalie detection)                           │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                              │                                                │
│                              ▼                                                │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │                    VISUALIZATION LAYER                                │    │
│  │                                                                       │    │
│  │  ┌────────────────────────────┐  ┌────────────────────────────┐      │    │
│  │  │   OpenSearch Dashboards    │  │    Control-Plane UI         │      │    │
│  │  │   (Kibana-compatible)      │  │    Page Monitoring          │      │    │
│  │  │   • Dashboards prédéfinis  │  │    • Timeline pipelines     │      │    │
│  │  │   • Alerting rules         │  │    • Stats en temps réel    │      │    │
│  │  │   • Anomaly detection      │  │    • Drill-down par trace   │      │    │
│  │  └────────────────────────────┘  └────────────────────────────┘      │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Architecture Pipeline Tracing avec OpenSearch**:

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  GitLab  │───▶│ Control- │───▶│  Kafka   │───▶│   AWX    │───▶│ Gateway  │
│  Push    │    │  Plane   │    │ (Events) │    │  (Jobs)  │    │ (Deploy) │
└──────────┘    └────┬─────┘    └──────────┘    └──────────┘    └──────────┘
                     │                                                │
                     │ PipelineTrace Events                          │
                     ▼                                                ▼
              ┌────────────────────────────────────────────────────────────┐
              │                      OpenSearch                             │
              │  Index: apim-traces-2024.12                                 │
              │  {                                                          │
              │    "trace_id": "trc-abc123",                                │
              │    "trigger_type": "gitlab-push",                           │
              │    "git_author": "john.doe",                                │
              │    "git_commit_sha": "abc123",                              │
              │    "git_commit_message": "Update payment API",              │
              │    "tenant_id": "tenant-finance",                           │
              │    "api_name": "payment-api",                               │
              │    "steps": [                                               │
              │      {"name": "webhook_received", "status": "success", ...},│
              │      {"name": "kafka_publish", "status": "success", ...},   │
              │      {"name": "awx_trigger", "status": "success", ...}      │
              │    ],                                                       │
              │    "status": "success",                                     │
              │    "total_duration_ms": 4523                                │
              │  }                                                          │
              └────────────────────────────────────────────────────────────┘
```

1. **Amazon OpenSearch Service** (~$35/mois)
   - Instance: t3.small.search (1 node partagé DEV+STAGING)
   - Storage: 20GB EBS gp3
   - Indices:
     - `apim-traces-YYYY.MM` - Pipeline traces (rétention 30 jours)
     - `apim-logs-YYYY.MM.DD` - Application logs (rétention 7 jours)
     - `apim-metrics-*` - Métriques (rétention 14 jours)
     - `apim-analytics-{tenant}` - Analytics API Gateway par tenant

2. **Intégration Control-Plane API → OpenSearch**
   - OpenSearchService dans `services/opensearch_service.py`
   - Indexation des PipelineTrace à chaque étape
   - Mise à jour du status en temps réel
   - Recherche full-text sur commit messages, erreurs

3. **FluentBit** (Log Shipping)
   - DaemonSet sur EKS
   - Parse logs JSON de tous les pods
   - Enrichissement: tenant_id, api_name, trace_id
   - Output vers OpenSearch
   - Helm: `fluent/fluent-bit`

4. **Prometheus + Remote Write** (Metrics)
   - Prometheus pour collecte locale
   - Remote Write vers OpenSearch (via Prometheus Exporter)
   - Métriques: latency, error_rate, requests/sec
   - Alerting: AlertManager → OpenSearch → Slack

5. **OpenSearch Dashboards** (Visualization)
   - URL: https://opensearch.apim.cab-i.com/_dashboards
   - Dashboards prédéfinis:
     - **Pipeline Overview**: Success rate, avg duration, errors/hour
     - **Deployment History**: Timeline par tenant/API
     - **Error Analysis**: Top errors, traces associées
     - **Commit Activity**: Heatmap GitLab pushes
   - Anomaly Detection: ML built-in pour spike detection

6. **Control-Plane UI - Page Monitoring** (✅ Déjà implémentée)
   - Lecture depuis OpenSearch au lieu de mémoire
   - Timeline interactive par trace
   - Filtres: tenant, status, date range
   - Export CSV des traces

7. **API Traces Endpoints** (à mettre à jour)
   ```python
   # Actuellement: in-memory store (TraceStore)
   # Cible: OpenSearch queries

   GET /v1/traces                    # OpenSearch query
   GET /v1/traces/{trace_id}         # OpenSearch get
   GET /v1/traces/stats              # OpenSearch aggregations
   GET /v1/traces/search             # Full-text search (nouveau)
   ```

8. **Index Templates & ILM**
   ```json
   {
     "index_patterns": ["apim-traces-*"],
     "template": {
       "settings": {
         "number_of_shards": 1,
         "number_of_replicas": 0
       },
       "mappings": {
         "properties": {
           "trace_id": { "type": "keyword" },
           "git_commit_message": { "type": "text" },
           "git_author": { "type": "keyword" },
           "tenant_id": { "type": "keyword" },
           "status": { "type": "keyword" },
           "created_at": { "type": "date" },
           "total_duration_ms": { "type": "integer" }
         }
       }
     }
   }
   ```

9. **Alerting Rules**
   - Pipeline failed > 3 fois/heure → Slack #apim-alerts
   - Duration P95 > 30s → Warning
   - AWX job timeout → Critical
   - Kafka consumer lag > 100 → Warning

**Avantages OpenSearch vs in-memory**:
| Aspect | In-Memory (actuel) | OpenSearch (cible) |
|--------|-------------------|-------------------|
| Persistance | ❌ Perdu au restart | ✅ Persistent |
| Recherche | ❌ Basique | ✅ Full-text, agrégations |
| Rétention | ❌ Limitée (500 traces) | ✅ Configurable (30 jours+) |
| Scalabilité | ❌ Single node | ✅ Cluster possible |
| Dashboards | ❌ UI custom uniquement | ✅ OpenSearch Dashboards |
| Coût | ✅ Gratuit | ⚠️ ~$35/mois |

**URLs Observabilité**:
| Service | URL |
|---------|-----|
| OpenSearch Dashboards | https://opensearch.apim.cab-i.com/_dashboards |
| Control-Plane Monitoring | https://devops.apim.cab-i.com/monitoring |
| Prometheus (interne) | prometheus.apim-system.svc.cluster.local:9090 |

#### Phase 4.5 : Jenkins Orchestration Layer (Priorité Haute - Enterprise)

**Objectif**: Intégrer Jenkins comme couche d'orchestration auditable entre Kafka et AWX pour une vision entreprise avec traçabilité complète, approval gates et reporting.

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                      JENKINS ORCHESTRATION LAYER                                      │
│                                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────────────┐    │
│   │                         ARCHITECTURE ENTREPRISE                              │    │
│   │                                                                              │    │
│   │   ┌──────────────┐                                                          │    │
│   │   │     GUI      │  ← UI Métier (produit API, tenant, accès)               │    │
│   │   └──────┬───────┘                                                          │    │
│   │          │ REST                                                              │    │
│   │   ┌──────▼────────┐                                                         │    │
│   │   │ Backend Python│  ← règles, validations, RBAC                           │    │
│   │   └──────┬────────┘                                                         │    │
│   │          │ EVENT (intent)                                                    │    │
│   │   ┌──────▼────────┐                                                         │    │
│   │   │     Kafka     │  ← source d'événements                                  │    │
│   │   └──────┬────────┘                                                         │    │
│   │          │ subscribe                                                         │    │
│   │   ┌──────▼────────┐                                                         │    │
│   │   │    Jenkins    │  ← ORCHESTRATEUR AUDITABLE                              │    │
│   │   │               │     • Pipeline as Code (Jenkinsfile)                    │    │
│   │   │               │     • Approval Gates                                     │    │
│   │   │               │     • Audit Trail complet                               │    │
│   │   │               │     • Parallel execution                                │    │
│   │   │               │     • Retry & rollback                                  │    │
│   │   └──────┬────────┘                                                         │    │
│   │          │ trigger                                                           │    │
│   │   ┌──────▼────────┐                                                         │    │
│   │   │      AWX      │  ← EXECUTION infra / gateway                            │    │
│   │   └───────────────┘                                                         │    │
│   │                                                                              │    │
│   └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                       │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**Avantages Jenkins comme Orchestrateur**:

| Aspect | Sans Jenkins (Kafka→AWX direct) | Avec Jenkins |
|--------|--------------------------------|--------------|
| **Auditabilité** | Logs dispersés | Console centralisée, Blue Ocean UI |
| **Approval Gates** | ❌ Pas de gates | ✅ `input` steps, RBAC approvers |
| **Retry/Rollback** | ❌ Manuel | ✅ Stage retry, automatic rollback |
| **Parallélisme** | ❌ Séquentiel | ✅ `parallel` stages |
| **Notification** | ❌ Custom | ✅ Native Slack/Email/Teams |
| **Compliance** | ❌ Logs Kafka | ✅ Build artifacts, audit trail |
| **Pipeline as Code** | ❌ Config AWX | ✅ Jenkinsfile versionné Git |

**Architecture Détaillée**:

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                        JENKINS + KAFKA + AWX FLOW                                     │
│                                                                                       │
│  ┌──────────┐       ┌──────────┐       ┌──────────┐       ┌──────────┐              │
│  │ Control  │       │  Kafka   │       │ Jenkins  │       │   AWX    │              │
│  │  Plane   │       │          │       │          │       │          │              │
│  └────┬─────┘       └────┬─────┘       └────┬─────┘       └────┬─────┘              │
│       │                  │                  │                  │                     │
│       │  POST /deploy    │                  │                  │                     │
│       │─────────────────▶│                  │                  │                     │
│       │                  │ api.lifecycle.   │                  │                     │
│       │                  │ events           │                  │                     │
│       │                  │─────────────────▶│                  │                     │
│       │                  │                  │ Trigger Pipeline │                     │
│       │                  │                  │─────────────────▶│                     │
│       │                  │                  │                  │                     │
│       │                  │                  │ ┌──────────────┐ │                     │
│       │                  │                  │ │ Jenkinsfile  │ │                     │
│       │                  │                  │ │              │ │                     │
│       │                  │                  │ │ 1. Validate  │ │                     │
│       │                  │                  │ │ 2. Approval? │ │                     │
│       │                  │                  │ │ 3. AWX Job   │─┼──▶ Launch Job      │
│       │                  │                  │ │ 4. Verify    │ │                     │
│       │                  │                  │ │ 5. Notify    │ │                     │
│       │                  │                  │ └──────────────┘ │                     │
│       │                  │                  │                  │                     │
│       │                  │                  │◀─────────────────│ Callback            │
│       │◀─────────────────│◀─────────────────│ Status Update    │                     │
│       │   Kafka event    │   Build Status   │                  │                     │
│                                                                                       │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**Déploiement Jenkins sur EKS**:

```yaml
# jenkins/values.yaml (Helm)
controller:
  image: jenkins/jenkins
  tag: lts-jdk17
  resources:
    requests:
      cpu: "1"
      memory: "2Gi"
    limits:
      cpu: "2"
      memory: "4Gi"

  # Plugins essentiels
  installPlugins:
    - kubernetes:latest
    - workflow-aggregator:latest
    - blueocean:latest
    - kafka-logs:latest
    - pipeline-stage-view:latest
    - slack:latest
    - ansible:latest
    - credentials-binding:latest
    - git:latest
    - job-dsl:latest
    - configuration-as-code:latest

  # JCasC - Configuration as Code
  JCasC:
    configScripts:
      security: |
        jenkins:
          securityRealm:
            oic:
              clientId: "jenkins"
              clientSecret: "${KEYCLOAK_CLIENT_SECRET}"
              authorizationServerUrl: "https://auth.apim.cab-i.com/realms/apim"
          authorizationStrategy:
            roleBased:
              roles:
                global:
                  - name: "admin"
                    permissions:
                      - "Overall/Administer"
                    entries:
                      - group: "cpi-admin"
                  - name: "deployer"
                    permissions:
                      - "Job/Build"
                      - "Job/Read"
                    entries:
                      - group: "devops"
                      - group: "tenant-admin"

agent:
  # Agents Kubernetes dynamiques
  podTemplates:
    - name: "apim-agent"
      label: "apim-agent"
      containers:
        - name: "python"
          image: "python:3.11"
          command: "sleep infinity"
        - name: "awx-cli"
          image: "quay.io/ansible/awx-cli:latest"
          command: "sleep infinity"

persistence:
  enabled: true
  size: 20Gi
  storageClass: gp3

ingress:
  enabled: true
  hostName: jenkins.apim.cab-i.com
  tls:
    - secretName: jenkins-tls
      hosts:
        - jenkins.apim.cab-i.com
```

**Kafka Consumer → Jenkins Trigger**:

```python
# jenkins-trigger-service/main.py
from kafka import KafkaConsumer
import requests
import json

JENKINS_URL = "https://jenkins.apim.cab-i.com"
JENKINS_TOKEN = os.getenv("JENKINS_API_TOKEN")

consumer = KafkaConsumer(
    'api.lifecycle.events',
    bootstrap_servers=['redpanda.apim-system.svc.cluster.local:9092'],
    group_id='jenkins-trigger',
    value_deserializer=lambda m: json.loads(m.decode('utf-8'))
)

# Mapping event_type → Jenkins job
JOB_MAPPING = {
    "deploy-request": "APIM/deploy-api",
    "promote-request": "APIM/promote-api",
    "rollback-request": "APIM/rollback-api",
    "delete-request": "APIM/delete-api",
    "sync-request": "APIM/sync-gateway"
}

for message in consumer:
    event = message.value
    event_type = event.get("event_type")

    if event_type in JOB_MAPPING:
        job_name = JOB_MAPPING[event_type]

        # Trigger Jenkins Pipeline
        response = requests.post(
            f"{JENKINS_URL}/job/{job_name}/buildWithParameters",
            auth=("apim-service", JENKINS_TOKEN),
            data={
                "TENANT_ID": event.get("tenant_id"),
                "API_NAME": event.get("api_name"),
                "API_VERSION": event.get("api_version"),
                "ENVIRONMENT": event.get("environment"),
                "TRACE_ID": event.get("trace_id"),
                "KAFKA_OFFSET": message.offset
            }
        )

        print(f"Triggered {job_name}: {response.status_code}")
```

**Jenkinsfile - Deploy API Pipeline**:

```groovy
// jenkins/pipelines/deploy-api/Jenkinsfile
pipeline {
    agent { label 'apim-agent' }

    parameters {
        string(name: 'TENANT_ID', description: 'Tenant ID')
        string(name: 'API_NAME', description: 'API Name')
        string(name: 'API_VERSION', description: 'API Version')
        string(name: 'ENVIRONMENT', description: 'Target Environment')
        string(name: 'TRACE_ID', description: 'Trace ID for correlation')
    }

    environment {
        AWX_HOST = 'https://awx.apim.cab-i.com'
        AWX_TOKEN = credentials('awx-api-token')
        KAFKA_BOOTSTRAP = 'redpanda.apim-system.svc.cluster.local:9092'
        SLACK_CHANNEL = '#apim-deployments'
    }

    options {
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '50'))
        timestamps()
        disableConcurrentBuilds(abortPrevious: true)
    }

    stages {
        stage('Validate') {
            steps {
                script {
                    echo "Validating deployment request..."

                    // Vérifier que l'API existe dans GitLab
                    def apiSpec = sh(
                        script: """
                            curl -s "https://api.apim.cab-i.com/v1/tenants/${TENANT_ID}/apis/${API_NAME}" \
                                -H "Authorization: Bearer ${API_TOKEN}"
                        """,
                        returnStdout: true
                    ).trim()

                    if (!apiSpec) {
                        error "API ${API_NAME} not found for tenant ${TENANT_ID}"
                    }

                    // Publier event Kafka: validation-passed
                    kafkaPublish(
                        topic: 'pipeline.events',
                        message: [
                            trace_id: params.TRACE_ID,
                            stage: 'validate',
                            status: 'success',
                            timestamp: new Date().toISOString()
                        ]
                    )
                }
            }
        }

        stage('Approval Gate') {
            when {
                expression { params.ENVIRONMENT == 'prod' }
            }
            steps {
                script {
                    slackSend(
                        channel: SLACK_CHANNEL,
                        color: 'warning',
                        message: """
                            :warning: *Approval Required*
                            API: ${params.API_NAME} v${params.API_VERSION}
                            Tenant: ${params.TENANT_ID}
                            Environment: ${params.ENVIRONMENT}
                            <${BUILD_URL}|Approve/Reject>
                        """
                    )

                    timeout(time: 4, unit: 'HOURS') {
                        input(
                            message: "Deploy ${params.API_NAME} to ${params.ENVIRONMENT}?",
                            ok: 'Deploy',
                            submitter: 'cpi-admin,tenant-admin',
                            submitterParameter: 'APPROVED_BY'
                        )
                    }

                    echo "Approved by: ${env.APPROVED_BY}"
                }
            }
        }

        stage('Deploy via AWX') {
            steps {
                script {
                    echo "Triggering AWX job..."

                    def awxJobId = sh(
                        script: """
                            awx job_templates launch 'deploy-api-gateway' \
                                --extra-vars '{
                                    "tenant_id": "${params.TENANT_ID}",
                                    "api_name": "${params.API_NAME}",
                                    "api_version": "${params.API_VERSION}",
                                    "environment": "${params.ENVIRONMENT}",
                                    "trace_id": "${params.TRACE_ID}"
                                }' \
                                --monitor \
                                --format json | jq -r '.id'
                        """,
                        returnStdout: true
                    ).trim()

                    env.AWX_JOB_ID = awxJobId
                    echo "AWX Job ID: ${awxJobId}"
                }
            }
        }

        stage('Verify Deployment') {
            steps {
                script {
                    // Attendre que l'API soit accessible
                    retry(5) {
                        sleep(time: 10, unit: 'SECONDS')

                        def healthCheck = sh(
                            script: """
                                curl -s -o /dev/null -w '%{http_code}' \
                                    "https://gateway.${params.ENVIRONMENT}.apim.cab-i.com/${params.TENANT_ID}/${params.API_NAME}/health"
                            """,
                            returnStdout: true
                        ).trim()

                        if (healthCheck != '200') {
                            error "Health check failed: ${healthCheck}"
                        }
                    }

                    echo "Deployment verified successfully"
                }
            }
        }

        stage('Smoke Tests') {
            steps {
                script {
                    echo "Running smoke tests..."

                    sh """
                        python3 -m pytest tests/smoke/ \
                            --api-url="https://gateway.${params.ENVIRONMENT}.apim.cab-i.com/${params.TENANT_ID}/${params.API_NAME}" \
                            --junitxml=smoke-results.xml
                    """
                }
            }
            post {
                always {
                    junit 'smoke-results.xml'
                }
            }
        }
    }

    post {
        success {
            script {
                kafkaPublish(
                    topic: 'deployment.events',
                    message: [
                        trace_id: params.TRACE_ID,
                        status: 'success',
                        awx_job_id: env.AWX_JOB_ID,
                        jenkins_build: env.BUILD_NUMBER,
                        duration_ms: currentBuild.duration,
                        timestamp: new Date().toISOString()
                    ]
                )

                slackSend(
                    channel: SLACK_CHANNEL,
                    color: 'good',
                    message: """
                        :white_check_mark: *Deployment Successful*
                        API: ${params.API_NAME} v${params.API_VERSION}
                        Tenant: ${params.TENANT_ID}
                        Environment: ${params.ENVIRONMENT}
                        Duration: ${currentBuild.durationString}
                        <${BUILD_URL}|View Build>
                    """
                )
            }
        }

        failure {
            script {
                kafkaPublish(
                    topic: 'deployment.events',
                    message: [
                        trace_id: params.TRACE_ID,
                        status: 'failed',
                        error: currentBuild.description,
                        jenkins_build: env.BUILD_NUMBER,
                        timestamp: new Date().toISOString()
                    ]
                )

                slackSend(
                    channel: SLACK_CHANNEL,
                    color: 'danger',
                    message: """
                        :x: *Deployment Failed*
                        API: ${params.API_NAME} v${params.API_VERSION}
                        Tenant: ${params.TENANT_ID}
                        Stage: ${currentBuild.currentResult}
                        <${BUILD_URL}console|View Logs>
                    """
                )
            }
        }

        aborted {
            script {
                slackSend(
                    channel: SLACK_CHANNEL,
                    color: 'warning',
                    message: ":no_entry: *Deployment Aborted*: ${params.API_NAME}"
                )
            }
        }
    }
}
```

**Jenkinsfile - Rollback Pipeline**:

```groovy
// jenkins/pipelines/rollback-api/Jenkinsfile
pipeline {
    agent { label 'apim-agent' }

    parameters {
        string(name: 'TENANT_ID', description: 'Tenant ID')
        string(name: 'API_NAME', description: 'API Name')
        string(name: 'TARGET_VERSION', description: 'Version to rollback to')
        string(name: 'ENVIRONMENT', description: 'Environment')
        booleanParam(name: 'EMERGENCY', defaultValue: false, description: 'Skip approval for emergency')
    }

    stages {
        stage('Identify Previous Version') {
            steps {
                script {
                    if (!params.TARGET_VERSION) {
                        // Récupérer la version précédente depuis GitLab
                        env.ROLLBACK_VERSION = sh(
                            script: """
                                git log --oneline -2 apis/${params.TENANT_ID}/${params.API_NAME}/openapi.yaml \
                                    | tail -1 | awk '{print \$1}'
                            """,
                            returnStdout: true
                        ).trim()
                    } else {
                        env.ROLLBACK_VERSION = params.TARGET_VERSION
                    }
                    echo "Rolling back to version: ${env.ROLLBACK_VERSION}"
                }
            }
        }

        stage('Emergency Approval') {
            when {
                expression { !params.EMERGENCY }
            }
            steps {
                timeout(time: 15, unit: 'MINUTES') {
                    input(
                        message: "Confirm rollback of ${params.API_NAME} to ${env.ROLLBACK_VERSION}?",
                        ok: 'Rollback Now'
                    )
                }
            }
        }

        stage('Execute Rollback') {
            steps {
                script {
                    sh """
                        awx job_templates launch 'rollback-api-gateway' \
                            --extra-vars '{
                                "tenant_id": "${params.TENANT_ID}",
                                "api_name": "${params.API_NAME}",
                                "target_version": "${env.ROLLBACK_VERSION}",
                                "environment": "${params.ENVIRONMENT}"
                            }' \
                            --monitor
                    """
                }
            }
        }

        stage('Verify Rollback') {
            steps {
                script {
                    // Health check après rollback
                    retry(3) {
                        sleep 5
                        sh """
                            curl -f "https://gateway.${params.ENVIRONMENT}.apim.cab-i.com/${params.TENANT_ID}/${params.API_NAME}/health"
                        """
                    }
                }
            }
        }
    }

    post {
        always {
            script {
                // Créer un incident ticket si rollback
                sh """
                    curl -X POST "https://api.apim.cab-i.com/v1/incidents" \
                        -H "Content-Type: application/json" \
                        -d '{
                            "type": "rollback",
                            "api": "${params.API_NAME}",
                            "tenant": "${params.TENANT_ID}",
                            "from_version": "current",
                            "to_version": "${env.ROLLBACK_VERSION}",
                            "emergency": ${params.EMERGENCY},
                            "jenkins_build": "${BUILD_URL}"
                        }'
                """
            }
        }
    }
}
```

**Jenkins Shared Library** (pour réutilisation):

```groovy
// vars/kafkaPublish.groovy
def call(Map config) {
    def message = groovy.json.JsonOutput.toJson(config.message)

    sh """
        echo '${message}' | kafka-console-producer.sh \
            --broker-list ${env.KAFKA_BOOTSTRAP} \
            --topic ${config.topic}
    """
}

// vars/awxLaunch.groovy
def call(String jobTemplate, Map extraVars) {
    def varsJson = groovy.json.JsonOutput.toJson(extraVars)

    return sh(
        script: """
            awx job_templates launch '${jobTemplate}' \
                --extra-vars '${varsJson}' \
                --monitor \
                --format json
        """,
        returnStdout: true
    )
}

// vars/notifyDeployment.groovy
def call(String status, Map details) {
    def color = status == 'success' ? 'good' : 'danger'
    def emoji = status == 'success' ? ':white_check_mark:' : ':x:'

    slackSend(
        channel: '#apim-deployments',
        color: color,
        message: """
            ${emoji} *Deployment ${status.capitalize()}*
            API: ${details.api_name}
            Tenant: ${details.tenant_id}
            Environment: ${details.environment}
            <${BUILD_URL}|View Build>
        """
    )
}
```

**Dashboard Jenkins - Métriques**:

| Métrique | Description | Objectif |
|----------|-------------|----------|
| **Deployment Success Rate** | % pipelines réussis | > 95% |
| **Mean Time to Deploy (MTTD)** | Durée moyenne pipeline | < 10 min |
| **Approval Wait Time** | Temps d'attente approbation | < 4h |
| **Rollback Frequency** | Nb rollbacks/semaine | < 2 |
| **Pipeline Queue Time** | Temps en attente | < 5 min |

**Checklist Phase 4.5**:
- [ ] Jenkins déployé sur EKS (Helm jenkins/jenkins)
- [ ] Configuration JCasC (Jenkins Configuration as Code)
- [ ] Intégration Keycloak SSO (OIDC)
- [ ] Service Kafka Consumer → Jenkins Trigger
- [ ] Jenkinsfile `deploy-api` avec approval gates
- [ ] Jenkinsfile `rollback-api` avec emergency bypass
- [ ] Jenkinsfile `promote-api` pour promotion entre envs
- [ ] Jenkinsfile `delete-api` avec confirmation
- [ ] Shared Library (kafkaPublish, awxLaunch, notifyDeployment)
- [ ] Blue Ocean UI accessible
- [ ] Slack notifications configurées
- [ ] Dashboard métriques Jenkins
- [ ] Credentials AWX/Kafka/Keycloak dans Jenkins Credentials Store
- [ ] Backup Jenkins config (PVC + S3)

**URLs Jenkins**:
| Service | URL |
|---------|-----|
| Jenkins UI | https://jenkins.apim.cab-i.com |
| Blue Ocean | https://jenkins.apim.cab-i.com/blue |
| API | https://jenkins.apim.cab-i.com/api/json |

#### Phase 5 : Multi-Environment (Priorité Basse)
1. **Environnement STAGING**
   - Promotion DEV → STAGING
   - Portal publication

2. **OpenSearch Analytics**
   - Global Policy par tenant
   - Index pattern: {env}-{tenant}-analytics

#### Phase 6 : Tenant Démo & Documentation (Beta Testing)

**Objectif**: Créer un tenant de démonstration avec des utilisateurs beta testeurs et générer la documentation utilisateur (MkDocs).

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           BETA TESTING - TENANT DÉMO                                 │
│                                                                                      │
│                        ┌──────────────────────────┐                                 │
│                        │       KEYCLOAK           │                                 │
│                        │   Realm: apim-platform   │                                 │
│                        │                          │                                 │
│                        │  Clients:                │                                 │
│                        │  ├── control-plane-ui    │                                 │
│                        │  └── control-plane-api   │                                 │
│                        └────────────┬─────────────┘                                 │
│                                     │                                                │
│                        ┌────────────┴────────────┐                                  │
│                        │                         │                                  │
│                        ▼                         ▼                                  │
│             ┌─────────────────┐       ┌─────────────────┐                          │
│             │   UI DevOps     │       │ Control-Plane   │                          │
│             │   (React)       │       │     API         │                          │
│             │                 │       │   (FastAPI)     │                          │
│             │ devops.apim...  │       │  api.apim...    │                          │
│             └─────────────────┘       └─────────────────┘                          │
│                        │                                                            │
│                        │                                                            │
│                    ┌───┴───────────────────────┐                                   │
│                    │     TENANT: tenant-demo   │                                   │
│                    │                           │                                   │
│                    │  Users:                   │                                   │
│                    │  ├── demo-cpi@cab-i.com   │  (CPI - Full access)             │
│                    │  └── demo-devops@cab-i.com│  (DevOps - Deploy only)          │
│                    │                           │                                   │
│                    │  APIs démo:               │                                   │
│                    │  ├── petstore-api         │                                   │
│                    │  └── weather-api          │                                   │
│                    └───────────────────────────┘                                   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

> **Note**: Le Developer Portal sera développé en Phase 8 comme portal custom React.

1. **Créer le Tenant Démo dans GitOps** 🔲

   ```yaml
   # iam/tenants.yaml - Ajout tenant-demo
   tenants:
     - id: tenant-demo
       displayName: "Demo Tenant (Beta Testing)"
       description: "Tenant de démonstration pour les beta testeurs"
       status: active
       createdAt: "2024-12-21T00:00:00Z"

       owner:
         email: "demo-cpi@cab-i.com"
         name: "Demo CPI Admin"

       quotas:
         maxApis: 10
         maxApplications: 5
         maxRequestsPerDay: 10000

       environments:
         - dev

       members:
         cpi:
           - email: "demo-cpi@cab-i.com"
             name: "Demo CPI Admin"
             addedAt: "2024-12-21T00:00:00Z"
             addedBy: "admin@apim.local"

         devops:
           - email: "demo-devops@cab-i.com"
             name: "Demo DevOps"
             addedAt: "2024-12-21T00:00:00Z"
             addedBy: "admin@apim.local"

         viewers: []
   ```

2. **Créer les Utilisateurs Beta dans Keycloak** 🔲

   | User | Email | Rôle | Accès |
   |------|-------|------|-------|
   | Demo CPI | demo-cpi@cab-i.com | `tenant-admin` | UI DevOps (full CRUD) |
   | Demo DevOps | demo-devops@cab-i.com | `devops` | UI DevOps (deploy only) |

   **Configuration Keycloak**:
   ```yaml
   # Groupe: tenant-demo
   users:
     - username: demo-cpi
       email: demo-cpi@cab-i.com
       firstName: Demo
       lastName: CPI Admin
       enabled: true
       credentials:
         - type: password
           value: "DemoCPI2024!"
           temporary: false
       groups:
         - tenant-demo
       realmRoles:
         - tenant-admin
       attributes:
         tenant_id: ["tenant-demo"]

     - username: demo-devops
       email: demo-devops@cab-i.com
       firstName: Demo
       lastName: DevOps
       enabled: true
       credentials:
         - type: password
           value: "DemoDevOps2024!"
           temporary: false
       groups:
         - tenant-demo
       realmRoles:
         - devops
       attributes:
         tenant_id: ["tenant-demo"]
   ```

3. **APIs Démo Pré-déployées** 🔲

   Créer des APIs de démonstration dans le tenant-demo pour que les beta testeurs puissent les explorer.

   ```
   apim-gitops/
   └── tenants/
       └── tenant-demo/
           └── apis/
               ├── petstore-api/
               │   ├── api.yaml
               │   ├── openapi.yaml         # Swagger Petstore
               │   └── environments/
               │       └── dev.yaml
               │
               └── weather-api/
                   ├── api.yaml
                   ├── openapi.yaml         # OpenWeatherMap wrapper
                   └── environments/
                       └── dev.yaml
   ```

   **Exemple petstore-api/api.yaml**:
   ```yaml
   apiVersion: apim.cab-i.com/v1
   kind: API
   metadata:
     name: petstore-api
     tenant: tenant-demo
   spec:
     displayName: "Petstore API (Demo)"
     version: "1.0.0"
     description: "API de démonstration basée sur Swagger Petstore"
     backend:
       url: "https://petstore.swagger.io/v2"
     security:
       type: apiKey
       apiKeyHeader: "api_key"
     policies:
       - rateLimit:
           requests: 100
           period: minute
   ```

4. **Workflow Beta Testeur** 🔲

   ```
   ┌─────────────────────────────────────────────────────────────────────────────────────┐
   │                        PARCOURS BETA TESTEUR                                         │
   │                                                                                      │
   │  1. CONNEXION                                                                        │
   │     ┌─────────────────────────────────────────────────────────────────────────────┐ │
   │     │  Accès: https://devops.apim.cab-i.com                                       │ │
   │     │  → Redirect vers Keycloak                                                   │ │
   │     │  → Login: demo-cpi@cab-i.com / DemoCPI2024!                                 │ │
   │     │  → Redirect vers UI DevOps (JWT avec tenant_id=tenant-demo)                │ │
   │     └─────────────────────────────────────────────────────────────────────────────┘ │
   │                                                                                      │
   │  2. UI DEVOPS - GESTION APIs                                                        │
   │     ┌─────────────────────────────────────────────────────────────────────────────┐ │
   │     │  • Voir les APIs du tenant-demo (petstore-api, weather-api)                │ │
   │     │  • Créer une nouvelle API de test                                          │ │
   │     │  • Déployer sur l'environnement DEV                                        │ │
   │     │  • Voir les traces du pipeline (GitLab → Kafka → AWX → Gateway)           │ │
   │     └─────────────────────────────────────────────────────────────────────────────┘ │
   │                                                                                      │
   └─────────────────────────────────────────────────────────────────────────────────────┘
   ```

   > **Note**: Le Developer Portal sera ajouté en Phase 8.

5. **Permissions par Rôle (UI DevOps)** 🔲

   | Action | CPI (demo-cpi) | DevOps (demo-devops) |
   |--------|----------------|----------------------|
   | Voir APIs tenant | ✅ | ✅ |
   | Créer/Modifier API | ✅ | ✅ |
   | Supprimer API | ✅ | ❌ |
   | Déployer API | ✅ | ✅ |
   | Gérer membres tenant | ✅ | ❌ |
   | Voir traces pipeline | ✅ | ✅ |

6. **Checklist Déploiement Phase 6** 🔲

   - [ ] Créer tenant-demo dans `iam/tenants.yaml` + commit GitLab
   - [ ] Sync IAM → Keycloak (créer groupe + users)
   - [ ] Créer APIs démo (petstore, weather) dans GitOps
   - [ ] Déployer APIs démo sur Gateway DEV
   - [ ] Tester parcours complet avec demo-cpi
   - [ ] Tester parcours complet avec demo-devops
   - [ ] Documenter accès beta testeurs

7. **Credentials Beta Testeurs**

   | User | URL | Login | Password |
   |------|-----|-------|----------|
   | Demo CPI | https://devops.apim.cab-i.com | demo-cpi@cab-i.com | DemoCPI2024! |
   | Demo DevOps | https://devops.apim.cab-i.com | demo-devops@cab-i.com | DemoDevOps2024! |

   > **Note**: Les credentials seront stockés dans Vault après validation beta.

8. **Documentation Utilisateur (MkDocs)** 🔲

   Générer une documentation complète pour les beta testeurs et futurs utilisateurs de la plateforme.

   **Structure Documentation**:
   ```
   docs/
   ├── user-guide/
   │   ├── README.md                    # Index documentation
   │   ├── 01-getting-started.md        # Premiers pas
   │   ├── 02-ui-devops-guide.md        # Guide UI DevOps
   │   ├── 03-developer-portal-guide.md # Guide Developer Portal
   │   ├── 04-api-lifecycle.md          # Cycle de vie d'une API
   │   ├── 05-rbac-roles.md             # Rôles et permissions
   │   └── 06-troubleshooting.md        # Dépannage
   │
   ├── tutorials/
   │   ├── create-first-api.md          # Tutoriel: Créer sa première API
   │   ├── deploy-api.md                # Tutoriel: Déployer une API
   │   ├── consume-api.md               # Tutoriel: Consommer une API
   │   └── manage-team.md               # Tutoriel: Gérer son équipe
   │
   └── images/
       ├── login-flow.png
       ├── ui-dashboard.png
       └── portal-subscribe.png
   ```

   **01-getting-started.md**:
   ```markdown
   # Guide de Démarrage Rapide

   ## Accès à la Plateforme APIM

   La plateforme APIM CAB-I dispose d'une interface principale:

   | Interface | URL | Description |
   |-----------|-----|-------------|
   | UI DevOps | https://devops.apim.cab-i.com | Gestion des APIs, déploiements, monitoring |

   > **Note**: Le Developer Portal custom sera disponible en Phase 8.

   ## Connexion (SSO Keycloak)

   Toutes les interfaces utilisent **Keycloak** pour l'authentification.
   Une seule connexion vous donne accès à toutes les applications.

   ### Étapes de connexion:
   1. Accédez à l'URL de l'interface souhaitée
   2. Vous êtes redirigé vers la page de connexion Keycloak
   3. Entrez votre email et mot de passe
   4. Vous êtes redirigé vers l'application

   ### Rôles Utilisateurs

   | Rôle | Description | Permissions |
   |------|-------------|-------------|
   | **CPI (Tenant Admin)** | Administrateur du tenant | CRUD complet sur APIs, Apps, Users |
   | **DevOps** | Développeur/Opérateur | Créer/Modifier APIs, Déployer |
   | **Viewer** | Lecture seule | Consulter APIs et statistiques |

   ## Votre Premier Déploiement

   1. **Connectez-vous** à l'UI DevOps
   2. **Créez une API** via le formulaire ou import OpenAPI
   3. **Déployez** sur l'environnement DEV
   4. **Vérifiez** le déploiement dans la page Monitoring
   5. **Testez** l'API via la Gateway
   ```

   **02-ui-devops-guide.md**:
   ```markdown
   # Guide UI DevOps

   ## Dashboard

   Le dashboard affiche une vue d'ensemble de votre tenant:
   - Nombre d'APIs
   - Déploiements récents
   - Statut des pipelines
   - Alertes en cours

   ## Gestion des APIs

   ### Créer une API
   1. Cliquez sur **+ Nouvelle API**
   2. Remplissez les informations:
      - Nom (unique dans le tenant)
      - Version
      - Description
      - Backend URL
   3. (Optionnel) Importez un fichier OpenAPI
   4. Cliquez sur **Créer**

   ### Déployer une API
   1. Sélectionnez l'API dans la liste
   2. Cliquez sur **Déployer**
   3. Choisissez l'environnement (DEV, STAGING, PROD)
   4. Confirmez le déploiement
   5. Suivez le pipeline dans l'onglet **Monitoring**

   ### Pipeline de Déploiement
   ```
   GitLab Commit → Kafka Event → AWX Job → Gateway Deploy
   ```
   Chaque étape est visible en temps réel dans la page Monitoring.

   ## Monitoring

   ### Timeline des Pipelines
   - Vue chronologique de tous les déploiements
   - Filtres par statut, API, environnement
   - Détail de chaque étape avec durée

   ### Statuts
   - 🟢 **Success**: Déploiement réussi
   - 🟡 **Pending**: En cours
   - 🔴 **Failed**: Échec (cliquez pour voir l'erreur)

   ## Gestion de l'Équipe (CPI uniquement)

   ### Ajouter un membre
   1. Allez dans **Paramètres > Équipe**
   2. Cliquez sur **+ Ajouter un membre**
   3. Entrez l'email et le nom
   4. Sélectionnez le rôle (CPI, DevOps, Viewer)
   5. Confirmez

   L'utilisateur recevra un accès automatiquement après synchronisation Keycloak.
   ```

   > **Note**: Le guide Developer Portal sera ajouté après Phase 8.

   **03-api-lifecycle.md**:
   ```markdown
   # Cycle de Vie d'une API

   ## États d'une API

   ```
   ┌─────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
   │  DRAFT  │ →  │   DEV    │ →  │ STAGING  │ →  │   PROD   │
   └─────────┘    └──────────┘    └──────────┘    └──────────┘
        │              │               │               │
        │              │               │               │
   Création       Déployé DEV     Promotion       Production
   dans Git       Tests internes   UAT            Live
   ```

   ## Workflow de Promotion

   1. **Développement (DEV)**
      - Créer l'API dans l'UI DevOps
      - Commit automatique dans GitLab
      - Déployer sur Gateway DEV
      - Tests d'intégration

   2. **Staging (STAGING)**
      - Promouvoir depuis DEV
      - Tests d'acceptation (UAT)
      - Validation métier

   3. **Production (PROD)**
      - Approbation requise
      - Déploiement Blue-Green
      - Monitoring renforcé

   ## Rollback

   En cas de problème:
   1. Allez dans **Monitoring > Historique**
   2. Sélectionnez une version précédente
   3. Cliquez sur **Rollback**
   4. Confirmez
   ```

   **Génération Automatique (MkDocs)**:
   ```yaml
   # mkdocs.yml
   site_name: APIM Platform - Documentation
   site_url: https://docs.apim.cab-i.com
   theme:
     name: material
     palette:
       primary: indigo
     features:
       - navigation.tabs
       - search.suggest

   nav:
     - Accueil: index.md
     - Guide Utilisateur:
       - Premiers Pas: user-guide/01-getting-started.md
       - UI DevOps: user-guide/02-ui-devops-guide.md
       - Cycle de Vie API: user-guide/03-api-lifecycle.md
       - Rôles & Permissions: user-guide/04-rbac-roles.md
       - Dépannage: user-guide/05-troubleshooting.md
     - Tutoriels:
       - Créer sa première API: tutorials/create-first-api.md
       - Déployer une API: tutorials/deploy-api.md
       - Gérer son équipe: tutorials/manage-team.md
     - API Reference: api-reference/

   plugins:
     - search
     - mkdocstrings  # Auto-génère doc depuis code Python
   ```

   **Déploiement Documentation**:
   - URL: https://docs.apim.cab-i.com
   - CI/CD: GitLab Pages ou S3 + CloudFront
   - Build: `mkdocs build`

   **Checklist Documentation**:
   - [ ] Écrire 01-getting-started.md
   - [ ] Écrire 02-ui-devops-guide.md avec screenshots
   - [ ] Écrire 03-api-lifecycle.md
   - [ ] Écrire 04-rbac-roles.md
   - [ ] Écrire 05-troubleshooting.md (FAQ)
   - [ ] Créer tutoriels pas-à-pas
   - [ ] Capturer screenshots des interfaces
   - [ ] Configurer MkDocs + thème Material
   - [ ] Déployer sur GitLab Pages
   - [ ] Ajouter lien "Documentation" dans UI DevOps

#### Phase 7 : Sécurité Opérationnelle (Batch Jobs)

**Objectif**: Mettre en place des jobs automatisés pour la sécurité opérationnelle : vérification des certificats, rotation des secrets, reporting d'utilisation, et scan de sécurité GitLab.

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         SECURITY OPERATIONS CENTER                                   │
│                                                                                      │
│   ┌──────────────────────────────────────────────────────────────────────────────┐  │
│   │                        4 JOBS DE SÉCURITÉ                                     │  │
│   │                                                                               │  │
│   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │  │
│   │  │ Certificate │  │   Secret    │  │   Usage     │  │   GitLab    │          │  │
│   │  │ Expiry      │  │   Rotation  │  │   Reporting │  │   Security  │          │  │
│   │  │ Check       │  │             │  │             │  │   Scan      │          │  │
│   │  │             │  │             │  │             │  │             │          │  │
│   │  │ Daily 6AM   │  │ Weekly Sun  │  │ Daily 1AM   │  │ On commit   │          │  │
│   │  │             │  │ Monthly 1st │  │ Weekly Mon  │  │ Daily 3AM   │          │  │
│   │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘          │  │
│   │                                                                               │  │
│   └──────────────────────────────────────────────────────────────────────────────┘  │
│                                      │                                               │
│                                      ▼                                               │
│   ┌──────────────────────────────────────────────────────────────────────────────┐  │
│   │                           ALERTING                                            │  │
│   │                                                                               │  │
│   │  Kafka → Email / Slack / Teams / PagerDuty → Grafana Dashboards              │  │
│   │                                                                               │  │
│   └──────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

1. **Job 1 : Vérification Expiration Certificats** 🔲

   **Sources vérifiées**:
   | Source | Type | Exemple |
   |--------|------|---------|
   | Kubernetes | TLS Secrets | Ingress certificates, mTLS |
   | Vault | PKI Certificates | API certs, Client certs |
   | External | Endpoints HTTPS | Backend URLs, Partner APIs |

   **Seuils d'alerte**:
   | Niveau | Jours restants | Action |
   |--------|----------------|--------|
   | 🔴 CRITICAL | < 7 jours | Email + Slack + PagerDuty |
   | 🟠 WARNING | < 30 jours | Email + Slack |
   | 🟡 INFO | < 60 jours | Slack |
   | 🟢 OK | > 60 jours | - |

   **CronJob**: Daily 6AM
   ```yaml
   apiVersion: batch/v1
   kind: CronJob
   metadata:
     name: certificate-checker
   spec:
     schedule: "0 6 * * *"
     jobTemplate:
       spec:
         template:
           spec:
             containers:
               - name: checker
                 image: apim-security-jobs:latest
                 command: ["python", "-m", "src.jobs.certificate_checker"]
   ```

2. **Job 2 : Rotation Automatique des Secrets** 🔲

   **Policies de rotation**:
   | Type de Secret | Fréquence | Auto-Rotate | Notifier avant |
   |----------------|-----------|-------------|----------------|
   | API Keys | 30 jours | ✅ Oui | 7 jours |
   | OAuth Client Secrets | 90 jours | ✅ Oui | 14 jours |
   | Database Passwords | 90 jours | ✅ Oui | 14 jours |
   | Service Accounts | 180 jours | ✅ Oui | 30 jours |
   | Encryption Keys | 365 jours | ❌ Manual | 60 jours |

   **Fonctionnalités**:
   - Génération de nouveaux secrets (alphanumeric, special chars)
   - Mise à jour dans Vault avec metadata (last_rotated, rotated_by)
   - Propagation vers Kubernetes Secrets et Keycloak Clients
   - Post-rotation actions (restart deployments si nécessaire)

   **CronJobs**:
   - Weekly: Sunday 2AM
   - Monthly (forced): 1st of month 3AM

3. **Job 3 : Reporting d'Utilisation par Tenant** 🔲

   **Métriques collectées**:
   | Catégorie | Métriques |
   |-----------|-----------|
   | API Calls | Total, Success, Failed, Error Rate |
   | Bandwidth | Inbound MB, Outbound MB, Total |
   | Latency | Avg, P50, P95, P99 |
   | Resources | Active APIs, Apps, Users |
   | Quota | Usage %, Exceeded |

   **Sources de données**:
   ```
   ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
   │   Prometheus    │   │   webMethods    │   │   PostgreSQL    │
   │   (Metrics)     │   │   Gateway       │   │   (Control      │
   │                 │   │   (Analytics)   │   │   Plane DB)     │
   └────────┬────────┘   └────────┬────────┘   └────────┬────────┘
            │                     │                     │
            └─────────────────────┼─────────────────────┘
                                  │
                                  ▼
                     ┌──────────────────────────┐
                     │   Usage Reporting Job    │
                     │                          │
                     │   Aggregation per Tenant │
                     │   PDF Generation         │
                     │   Email Distribution     │
                     └──────────────────────────┘
   ```

   **CronJobs**:
   - Daily: 1AM (rapport quotidien)
   - Weekly: Monday 2AM (rapport PDF hebdomadaire)

4. **Job 4 : Scan Sécurité GitLab** 🔲

   **Types de scan**:
   | Scan | Outil | Détection |
   |------|-------|-----------|
   | Secret Detection | Gitleaks | API Keys, Passwords, Tokens, Certs |
   | SAST | Semgrep | SQL Injection, XSS, Hardcoded creds |
   | Dependency Check | Trivy | CVE, Outdated packages |
   | License Compliance | pip-licenses | GPL/LGPL, Proprietary |

   **Règles Gitleaks** (`.gitleaks.toml`):
   - AWS Access Keys (`AKIA...`)
   - Generic API Keys
   - Passwords
   - Private Keys (RSA, EC, DSA)
   - JWT Tokens (`eyJ...`)
   - Vault Tokens (`hvs....`)
   - Database Connection Strings

   **GitLab CI/CD Integration**:
   ```yaml
   stages:
     - security-scan
     - validate
     - build

   secret-detection:
     stage: security-scan
     image: zricethezav/gitleaks:latest
     script:
       - gitleaks detect --source . --config .gitleaks.toml --exit-code 1
     rules:
       - if: $CI_PIPELINE_SOURCE == "push"
       - if: $CI_PIPELINE_SOURCE == "merge_request_event"

   security-gate:
     stage: security-scan
     script:
       - |
         if [ "$CRITICAL_SECRETS" -gt "0" ]; then
           echo "❌ BLOCKED: Secrets detected!"
           exit 1
         fi
   ```

   **CronJob**: Daily 3AM + On-commit (webhook)

5. **Service de Notification** 🔲

   | Niveau | Canaux |
   |--------|--------|
   | 🔴 CRITICAL | Email + Slack + PagerDuty |
   | 🟠 WARNING | Email + Slack |
   | 🟡 INFO | Slack |

   **Configuration**:
   ```yaml
   notifications:
     email:
       smtp_host: smtp.cab-i.com
       recipients:
         critical: ["security-team@cab-i.com"]
         warning: ["platform-admins@cab-i.com"]
     slack:
       webhook: vault:secret/data/notifications#slack_webhook
       channel: "#apim-alerts"
     pagerduty:
       routing_key: vault:secret/data/notifications#pagerduty_key
   ```

6. **Structure des Jobs** 🔲

   ```
   control-plane-api/
   └── src/
       └── jobs/
           ├── __init__.py
           ├── certificate_checker.py      # Job 1
           ├── secret_rotation.py          # Job 2
           ├── usage_reporting.py          # Job 3
           └── security_scanner.py         # Job 4

   charts/apim-platform/
   └── templates/
       └── security-jobs/
           ├── certificate-checker.yaml
           ├── secret-rotation.yaml
           ├── usage-reporting.yaml
           └── gitlab-security-scan.yaml
   ```

7. **Helm Values** 🔲

   ```yaml
   # values.yaml
   securityJobs:
     enabled: true
     image: apim-security-jobs:latest

     certificateChecker:
       schedule: "0 6 * * *"
       criticalDays: 7
       warningDays: 30

     secretRotation:
       weeklySchedule: "0 2 * * 0"
       monthlySchedule: "0 3 1 * *"
       policies:
         - name: api-keys
           frequency: 30d
           autoRotate: true

     usageReporting:
       dailySchedule: "0 1 * * *"
       weeklySchedule: "0 2 * * 1"
       generatePdf: true

     gitlabSecurityScan:
       schedule: "0 3 * * *"
       tools:
         - gitleaks
         - semgrep
         - trivy
   ```

8. **Checklist Déploiement Phase 7** 🔲

   - [ ] Créer image Docker `apim-security-jobs` avec Python + outils
   - [ ] Implémenter `certificate_checker.py`
   - [ ] Implémenter `secret_rotation.py` avec intégration Vault
   - [ ] Implémenter `usage_reporting.py` avec génération PDF
   - [ ] Implémenter `security_scanner.py` avec Gitleaks/Semgrep/Trivy
   - [ ] Créer `NotificationService` (Email/Slack/PagerDuty)
   - [ ] Ajouter CronJobs dans Helm chart
   - [ ] Configurer `.gitleaks.toml` dans repos GitLab
   - [ ] Ajouter stages security-scan dans `.gitlab-ci.yml`
   - [ ] Configurer alerting dans Grafana
   - [ ] Tester chaque job manuellement
   - [ ] Documenter les procédures de réponse aux alertes

9. **Monitoring des Jobs de Sécurité** 🔲

   **Architecture Observabilité Jobs**:
   ```
   ┌─────────────────────────────────────────────────────────────────────────────────────┐
   │                      SECURITY JOBS OBSERVABILITY                                     │
   │                                                                                      │
   │   ┌──────────────────┐                                                              │
   │   │  Security Jobs   │                                                              │
   │   │  (CronJobs K8s)  │                                                              │
   │   └────────┬─────────┘                                                              │
   │            │                                                                         │
   │            ├──────────────────┬──────────────────┬──────────────────┐               │
   │            ▼                  ▼                  ▼                  ▼               │
   │   ┌────────────────┐  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐   │
   │   │  Prometheus    │  │     Kafka      │  │   OpenSearch   │  │    Grafana     │   │
   │   │  (Metrics)     │  │   (Events)     │  │  (Historique)  │  │  (Dashboards)  │   │
   │   │                │  │                │  │                │  │                │   │
   │   │ job_success    │  │ security-job-  │  │ security-jobs- │  │ Security Jobs  │   │
   │   │ job_duration   │  │ results        │  │ YYYY.MM        │  │ Dashboard      │   │
   │   │ job_last_run   │  │                │  │                │  │                │   │
   │   └────────────────┘  └────────────────┘  └────────────────┘  └────────────────┘   │
   │            │                  │                  │                  │               │
   │            └──────────────────┴──────────────────┴──────────────────┘               │
   │                                      │                                               │
   │                                      ▼                                               │
   │                        ┌──────────────────────────┐                                 │
   │                        │      AlertManager        │                                 │
   │                        │  → Slack / PagerDuty     │                                 │
   │                        └──────────────────────────┘                                 │
   └─────────────────────────────────────────────────────────────────────────────────────┘
   ```

   **Métriques Prometheus exposées par chaque job**:
   ```python
   # src/jobs/base_job.py
   from prometheus_client import Counter, Histogram, Gauge, push_to_gateway

   class BaseSecurityJob:
       # Métriques communes à tous les jobs
       job_runs_total = Counter(
           'security_job_runs_total',
           'Total number of job executions',
           ['job_name', 'status']  # status: success, failure
       )

       job_duration_seconds = Histogram(
           'security_job_duration_seconds',
           'Job execution duration',
           ['job_name'],
           buckets=[1, 5, 10, 30, 60, 120, 300, 600]
       )

       job_last_run_timestamp = Gauge(
           'security_job_last_run_timestamp',
           'Timestamp of last job execution',
           ['job_name']
       )

       job_findings_total = Gauge(
           'security_job_findings_total',
           'Number of findings from last run',
           ['job_name', 'severity']  # severity: critical, warning, info
       )

       async def run_with_metrics(self):
           start_time = time.time()
           try:
               result = await self.run()
               self.job_runs_total.labels(job_name=self.name, status='success').inc()
               return result
           except Exception as e:
               self.job_runs_total.labels(job_name=self.name, status='failure').inc()
               raise
           finally:
               duration = time.time() - start_time
               self.job_duration_seconds.labels(job_name=self.name).observe(duration)
               self.job_last_run_timestamp.labels(job_name=self.name).set_to_current_time()
               # Push to Prometheus Pushgateway
               push_to_gateway('prometheus-pushgateway:9091', job=self.name, registry=REGISTRY)
   ```

   **Events Kafka** - Topic `security-job-results`:
   ```python
   # Publié à la fin de chaque job
   {
       "job_name": "certificate-checker",
       "run_id": "run-abc123",
       "started_at": "2024-12-21T06:00:00Z",
       "completed_at": "2024-12-21T06:00:45Z",
       "duration_seconds": 45,
       "status": "success",  # success | failure | partial
       "summary": {
           "total_checked": 15,
           "critical": 1,
           "warning": 3,
           "info": 2,
           "ok": 9
       },
       "findings": [
           {
               "type": "certificate_expiry",
               "severity": "critical",
               "resource": "ingress-nginx/tls-secret",
               "message": "Certificate expires in 5 days",
               "expires_at": "2024-12-26T00:00:00Z"
           }
       ],
       "alerts_sent": ["slack", "pagerduty"]
   }
   ```

   **Index OpenSearch** - `security-jobs-YYYY.MM`:
   ```json
   {
     "index_patterns": ["security-jobs-*"],
     "template": {
       "mappings": {
         "properties": {
           "job_name": { "type": "keyword" },
           "run_id": { "type": "keyword" },
           "status": { "type": "keyword" },
           "duration_seconds": { "type": "float" },
           "findings_count": { "type": "integer" },
           "findings": {
             "type": "nested",
             "properties": {
               "severity": { "type": "keyword" },
               "resource": { "type": "keyword" },
               "message": { "type": "text" }
             }
           },
           "@timestamp": { "type": "date" }
         }
       }
     }
   }
   ```

   **Alertes Prometheus (AlertManager)**:
   ```yaml
   # prometheus-rules.yaml
   groups:
     - name: security-jobs
       rules:
         # Alerte si un job n'a pas tourné depuis 2x son intervalle
         - alert: SecurityJobNotRunning
           expr: |
             time() - security_job_last_run_timestamp > 2 * 86400
           for: 5m
           labels:
             severity: warning
           annotations:
             summary: "Security job {{ $labels.job_name }} not running"
             description: "Job has not run for more than 2 days"

         # Alerte si un job échoue
         - alert: SecurityJobFailed
           expr: |
             increase(security_job_runs_total{status="failure"}[1h]) > 0
           for: 0m
           labels:
             severity: critical
           annotations:
             summary: "Security job {{ $labels.job_name }} failed"
             description: "Job execution failed in the last hour"

         # Alerte si findings critiques détectés
         - alert: SecurityCriticalFindings
           expr: |
             security_job_findings_total{severity="critical"} > 0
           for: 0m
           labels:
             severity: critical
           annotations:
             summary: "Critical security findings in {{ $labels.job_name }}"
             description: "{{ $value }} critical findings detected"

         # Alerte si job prend trop de temps
         - alert: SecurityJobSlow
           expr: |
             security_job_duration_seconds > 600
           for: 0m
           labels:
             severity: warning
           annotations:
             summary: "Security job {{ $labels.job_name }} slow"
             description: "Job took {{ $value }}s to complete"
   ```

   **Dashboard Grafana** - Security Jobs Overview:
   ```
   ┌─────────────────────────────────────────────────────────────────────────────┐
   │                    SECURITY JOBS DASHBOARD                                   │
   ├─────────────────────────────────────────────────────────────────────────────┤
   │                                                                              │
   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
   │  │ Cert Checker │  │ Secret Rot.  │  │ Usage Report │  │ GitLab Scan  │    │
   │  │   ✅ OK      │  │   ✅ OK      │  │   ✅ OK      │  │   ⚠️ WARN    │    │
   │  │ Last: 6:00   │  │ Last: Sun    │  │ Last: 1:00   │  │ Last: 3:00   │    │
   │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘    │
   │                                                                              │
   │  ┌─────────────────────────────────────────────────────────────────────┐    │
   │  │  Job Execution Timeline (last 7 days)                               │    │
   │  │  ═══════════════════════════════════════════════════════════════   │    │
   │  │  Cert:    ●  ●  ●  ●  ●  ●  ●                                      │    │
   │  │  Secret:        ●              ●                                    │    │
   │  │  Usage:   ●  ●  ●  ●  ●  ●  ●                                      │    │
   │  │  GitLab:  ●  ●  ●  ●  ●  ●  ●                                      │    │
   │  │          Mon Tue Wed Thu Fri Sat Sun                                │    │
   │  └─────────────────────────────────────────────────────────────────────┘    │
   │                                                                              │
   │  ┌────────────────────────────┐  ┌────────────────────────────────────┐    │
   │  │  Findings by Severity      │  │  Job Duration (P95)                │    │
   │  │                            │  │                                    │    │
   │  │  🔴 Critical: 1            │  │  Cert Checker:  45s               │    │
   │  │  🟠 Warning:  5            │  │  Secret Rot:    120s              │    │
   │  │  🟡 Info:     12           │  │  Usage Report:  90s               │    │
   │  │                            │  │  GitLab Scan:   180s              │    │
   │  └────────────────────────────┘  └────────────────────────────────────┘    │
   │                                                                              │
   │  ┌─────────────────────────────────────────────────────────────────────┐    │
   │  │  Recent Alerts                                                      │    │
   │  │  ──────────────────────────────────────────────────────────────────│    │
   │  │  🔴 2024-12-21 06:01 - Certificate expires in 5 days (nginx-tls)   │    │
   │  │  🟠 2024-12-21 03:15 - 2 high CVEs in trivy scan                   │    │
   │  │  🟡 2024-12-20 06:00 - Certificate expires in 45 days (api-tls)    │    │
   │  └─────────────────────────────────────────────────────────────────────┘    │
   │                                                                              │
   └─────────────────────────────────────────────────────────────────────────────┘
   ```

   **Helm Values pour Monitoring**:
   ```yaml
   # values.yaml
   securityJobs:
     monitoring:
       enabled: true
       prometheus:
         pushgateway: prometheus-pushgateway:9091
         scrapeInterval: 30s
       kafka:
         topic: security-job-results
         enabled: true
       opensearch:
         enabled: true
         indexPrefix: security-jobs
         retentionDays: 90
       grafana:
         dashboardEnabled: true
         dashboardConfigMap: security-jobs-dashboard
       alerting:
         enabled: true
         rules:
           jobNotRunning:
             threshold: 2  # x scheduled interval
             severity: warning
           jobFailed:
             severity: critical
           criticalFindings:
             severity: critical
           slowJob:
             thresholdSeconds: 600
             severity: warning
   ```

   **Checklist Monitoring**:
   - [ ] Déployer Prometheus Pushgateway
   - [ ] Implémenter `BaseSecurityJob` avec métriques
   - [ ] Créer topic Kafka `security-job-results`
   - [ ] Configurer index template OpenSearch
   - [ ] Créer règles AlertManager
   - [ ] Importer dashboard Grafana
   - [ ] Tester alertes (job failure, critical findings)
   - [ ] Configurer rétention OpenSearch (90 jours)

#### Phase 8 : Developer Portal Custom (React)

**Objectif**: Développer un Developer Portal custom React intégré à l'architecture APIM GitOps avec SSO Keycloak unifié.

> **Plan détaillé**: Voir [docs/DEVELOPER-PORTAL-PLAN.md](docs/DEVELOPER-PORTAL-PLAN.md)

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         DEVELOPER PORTAL CUSTOM                                      │
│                                                                                      │
│   ┌──────────────────────────────────────────────────────────────────────────────┐  │
│   │                           FRONTEND (React)                                    │  │
│   │                                                                               │  │
│   │   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │  │
│   │   │  Catalogue  │  │    API      │  │   Mes       │  │   Try-It    │         │  │
│   │   │    APIs     │  │   Detail    │  │   Apps      │  │   Console   │         │  │
│   │   │             │  │  + Swagger  │  │  + Subs     │  │             │         │  │
│   │   └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘         │  │
│   │                                                                               │  │
│   └───────────────────────────────────┬───────────────────────────────────────────┘  │
│                                       │                                              │
│                                       │ REST API                                     │
│                                       ▼                                              │
│   ┌──────────────────────────────────────────────────────────────────────────────┐  │
│   │                      CONTROL-PLANE API (FastAPI)                              │  │
│   │                                                                               │  │
│   │   /portal/apis          → Liste APIs publiées                                │  │
│   │   /portal/apis/{id}     → Détail + OpenAPI spec                              │  │
│   │   /portal/applications  → CRUD Applications                                   │  │
│   │   /portal/subscriptions → Gestion souscriptions                              │  │
│   │   /portal/try-it        → Proxy requêtes vers Gateway                        │  │
│   │                                                                               │  │
│   └───────────────────────────────────┬───────────────────────────────────────────┘  │
│                                       │                                              │
│               ┌───────────────────────┼───────────────────────┐                     │
│               │                       │                       │                     │
│               ▼                       ▼                       ▼                     │
│   ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐             │
│   │    Keycloak      │    │     GitLab       │    │    Gateway       │             │
│   │    (SSO)         │    │    (GitOps)      │    │   (Runtime)      │             │
│   │                  │    │                  │    │                  │             │
│   │ Client:          │    │ Applications     │    │ API Key          │             │
│   │ developer-portal │    │ Subscriptions    │    │ Validation       │             │
│   └──────────────────┘    └──────────────────┘    └──────────────────┘             │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**Stack Technique**:
| Composant | Technologie |
|-----------|-------------|
| Frontend | React 18 + TypeScript + Vite |
| Styling | TailwindCSS |
| Auth | Keycloak OIDC (même realm que UI DevOps) |
| API Docs | Swagger-UI React |
| Code Editor | Monaco Editor |
| Backend | Control-Plane API (FastAPI) - nouveaux endpoints `/portal/*` |

**Fonctionnalités Clés**:

1. **Catalogue APIs** 🔲
   - Liste des APIs publiées avec recherche
   - Filtres par catégorie, tenant
   - Cards avec nom, version, description

2. **Détail API** 🔲
   - Informations générales
   - Documentation OpenAPI (Swagger-UI)
   - Bouton "Souscrire"
   - Code samples (curl, Python, JavaScript)

3. **Gestion Applications** 🔲
   - Créer une application (génère client_id, client_secret, api_key)
   - Voir mes applications
   - Rotation API Key
   - Supprimer application

4. **Souscriptions** 🔲
   - Souscrire une application à une API
   - Voir mes souscriptions
   - Désouscrire

5. **Try-It Console** 🔲
   - Sélection méthode HTTP, path, headers
   - Body editor JSON (Monaco)
   - Envoi requête via proxy backend
   - Affichage réponse (status, headers, body, timing)

**Endpoints Backend à Ajouter** (Control-Plane API):
```
# Catalogue
GET    /portal/apis                    # Liste APIs publiées
GET    /portal/apis/{api_id}           # Détail API
GET    /portal/apis/{api_id}/spec      # Spec OpenAPI

# Applications
GET    /portal/my/applications         # Mes applications
POST   /portal/applications            # Créer application
DELETE /portal/applications/{app_id}   # Supprimer
POST   /portal/applications/{app_id}/rotate-key  # Rotation

# Souscriptions
GET    /portal/my/subscriptions        # Mes souscriptions
POST   /portal/subscriptions           # Souscrire
DELETE /portal/subscriptions/{sub_id}  # Désouscrire

# Try-It
POST   /portal/try-it                  # Proxy vers Gateway
```

**Keycloak - Nouveau Client**:
```yaml
client_id: developer-portal
client_type: public
valid_redirect_uris:
  - https://portal.apim.cab-i.com/*
  - http://localhost:3001/*
roles:
  - developer  # Accès portal
```

**Intégration Kafka**:
- `application-created` → Audit + sync GitLab
- `subscription-created` → Audit + provisionning Gateway
- `api-key-rotated` → Audit + invalidation cache

**Checklist Phase 8**:
- [ ] Setup projet Vite + React + TypeScript + TailwindCSS
- [ ] Configuration Keycloak OIDC (client developer-portal)
- [ ] Layout responsive (Header, Sidebar, Footer)
- [ ] Page Catalogue APIs avec recherche/filtres
- [ ] Page Détail API avec Swagger-UI
- [ ] Page Mes Applications (CRUD)
- [ ] Affichage credentials sécurisé (visible une fois)
- [ ] Page Souscriptions
- [ ] Try-It Console avec Monaco Editor
- [ ] Code Samples (curl, Python, JS)
- [ ] Endpoints `/portal/*` dans Control-Plane API
- [ ] Events Kafka pour audit
- [ ] Déploiement Kubernetes (Helm)
- [ ] URL: https://portal.apim.cab-i.com

#### Phase 9 : Système de Ticketing (Demandes de Production)

**Objectif**: Implémenter un workflow de validation manuelle pour les promotions vers PROD avec traçabilité complète et règle anti-self-approval.

> **Plan détaillé**: Voir [docs/TICKETING-SYSTEM-PLAN.md](docs/TICKETING-SYSTEM-PLAN.md)

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         TICKETING WORKFLOW                                           │
│                                                                                      │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐                      │
│   │  PENDING │───▶│ APPROVED │───▶│DEPLOYING │───▶│ DEPLOYED │                      │
│   └──────────┘    └──────────┘    └──────────┘    └──────────┘                      │
│        │                               │                                             │
│        │                               │                                             │
│        ▼                               ▼                                             │
│   ┌──────────┐                   ┌──────────┐                                       │
│   │ REJECTED │                   │  FAILED  │                                       │
│   └──────────┘                   └──────────┘                                       │
│                                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────────────┐   │
│   │                              FLUX                                            │   │
│   │                                                                              │   │
│   │  DevOps ──▶ Crée demande ──▶ Git (requests/prod/) ──▶ Event Kafka           │   │
│   │                                        │                                     │   │
│   │                                        ▼                                     │   │
│   │  CPI Admin ◀── Notification ◀── UI Console ──▶ Approve/Reject               │   │
│   │                                        │                                     │   │
│   │                                        ▼                                     │   │
│   │  AWX ◀────────── Trigger ◀────── Si approved ──▶ Deploy PROD                │   │
│   │                                        │                                     │   │
│   │                                        ▼                                     │   │
│   │  Callback AWX ──▶ Update Git ──▶ Notification ──▶ Demandeur + Approbateur   │   │
│   │                                                                              │   │
│   └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**Fonctionnalités Clés**:

| Fonctionnalité | Description |
|----------------|-------------|
| Créer une demande | DevOps soumet une demande de promotion STAGING → PROD |
| Validation RBAC | Seuls les CPI/Admins peuvent approuver |
| Anti-self-approval | Le demandeur ne peut pas approuver sa propre demande |
| Workflow automatisé | Approbation → AWX Job → Déploiement PROD |
| Notifications | Email + Slack à chaque étape |
| Historique complet | Audit trail dans Git |

**Structure GitOps**:
```
apim-gitops/
└── requests/
    └── prod/
        └── 2024/
            └── 12/
                ├── PR-2024-0001.yaml
                ├── PR-2024-0002.yaml
                └── PR-2024-0003.yaml
```

**Format Ticket YAML**:
```yaml
apiVersion: apim.cab-i.com/v1
kind: PromotionRequest
metadata:
  id: PR-2024-0003
  createdAt: "2024-12-23T10:30:00Z"
  createdBy: pierre.durand@cab-i.com
  tenant: tenant-finance

spec:
  target:
    type: api
    name: payment-api
    version: "2.1.0"
    sourceEnvironment: staging
    targetEnvironment: prod

  request:
    justification: "New PCI-DSS compliant payment flow"
    impactAssessment: low
    rollbackPlan: "Revert to v2.0.0"

  preChecks:
    stagingTestsPassed: true
    securityScanPassed: true
    testEvidenceUrl: "https://gitlab.../pipeline/12345"

status:
  state: pending  # pending | approved | rejected | deploying | deployed | failed
  history:
    - action: created
      at: "2024-12-23T10:30:00Z"
      by: pierre.durand@cab-i.com
```

**RBAC**:

| Rôle | Créer demande | Approuver | Rejeter | Voir |
|------|---------------|-----------|---------|------|
| DevOps | ✅ Son tenant | ❌ | ❌ | Ses demandes |
| CPI (Tenant Admin) | ✅ Son tenant | ✅ Son tenant* | ✅ Son tenant | Son tenant |
| CPI Admin | ✅ Tous | ✅ Tous* | ✅ Tous | Tous |

*\* Sauf ses propres demandes (anti-self-approval)*

**Endpoints API**:
```
# Liste et recherche
GET    /v1/requests/prod?state=pending&tenant=...

# Mes demandes
GET    /v1/requests/prod/my

# Demandes en attente pour moi (approbateur)
GET    /v1/requests/prod/pending

# Créer une demande
POST   /v1/requests/prod

# Détail
GET    /v1/requests/prod/{id}

# Approuver (déclenche AWX automatiquement)
POST   /v1/requests/prod/{id}/approve

# Rejeter (reason obligatoire)
POST   /v1/requests/prod/{id}/reject

# Stats dashboard
GET    /v1/requests/prod/stats
```

**Intégration Kafka**:
- `request-created` → Notification approbateurs
- `request-approved` → Trigger AWX + notification demandeur
- `request-rejected` → Notification demandeur
- `deployment-started` → Notification demandeur + approbateur
- `deployment-succeeded` → Notification tous
- `deployment-failed` → Notification tous + ops

**Checklist Phase 9**:
- [ ] Modèle Pydantic `PromotionRequest`
- [ ] Service Git pour CRUD requests
- [ ] Endpoints CRUD `/v1/requests/prod`
- [ ] Endpoint approve avec anti-self-approval
- [ ] Endpoint reject avec reason obligatoire
- [ ] Trigger AWX sur approbation
- [ ] Webhook callback AWX → update status
- [ ] UI - Page liste demandes avec filtres
- [ ] UI - Formulaire nouvelle demande
- [ ] UI - Page détail avec timeline
- [ ] UI - Boutons Approve/Reject
- [ ] Events Kafka pour notifications
- [ ] Templates email (created, approved, rejected, deployed, failed)
- [ ] Notifications Slack

#### Phase 9.5 : Production Readiness

**Objectif**: Préparer la plateforme APIM pour le passage en production avec toutes les garanties de fiabilité, sécurité et opérabilité.

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                      PRODUCTION READINESS CHECKLIST                                   │
│                                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────────────┐    │
│   │                         BACKUP & RECOVERY                                    │    │
│   │                                                                              │    │
│   │   AWX Database                    Vault Storage                             │    │
│   │        │                               │                                     │    │
│   │        ▼                               ▼                                     │    │
│   │   ┌──────────┐                   ┌──────────┐                              │    │
│   │   │ CronJob  │                   │ CronJob  │                              │    │
│   │   │  Backup  │                   │ Snapshot │                              │    │
│   │   └────┬─────┘                   └────┬─────┘                              │    │
│   │        │                               │                                     │    │
│   │        └───────────────┬───────────────┘                                    │    │
│   │                        │                                                     │    │
│   │                        ▼                                                     │    │
│   │                  ┌──────────┐                                               │    │
│   │                  │  S3 +    │                                               │    │
│   │                  │  KMS     │                                               │    │
│   │                  └──────────┘                                               │    │
│   │                                                                              │    │
│   └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────────────┐    │
│   │                         TESTING & VALIDATION                                 │    │
│   │                                                                              │    │
│   │   Load Testing              Security Audit           Chaos Testing          │    │
│   │   (K6/Gatling)              (OWASP ZAP)             (Litmus/Chaos Mesh)    │    │
│   │        │                         │                        │                 │    │
│   │        └─────────────────────────┼────────────────────────┘                 │    │
│   │                                  │                                          │    │
│   │                                  ▼                                          │    │
│   │                        ┌──────────────────┐                                 │    │
│   │                        │ Production Ready │                                 │    │
│   │                        │    Validation    │                                 │    │
│   │                        └──────────────────┘                                 │    │
│   │                                                                              │    │
│   └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                       │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**SLO Cibles**:

| Métrique | Objectif | Mesure |
|----------|----------|--------|
| Availability | 99.9% | < 8.76h downtime/an |
| API Latency p95 | < 500ms | Prometheus |
| Deployment Success Rate | > 99% | Jenkins metrics |
| MTTR (P1 incidents) | < 1h | Runbook SLA |
| Error Rate | < 0.1% | Grafana dashboard |

**Composants Production Readiness**:

| Composant | Description | Priorité |
|-----------|-------------|----------|
| Backup AWX | CronJob backup PostgreSQL → S3 | P0 |
| Backup Vault | Snapshot storage + unseal keys | P0 |
| Load Testing | K6/Gatling pipeline avec seuils | P0 |
| Runbooks | Procédures opérationnelles | P0 |
| Security Audit | Scan OWASP ZAP + remédiation | P0 |
| Chaos Testing | Litmus/Chaos Mesh validation | P1 |
| SLO Dashboard | Grafana + alerting | P0 |

**Runbooks à Documenter**:
- Incident: API Gateway down
- Incident: AWX job failure
- Incident: Vault sealed
- Incident: Kafka lag élevé
- Procédure: Rollback d'urgence
- Procédure: Scaling horizontal
- Procédure: Rotation des secrets
- Procédure: DR failover

**Checklist Phase 9.5**:
- [ ] Script backup AWX database (PostgreSQL) → S3
- [ ] Script backup Vault snapshot → S3 + KMS
- [ ] CronJob Kubernetes pour backups quotidiens
- [ ] Procédures de restore documentées et testées
- [ ] Pipeline Load Testing (K6 ou Gatling)
- [ ] Seuils de performance définis (p95, p99)
- [ ] Runbooks opérationnels (docs/runbooks/)
- [ ] Scan OWASP ZAP sur API et UI
- [ ] Remédiation vulnérabilités critiques
- [ ] Chaos Testing (pod kill, network latency)
- [ ] Validation auto-healing Kubernetes
- [ ] SLO/SLA documentés
- [ ] Dashboard SLO dans Grafana
- [ ] Alertes configurées sur SLO breach

#### Phase 10 : Resource Lifecycle Management (Non-Production Auto-Teardown)

**Objectif**: Implémenter une stratégie de tagging obligatoire et d'auto-suppression des ressources non-production pour optimiser les coûts et éviter l'accumulation de ressources orphelines.

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                      RESOURCE LIFECYCLE MANAGEMENT                                    │
│                                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────────────┐    │
│   │                         MANDATORY TAGS                                       │    │
│   │                                                                              │    │
│   │   environment    : dev | staging | sandbox | demo                           │    │
│   │   owner          : email du responsable                                     │    │
│   │   project        : nom du projet / tenant                                   │    │
│   │   cost-center    : code centre de coût                                      │    │
│   │   ttl            : durée de vie (7d, 14d, 30d max)                          │    │
│   │   created_at     : date de création (auto)                                  │    │
│   │   auto-teardown  : true | false                                             │    │
│   │   data-class     : public | internal | confidential | restricted            │    │
│   │                                                                              │    │
│   └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────────────┐    │
│   │                            WORKFLOW                                          │    │
│   │                                                                              │    │
│   │   Deploy Request                                                            │    │
│   │        │                                                                     │    │
│   │        ▼                                                                     │    │
│   │   ┌──────────┐    Missing tags?    ┌──────────┐                            │    │
│   │   │ Validate │───────────────────▶ │ REJECTED │                            │    │
│   │   │   Tags   │                     └──────────┘                            │    │
│   │   └────┬─────┘                                                              │    │
│   │        │ OK                                                                  │    │
│   │        ▼                                                                     │    │
│   │   ┌──────────┐    TTL > 30d?       ┌──────────┐                            │    │
│   │   │  Check   │───────────────────▶ │ REJECTED │                            │    │
│   │   │   TTL    │                     └──────────┘                            │    │
│   │   └────┬─────┘                                                              │    │
│   │        │ OK                                                                  │    │
│   │        ▼                                                                     │    │
│   │   ┌──────────┐    data-class =     ┌───────────────┐                       │    │
│   │   │  Check   │    restricted?      │ REQUIRE MANUAL│                       │    │
│   │   │Data Class│───────────────────▶ │   APPROVAL    │                       │    │
│   │   └────┬─────┘                     └───────────────┘                       │    │
│   │        │ OK                                                                  │    │
│   │        ▼                                                                     │    │
│   │   ┌──────────┐                                                              │    │
│   │   │  DEPLOY  │                                                              │    │
│   │   └──────────┘                                                              │    │
│   │                                                                              │    │
│   └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────────────┐    │
│   │                         AUTO-TEARDOWN SCHEDULER                              │    │
│   │                                                                              │    │
│   │   EventBridge (cron: 0 2 * * *)                                             │    │
│   │        │                                                                     │    │
│   │        ▼                                                                     │    │
│   │   ┌──────────────┐                                                          │    │
│   │   │    Lambda    │                                                          │    │
│   │   │ cleanup-job  │                                                          │    │
│   │   └──────┬───────┘                                                          │    │
│   │          │                                                                   │    │
│   │    ┌─────┴─────────────────────────────────────────┐                        │    │
│   │    │                                               │                        │    │
│   │    ▼                                               ▼                        │    │
│   │  AWS Resources                              K8s Resources                   │    │
│   │  - EC2 instances                            - Namespaces                    │    │
│   │  - RDS databases                            - Deployments                   │    │
│   │  - S3 buckets                               - Services                      │    │
│   │  - EKS nodegroups                           - ConfigMaps                    │    │
│   │                                                                              │    │
│   │   1. Query resources where auto-teardown=true                               │    │
│   │   2. Check if created_at + ttl < now()                                      │    │
│   │   3. Notify owner (48h warning, then 24h, then delete)                      │    │
│   │   4. Delete expired resources                                               │    │
│   │   5. Audit log to Kafka + S3                                                │    │
│   │                                                                              │    │
│   └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                       │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**Tags Obligatoires**:

| Tag | Description | Valeurs Possibles | Obligatoire |
|-----|-------------|-------------------|-------------|
| `environment` | Environnement cible | `dev`, `staging`, `sandbox`, `demo` | ✅ |
| `owner` | Email du responsable | Email valide | ✅ |
| `project` | Nom du projet/tenant | String | ✅ |
| `cost-center` | Code centre de coût | Code numérique | ✅ |
| `ttl` | Durée de vie | `7d`, `14d`, `30d` (max) | ✅ Non-prod |
| `created_at` | Date création | ISO 8601 (auto-généré) | ✅ Auto |
| `auto-teardown` | Suppression auto | `true`, `false` | ✅ Non-prod |
| `data-class` | Classification données | `public`, `internal`, `confidential`, `restricted` | ✅ |

**Guardrails (Règles de Protection)**:

1. **Tag Validation** - Rejeter tout déploiement sans tags obligatoires
2. **TTL Maximum** - 30 jours max pour environnements non-prod
3. **Data Classification** - Ressources `restricted` exclues de l'auto-teardown
4. **Owner Notification** - 48h avant expiration → 24h → suppression
5. **Audit Trail** - Toute suppression loggée dans Kafka + S3

**Terraform - Module common_tags**:
```hcl
# terraform/modules/common_tags/variables.tf
variable "environment" {
  type        = string
  description = "Environment name (dev, staging, sandbox, demo)"
  validation {
    condition     = contains(["dev", "staging", "sandbox", "demo", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, sandbox, demo, prod."
  }
}

variable "owner" {
  type        = string
  description = "Owner email address"
  validation {
    condition     = can(regex("^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$", var.owner))
    error_message = "Owner must be a valid email address."
  }
}

variable "project" {
  type        = string
  description = "Project or tenant name"
}

variable "cost_center" {
  type        = string
  description = "Cost center code"
}

variable "ttl" {
  type        = string
  description = "Time to live (7d, 14d, 30d)"
  default     = "14d"
  validation {
    condition     = can(regex("^(7|14|30)d$", var.ttl))
    error_message = "TTL must be 7d, 14d, or 30d."
  }
}

variable "auto_teardown" {
  type        = bool
  description = "Enable automatic teardown after TTL"
  default     = true
}

variable "data_class" {
  type        = string
  description = "Data classification"
  default     = "internal"
  validation {
    condition     = contains(["public", "internal", "confidential", "restricted"], var.data_class)
    error_message = "Data class must be one of: public, internal, confidential, restricted."
  }
}

# terraform/modules/common_tags/outputs.tf
output "tags" {
  value = {
    environment    = var.environment
    owner          = var.owner
    project        = var.project
    cost-center    = var.cost_center
    ttl            = var.environment != "prod" ? var.ttl : "permanent"
    created_at     = timestamp()
    auto-teardown  = var.environment != "prod" ? tostring(var.auto_teardown) : "false"
    data-class     = var.data_class
    managed-by     = "terraform"
  }
}
```

**Utilisation Terraform**:
```hcl
# terraform/environments/dev/main.tf
module "tags" {
  source = "../../modules/common_tags"

  environment   = "dev"
  owner         = "devteam@cab-i.com"
  project       = "apim-platform"
  cost_center   = "CC-12345"
  ttl           = "14d"
  auto_teardown = true
  data_class    = "internal"
}

resource "aws_instance" "example" {
  ami           = "ami-xxxxx"
  instance_type = "t3.medium"

  tags = module.tags.tags
}
```

**Lambda Cleanup Job**:
```python
# lambda/resource_cleanup/handler.py
import boto3
from datetime import datetime, timedelta
import json

def handler(event, context):
    """
    Scheduled job to cleanup expired non-prod resources.
    Runs daily at 2 AM UTC via EventBridge.
    """
    ec2 = boto3.client('ec2')
    rds = boto3.client('rds')

    # Find resources with auto-teardown=true and expired TTL
    filters = [
        {'Name': 'tag:auto-teardown', 'Values': ['true']},
        {'Name': 'tag:environment', 'Values': ['dev', 'staging', 'sandbox', 'demo']}
    ]

    instances = ec2.describe_instances(Filters=filters)

    for reservation in instances['Reservations']:
        for instance in reservation['Instances']:
            tags = {t['Key']: t['Value'] for t in instance.get('Tags', [])}

            # Skip restricted data
            if tags.get('data-class') == 'restricted':
                continue

            created_at = datetime.fromisoformat(tags.get('created_at', ''))
            ttl_days = int(tags.get('ttl', '14d').replace('d', ''))
            expiry = created_at + timedelta(days=ttl_days)

            if datetime.utcnow() > expiry:
                # Notify owner before deletion
                notify_owner(tags.get('owner'), instance['InstanceId'], 'terminated')
                ec2.terminate_instances(InstanceIds=[instance['InstanceId']])

                # Audit log
                log_deletion(instance['InstanceId'], tags)

    return {'statusCode': 200, 'deleted': deleted_count}
```

**Alternative: n8n Workflow (Low-Code)**:
- Pour environnements multi-cloud (AWS + Azure + GCP)
- Workflow visuel avec nœuds configurables
- Intégration Slack/Teams pour notifications
- Dashboard de reporting des ressources expirées

**Kubernetes - OPA Gatekeeper Policy**:
```yaml
# k8s/policies/require-resource-tags.yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8srequiredtags
spec:
  crd:
    spec:
      names:
        kind: K8sRequiredTags
      validation:
        openAPIV3Schema:
          type: object
          properties:
            requiredTags:
              type: array
              items:
                type: string
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package k8srequiredtags

        violation[{"msg": msg}] {
          provided := {label | input.review.object.metadata.labels[label]}
          required := {label | label := input.parameters.requiredTags[_]}
          missing := required - provided
          count(missing) > 0
          msg := sprintf("Missing required tags: %v", [missing])
        }
---
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sRequiredTags
metadata:
  name: require-resource-lifecycle-tags
spec:
  match:
    kinds:
      - apiGroups: [""]
        kinds: ["Namespace", "Pod"]
      - apiGroups: ["apps"]
        kinds: ["Deployment", "StatefulSet"]
    excludedNamespaces:
      - kube-system
      - gatekeeper-system
      - apim-system  # Core platform excluded
  parameters:
    requiredTags:
      - environment
      - owner
      - project
      - ttl
```

**CI/CD Tag Governance** (GitHub Actions):
```yaml
# .github/workflows/tag-governance.yaml
name: Tag Governance Check

on:
  pull_request:
    paths:
      - 'terraform/**'
      - 'k8s/**'

jobs:
  check-tags:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Check Terraform Tags
        run: |
          # Ensure all resources use common_tags module
          missing=$(grep -rL "module.tags.tags" terraform/environments/*/main.tf || true)
          if [ -n "$missing" ]; then
            echo "::error::Resources without common_tags: $missing"
            exit 1
          fi

      - name: Validate TTL Values
        run: |
          # Ensure TTL doesn't exceed 30d for non-prod
          invalid=$(grep -r 'ttl.*=.*"[4-9][0-9]d\|[1-9][0-9][0-9]d"' terraform/ || true)
          if [ -n "$invalid" ]; then
            echo "::error::TTL exceeds maximum 30 days: $invalid"
            exit 1
          fi
```

**Intégration Kafka**:
- `resource-created` → Log création avec tags
- `resource-expiring` → Notification 48h/24h avant expiration
- `resource-deleted` → Audit trail suppression
- `tag-violation` → Alerte déploiement sans tags

**Checklist Phase 10**:
- [ ] Module Terraform `common_tags` avec validations
- [ ] Lambda `resource-cleanup` avec EventBridge schedule
- [ ] Notifications owner (48h → 24h → delete)
- [ ] OPA Gatekeeper policies pour Kubernetes
- [ ] GitHub Actions workflow `tag-governance.yaml`
- [ ] Dashboard Grafana "Resource Lifecycle"
- [ ] Events Kafka (resource-created, expiring, deleted)
- [ ] Exclusion ressources `data-class=restricted`
- [ ] Exclusion environnement `prod` (auto-teardown=false)
- [ ] Documentation tagging policy
- [ ] Alternative n8n workflow pour multi-cloud (optionnel)

#### Phase 11 : Resource Lifecycle Advanced (Gouvernance Avancée)

**Objectif**: Compléter la Phase 10 avec des fonctionnalités avancées de gouvernance : quotas, whitelist, destruction ordonnée, métriques de coûts et self-service TTL extension.

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                      RESOURCE LIFECYCLE ADVANCED                                      │
│                                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────────────┐    │
│   │                         QUOTAS PAR PROJET                                    │    │
│   │                                                                              │    │
│   │   Limites configurables par project/tenant:                                 │    │
│   │                                                                              │    │
│   │   ┌─────────────────────────────────────────────────────────────────────┐   │    │
│   │   │  Resource Type        │  Default Quota  │  Custom (per tenant)     │   │    │
│   │   ├───────────────────────┼─────────────────┼──────────────────────────┤   │    │
│   │   │  EC2 Instances        │  10             │  Configurable            │   │    │
│   │   │  RDS Databases        │  3              │  Configurable            │   │    │
│   │   │  S3 Buckets           │  5              │  Configurable            │   │    │
│   │   │  Lambda Functions     │  20             │  Configurable            │   │    │
│   │   │  K8s Namespaces       │  5              │  Configurable            │   │    │
│   │   │  EBS Volumes (GB)     │  500            │  Configurable            │   │    │
│   │   │  EKS Node Groups      │  2              │  Configurable            │   │    │
│   │   └───────────────────────┴─────────────────┴──────────────────────────┘   │    │
│   │                                                                              │    │
│   └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────────────┐    │
│   │                         WHITELIST (NEVER DELETE)                             │    │
│   │                                                                              │    │
│   │   Ressources critiques exclues de l'auto-teardown:                          │    │
│   │                                                                              │    │
│   │   whitelist.yaml:                                                           │    │
│   │   ├── arn:aws:ec2:*:*:instance/i-core-*      # Instances core              │    │
│   │   ├── arn:aws:rds:*:*:db:apim-*              # BDD plateforme              │    │
│   │   ├── arn:aws:s3:::apim-artifacts-*          # Buckets artifacts           │    │
│   │   ├── namespace:apim-system                   # K8s core namespace         │    │
│   │   └── tag:critical=true                       # Tag générique              │    │
│   │                                                                              │    │
│   └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────────────┐    │
│   │                    DESTRUCTION ORDONNÉE (Dependencies)                       │    │
│   │                                                                              │    │
│   │   Ordre de suppression pour éviter les erreurs:                             │    │
│   │                                                                              │    │
│   │   1. Detach IAM Policies/Roles                                              │    │
│   │   2. Stop Auto Scaling Groups                                               │    │
│   │   3. Terminate EC2 Instances                                                │    │
│   │   4. Delete Load Balancers                                                  │    │
│   │   5. Empty & Delete S3 Buckets                                              │    │
│   │   6. Delete RDS Snapshots (optionnel)                                       │    │
│   │   7. Delete RDS Instances                                                   │    │
│   │   8. Delete EBS Volumes orphelins                                           │    │
│   │   9. Delete Security Groups (après dépendances)                             │    │
│   │   10. Delete K8s Namespaces (cascade delete)                                │    │
│   │                                                                              │    │
│   └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────────────┐    │
│   │                         SELF-SERVICE TTL EXTENSION                           │    │
│   │                                                                              │    │
│   │   Email de pré-alerte contient:                                             │    │
│   │                                                                              │    │
│   │   ┌───────────────────────────────────────────────────────────────────┐     │    │
│   │   │  ⚠️ Votre ressource "dev-api-server" expire dans 24h              │     │    │
│   │   │                                                                    │     │    │
│   │   │  [🔄 Snooze +7 jours]  [🔄 Snooze +14 jours]  [❌ Supprimer]      │     │    │
│   │   │                                                                    │     │    │
│   │   │  Lien: https://api.apim.cab-i.com/v1/resources/{id}/extend?days=7 │     │    │
│   │   └───────────────────────────────────────────────────────────────────┘     │    │
│   │                                                                              │    │
│   │   API Endpoint: PATCH /v1/resources/{id}/ttl                                │    │
│   │   Body: { "extend_days": 7, "reason": "Tests en cours" }                    │    │
│   │   Limite: max 2 extensions (30j + 30j = 60j total max)                      │    │
│   │                                                                              │    │
│   └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────────────┐    │
│   │                         MÉTRIQUES & REPORTING                                │    │
│   │                                                                              │    │
│   │   Dashboard "Cost Savings":                                                 │    │
│   │                                                                              │    │
│   │   ┌─────────────────────────────────────────────────────────────────────┐   │    │
│   │   │  Ce mois-ci:                                                         │   │    │
│   │   │  ├── 47 ressources supprimées automatiquement                       │   │    │
│   │   │  ├── 💰 Coût évité estimé: $2,340                                   │   │    │
│   │   │  ├── 12 ressources snooze (+7j)                                     │   │    │
│   │   │  └── 3 violations tags bloquées                                     │   │    │
│   │   │                                                                      │   │    │
│   │   │  Par project:                                                        │   │    │
│   │   │  ├── tenant-finance: $890 économisés (18 ressources)                │   │    │
│   │   │  ├── poc-ml-team: $720 économisés (15 ressources)                   │   │    │
│   │   │  └── sandbox-dev: $730 économisés (14 ressources)                   │   │    │
│   │   └─────────────────────────────────────────────────────────────────────┘   │    │
│   │                                                                              │    │
│   │   Calcul coût évité:                                                        │    │
│   │   - EC2: instance_type → prix horaire AWS × heures restantes TTL           │    │
│   │   - RDS: db_instance_class × heures × multi-AZ factor                      │    │
│   │   - S3: storage_gb × $0.023/GB + requests estimées                         │    │
│   │                                                                              │    │
│   └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                       │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**Quotas par Projet** (Terraform):
```hcl
# terraform/modules/project_quotas/variables.tf
variable "project_quotas" {
  type = map(object({
    ec2_instances    = number
    rds_databases    = number
    s3_buckets       = number
    lambda_functions = number
    k8s_namespaces   = number
    ebs_volumes_gb   = number
  }))
  default = {
    default = {
      ec2_instances    = 10
      rds_databases    = 3
      s3_buckets       = 5
      lambda_functions = 20
      k8s_namespaces   = 5
      ebs_volumes_gb   = 500
    }
  }
}

# Service Quotas AWS + validation avant déploiement
resource "aws_servicequotas_service_quota" "ec2_instances" {
  quota_code   = "L-1216C47A"
  service_code = "ec2"
  value        = var.project_quotas["default"].ec2_instances
}
```

**Whitelist Configuration**:
```yaml
# config/whitelist.yaml
never_delete:
  # Par ARN pattern
  aws_resources:
    - "arn:aws:ec2:*:*:instance/i-apim-*"
    - "arn:aws:rds:*:*:db:apim-prod-*"
    - "arn:aws:s3:::apim-artifacts"
    - "arn:aws:s3:::apim-backups"
    - "arn:aws:lambda:*:*:function:apim-core-*"

  # Par tag
  tags:
    - key: critical
      value: "true"
    - key: environment
      value: "prod"

  # K8s namespaces
  kubernetes:
    namespaces:
      - kube-system
      - gatekeeper-system
      - apim-system
      - monitoring
      - vault
```

**API Self-Service TTL Extension**:
```python
# control-plane-api/src/routers/resources.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/v1/resources", tags=["Resources"])

class TTLExtendRequest(BaseModel):
    extend_days: int  # 7 ou 14
    reason: str

@router.patch("/{resource_id}/ttl")
async def extend_ttl(resource_id: str, request: TTLExtendRequest, user: User = Depends(get_current_user)):
    """
    Extend TTL of a resource (max 2 extensions, 60 days total).
    """
    resource = await get_resource(resource_id)

    # Vérifier ownership
    if resource.tags.get("owner") != user.email:
        raise HTTPException(403, "Only resource owner can extend TTL")

    # Vérifier limite extensions
    if resource.extension_count >= 2:
        raise HTTPException(400, "Maximum 2 extensions allowed (60 days total)")

    # Vérifier jours demandés
    if request.extend_days not in [7, 14]:
        raise HTTPException(400, "Extension must be 7 or 14 days")

    # Mettre à jour le tag TTL
    new_ttl = f"{int(resource.tags['ttl'].replace('d', '')) + request.extend_days}d"
    await update_resource_tag(resource_id, "ttl", new_ttl)
    await increment_extension_count(resource_id)

    # Audit
    await emit_kafka_event("resource-ttl-extended", {
        "resource_id": resource_id,
        "old_ttl": resource.tags["ttl"],
        "new_ttl": new_ttl,
        "extended_by": user.email,
        "reason": request.reason
    })

    return {"message": f"TTL extended to {new_ttl}", "extensions_remaining": 2 - resource.extension_count - 1}
```

**Lambda Destruction Ordonnée**:
```python
# lambda/resource_cleanup/ordered_destroy.py
DESTRUCTION_ORDER = [
    ("iam", "detach_policies"),
    ("autoscaling", "stop_groups"),
    ("ec2", "terminate_instances"),
    ("elb", "delete_load_balancers"),
    ("s3", "empty_and_delete_buckets"),
    ("rds", "delete_snapshots"),
    ("rds", "delete_instances"),
    ("ec2", "delete_volumes"),
    ("ec2", "delete_security_groups"),
    ("eks", "delete_namespaces"),
]

async def ordered_destroy(resources: list):
    """Destroy resources in dependency order."""
    for service, action in DESTRUCTION_ORDER:
        service_resources = [r for r in resources if r.service == service]
        if service_resources:
            handler = get_handler(service, action)
            for resource in service_resources:
                try:
                    await handler(resource)
                    await log_deletion(resource, "success")
                except Exception as e:
                    await log_deletion(resource, "failed", str(e))
                    # Continue with next resource
```

**Métriques Coût Évité** (Grafana/Prometheus):
```python
# lambda/resource_cleanup/cost_calculator.py
AWS_PRICING = {
    "t3.micro": 0.0104,
    "t3.small": 0.0208,
    "t3.medium": 0.0416,
    "t3.large": 0.0832,
    "db.t3.micro": 0.017,
    "db.t3.small": 0.034,
    "db.t3.medium": 0.068,
}

def calculate_cost_avoided(resource, remaining_hours: int) -> float:
    """Calculate estimated cost avoided by early deletion."""
    if resource.type == "ec2":
        hourly_rate = AWS_PRICING.get(resource.instance_type, 0.05)
    elif resource.type == "rds":
        hourly_rate = AWS_PRICING.get(resource.db_instance_class, 0.05)
        if resource.multi_az:
            hourly_rate *= 2
    elif resource.type == "s3":
        # Estimate based on storage size
        return resource.size_gb * 0.023
    else:
        hourly_rate = 0.01  # Default estimate

    return hourly_rate * remaining_hours
```

**n8n Workflow Complet avec Board Notion**:
```json
{
  "name": "Resource Cleanup Advanced",
  "nodes": [
    {"type": "Schedule Trigger", "cron": "0 * * * *"},
    {"type": "AWS", "action": "Describe resources with auto-teardown=true"},
    {"type": "Function", "code": "Check whitelist + calculate expiry"},
    {"type": "IF", "condition": "expiring_in_48h"},
    {"type": "Slack", "message": "Pre-alert notification"},
    {"type": "Notion", "action": "Add to 'Resources to Delete' database"},
    {"type": "Wait", "duration": "24h"},
    {"type": "IF", "condition": "not_snoozed"},
    {"type": "Function", "code": "Ordered destruction"},
    {"type": "HTTP", "url": "/v1/events/resource-deleted"},
    {"type": "Notion", "action": "Mark as deleted"},
    {"type": "Slack", "message": "Deletion report + cost saved"}
  ]
}
```

**Checklist Phase 11**:
- [ ] Système de quotas par projet (Terraform + Service Quotas AWS)
- [ ] Whitelist configuration (YAML + validation)
- [ ] Destruction ordonnée (dépendances AWS)
- [ ] API self-service TTL extension (`PATCH /v1/resources/{id}/ttl`)
- [ ] Boutons Snooze dans emails (7j, 14j)
- [ ] Limite 2 extensions max (60j total)
- [ ] Calcul coût évité (pricing AWS)
- [ ] Dashboard Grafana "Cost Savings"
- [ ] Métriques Prometheus (resources_deleted, cost_avoided_usd)
- [ ] n8n workflow complet avec Notion board
- [ ] Cron horaire (au lieu de quotidien) pour pré-alertes
- [ ] Event Kafka `resource-ttl-extended`

---

### Architecture Cible Complète

```
┌─────────────────────────────────────────────────────────────────────┐
│                         UTILISATEURS                                 │
│   CPI Admin │ Tenant Admin │ DevOps │ Viewer                        │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    UI Control-Plane (React + Keycloak)               │
│                    https://devops.apim.cab-i.com                     │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Control-Plane API (FastAPI)                       │
│                    https://api.apim.cab-i.com                        │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ /v1/tenants     │ /v1/apis     │ /v1/deploy     │ /v1/events   ││
│  └─────────────────────────────────────────────────────────────────┘│
│                           │                                          │
│           ┌───────────────┼───────────────┬──────────────┐          │
│           ▼               ▼               ▼              ▼          │
│    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐   │
│    │  GitLab  │    │ Redpanda │    │   AWX    │    │  Vault   │   │
│    │ (GitOps) │    │ (Kafka)  │    │(Ansible) │    │(Secrets) │   │
│    └──────────┘    └──────────┘    └──────────┘    └──────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    RUNTIME LAYER                                     │
│   ┌────────────────────────────────────────────────────────┐        │
│   │              webMethods Gateway (DEV)                   │        │
│   └────────────────────────────────────────────────────────┘        │
│              │                                                       │
│              ▼                                                       │
│   ┌────────────────────────────────────────────────────────┐        │
│   │              Elasticsearch 8 (EKS)                      │        │
│   │              cluster: SAG_EventDataStore                │        │
│   └────────────────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────────────────┘
```

### Estimation Temps de Développement

| Phase | Description | Durée Estimée |
|-------|-------------|---------------|
| Phase 1 | Kafka/Redpanda + AWX Automation | À planifier |
| Phase 2 | GitOps + Variables d'Environnement + IAM | À planifier |
| Phase 3 | Vault + Gateway Alias | À planifier |
| Phase 4 | OpenSearch + Monitoring | À planifier |
| Phase 5 | Multi-environnements (dev/staging/prod) | À planifier |
| Phase 6 | Demo Tenant + SSO Unifié + Documentation | À planifier |
| Phase 7 | Sécurité Opérationnelle (Batch Jobs) | À planifier |
| Phase 8 | Developer Portal Custom (React) | À planifier |
| Phase 9 | Ticketing (Demandes de Production) | À planifier |
| Phase 9.5 | Production Readiness | À planifier |
| Phase 10 | Resource Lifecycle (Tagging + Auto-Teardown) | À planifier |
