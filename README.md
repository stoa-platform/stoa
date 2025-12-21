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

## Structure du Projet

```
apim-aws/
├── control-plane-api/       # FastAPI backend
│   ├── src/
│   │   ├── auth/            # RBAC & Keycloak
│   │   ├── routers/         # API endpoints
│   │   └── services/        # Business logic
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
├── charts/                  # Helm charts
│   ├── control-plane-api/
│   └── control-plane-ui/
├── terraform/               # Infrastructure as Code
│   ├── modules/
│   │   ├── vpc/
│   │   ├── eks/
│   │   ├── rds/
│   │   └── ecr/
│   └── environments/
│       └── dev/
├── keycloak/                # Keycloak config
│   └── realm-export.json
└── CLAUDE.md                # Claude Code instructions
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
| Developer Portal | https://portal.apim.cab-i.com/portal/ | Portail développeur |
| **AWX (Ansible)** | https://awx.apim.cab-i.com | Automation (admin: admin/demo) |
| Redpanda Console | `kubectl port-forward svc/redpanda-console 8080:8080 -n apim-system` | Administration Kafka (interne) |

### Environnement STAGING (à venir)

| Service | URL |
|---------|-----|
| Control Plane UI | https://devops.staging.apim.cab-i.com |
| Control Plane API | https://api.staging.apim.cab-i.com |
| Keycloak | https://auth.staging.apim.cab-i.com |
| API Gateway | https://gateway.staging.apim.cab-i.com |
| Developer Portal | https://portal.staging.apim.cab-i.com |

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
| Developer Portal | 100m | 512Mi | 1 | 100m | 512Mi |
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
- [webMethods Developer Portal](https://github.com/ibm-wm-transition/webmethods-developer-portal) - Documentation Developer Portal
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
| webMethods Portal | ✅ Déployé | Developer Portal |
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

#### Phase 1 : Event-Driven Architecture ✅ DÉPLOYÉ

> **Infrastructure**: Nodes scalés à t3.large (2 CPU / 8GB RAM) pour supporter Redpanda.

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
         ✅                 ✅                  🔲                 ✅
   ```

4. **AWX (Ansible Tower)** ✅ DÉPLOYÉ
   - AWX 24.6.1 via AWX Operator 2.19.1
   - URL: https://awx.apim.cab-i.com
   - Login: admin / demo
   - Base de données: RDS PostgreSQL (partagée avec Keycloak)

   **Jobs à configurer**:
   - `deploy-api` - Déploie une API sur la Gateway
   - `sync-gateway` - Synchronise config Gateway
   - `promote-portal` - Publie API sur Developer Portal
   - `rollback` - Rollback en cas d'échec

   **Intégration Kafka (à configurer)**:
   - Consumer Kafka → Trigger AWX Job Templates via Webhook
   - Topics surveillés: `deploy-requests`, `api-created`, `api-updated`

#### Phase 2 : GitOps (Priorité Haute)

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

#### Phase 3 : Sécurité & Secrets (Priorité Moyenne)
1. **Déployer HashiCorp Vault**
   - Secrets dynamiques pour clients OAuth2
   - API Keys rotation

2. **Intégrer Vault dans Control-Plane API**
   - Stockage clientSecret/apiKey
   - Références: vault:secret/apps/{app}#key

#### Phase 4 : Observabilité (Priorité Moyenne)

Stack complète d'observabilité pour APIM Platform:

```
┌─────────────────────────────────────────────────────────────────────┐
│                      OBSERVABILITY STACK                             │
│                                                                      │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐         │
│  │   METRICS      │  │    LOGS        │  │   TRACES       │         │
│  │   Prometheus   │  │    Loki        │  │ OpenTelemetry  │         │
│  └───────┬────────┘  └───────┬────────┘  └───────┬────────┘         │
│          │                   │                   │                   │
│          └───────────────────┼───────────────────┘                   │
│                              ▼                                       │
│                    ┌─────────────────┐                              │
│                    │     GRAFANA     │                              │
│                    │   Dashboards    │                              │
│                    │   + Alerting    │                              │
│                    └─────────────────┘                              │
└─────────────────────────────────────────────────────────────────────┘
```

1. **Prometheus Stack** (kube-prometheus-stack)
   - Métriques Kubernetes (nodes, pods, services)
   - Métriques API Gateway (requests, latency, errors)
   - Métriques Control-Plane API (FastAPI metrics)
   - ServiceMonitors pour tous les composants
   - Helm: `prometheus-community/kube-prometheus-stack`

2. **Grafana Loki** (Logs aggregation)
   - Logs centralisés de tous les pods
   - Logs API Gateway transactions
   - Logs Control-Plane API (audit, errors)
   - Retention configurable par namespace
   - Helm: `grafana/loki-stack`

3. **OpenTelemetry** (Distributed Tracing)
   - Traces end-to-end: UI → API → Kafka → AWX → Gateway
   - Correlation IDs pour debug
   - Instrumentation auto pour FastAPI
   - OpenTelemetry Collector
   - Helm: `open-telemetry/opentelemetry-collector`

4. **Grafana Dashboards**
   - **APIM Overview**: APIs déployées, requêtes/sec, latence P99
   - **Pipeline Status**: Control-Plane → Kafka → AWX → Gateway
   - **Tenant Analytics**: Usage par tenant, quotas
   - **Deployment History**: Succès/échecs, rollbacks
   - **Error Analysis**: Top errors, traces associées

5. **Alerting** (Grafana + AlertManager)
   - Slack/Email/PagerDuty notifications
   - Alertes critiques:
     - Gateway down
     - Deployment failed
     - High error rate (>5%)
     - Latency spike (P99 > 500ms)
     - Disk space low
   - Alertes warning:
     - Pod restarts
     - Memory pressure
     - Kafka lag

**URLs Observabilité (à déployer)**:
| Service | URL |
|---------|-----|
| Grafana | https://grafana.apim.cab-i.com |
| Prometheus | https://prometheus.apim.cab-i.com (interne) |
| Loki | Interne (via Grafana datasource) |

#### Phase 5 : Multi-Environment (Priorité Basse)
1. **Environnement STAGING**
   - Promotion DEV → STAGING
   - Portal publication

2. **OpenSearch Analytics**
   - Global Policy par tenant
   - Index pattern: {env}-{tenant}-analytics

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
│   ┌────────────────────┐         ┌────────────────────┐             │
│   │ webMethods Gateway │ ◄─────► │ Developer Portal   │             │
│   │ (DEV)              │         │                    │             │
│   └────────────────────┘         └────────────────────┘             │
│              │                              │                        │
│              ▼                              ▼                        │
│   ┌────────────────────────────────────────────────────────┐        │
│   │              Elasticsearch 7.17 (EKS)                   │        │
│   │              cluster: SAG_EventDataStore                │        │
│   └────────────────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────────────────┘
```

### Estimation Temps de Développement

| Phase | Durée Estimée |
|-------|---------------|
| Phase 1 (Kafka + AWX) | À planifier |
| Phase 2 (GitOps) | À planifier |
| Phase 3 (Vault) | À planifier |
| Phase 4 (Monitoring) | À planifier |
| Phase 5 (Multi-env) | À planifier |
