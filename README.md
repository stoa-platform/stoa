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
   - `Promote Portal` (id: 10) - Publie API sur Developer Portal
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

#### Phase 5 : Multi-Environment (Priorité Basse)
1. **Environnement STAGING**
   - Promotion DEV → STAGING
   - Portal publication

2. **OpenSearch Analytics**
   - Global Policy par tenant
   - Index pattern: {env}-{tenant}-analytics

#### Phase 6 : Tenant Démo & SSO Unifié (Beta Testing)

**Objectif**: Créer un tenant de démonstration avec des utilisateurs beta testeurs, et unifier l'authentification SSO sur toutes les interfaces (UI DevOps + Developer Portal).

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           SSO UNIFIÉ - KEYCLOAK                                      │
│                                                                                      │
│                        ┌──────────────────────────┐                                 │
│                        │       KEYCLOAK           │                                 │
│                        │   Realm: apim-platform   │                                 │
│                        │                          │                                 │
│                        │  Clients:                │                                 │
│                        │  ├── control-plane-ui    │                                 │
│                        │  ├── control-plane-api   │                                 │
│                        │  └── developer-portal    │  ⬅️ NOUVEAU                    │
│                        └────────────┬─────────────┘                                 │
│                                     │                                                │
│              ┌──────────────────────┼──────────────────────┐                        │
│              │                      │                      │                        │
│              ▼                      ▼                      ▼                        │
│   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐               │
│   │   UI DevOps     │    │ Control-Plane   │    │   Developer     │               │
│   │   (React)       │    │     API         │    │    Portal       │               │
│   │                 │    │   (FastAPI)     │    │  (webMethods)   │               │
│   │ devops.apim...  │    │  api.apim...    │    │ portal.apim...  │               │
│   └─────────────────┘    └─────────────────┘    └─────────────────┘               │
│          │                       │                      │                          │
│          └───────────────────────┼──────────────────────┘                          │
│                                  │                                                  │
│                    ┌─────────────┴─────────────┐                                   │
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
   | Demo CPI | demo-cpi@cab-i.com | `tenant-admin` | UI DevOps + Portal (full CRUD) |
   | Demo DevOps | demo-devops@cab-i.com | `devops` | UI DevOps + Portal (deploy only) |

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

3. **Configurer SSO Developer Portal (webMethods)** 🔲

   Le Developer Portal webMethods doit être configuré pour utiliser Keycloak comme IdP.

   **Keycloak - Nouveau Client pour Portal**:
   ```yaml
   # Client: developer-portal
   clientId: developer-portal
   name: "Developer Portal"
   protocol: openid-connect
   publicClient: false
   redirectUris:
     - "https://portal.dev.apim.cab-i.com/*"
     - "https://portal.staging.apim.cab-i.com/*"
   webOrigins:
     - "https://portal.dev.apim.cab-i.com"
     - "https://portal.staging.apim.cab-i.com"
   standardFlowEnabled: true
   directAccessGrantsEnabled: false

   # Mappers pour claims JWT
   protocolMappers:
     - name: tenant_id
       protocol: openid-connect
       protocolMapper: oidc-usermodel-attribute-mapper
       config:
         user.attribute: tenant_id
         claim.name: tenant_id
         jsonType.label: String

     - name: roles
       protocol: openid-connect
       protocolMapper: oidc-usermodel-realm-role-mapper
       config:
         claim.name: roles
         multivalued: "true"
   ```

   **webMethods Portal - Configuration OIDC**:
   ```
   Portal Administration > Security > Identity Providers

   Provider Type: OpenID Connect
   Provider Name: Keycloak
   Discovery URL: https://keycloak.dev.apim.cab-i.com/realms/apim-platform/.well-known/openid-configuration
   Client ID: developer-portal
   Client Secret: *** (depuis Vault)
   Scope: openid profile email

   User Mapping:
   - Username: preferred_username
   - Email: email
   - Groups: tenant_id
   ```

4. **APIs Démo Pré-déployées** 🔲

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

5. **Workflow Beta Testeur** 🔲

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
   │  3. DEVELOPER PORTAL - CONSOMMATION APIs                                            │
   │     ┌─────────────────────────────────────────────────────────────────────────────┐ │
   │     │  Accès: https://portal.dev.apim.cab-i.com                                  │ │
   │     │  → SSO Keycloak (même session, pas de re-login)                            │ │
   │     │  • Voir les APIs publiées du tenant-demo                                   │ │
   │     │  • Créer une Application                                                    │ │
   │     │  • Souscrire à une API                                                      │ │
   │     │  • Obtenir les credentials (API Key)                                        │ │
   │     │  • Tester l'API via le Portal                                               │ │
   │     └─────────────────────────────────────────────────────────────────────────────┘ │
   │                                                                                      │
   └─────────────────────────────────────────────────────────────────────────────────────┘
   ```

6. **Permissions par Rôle sur les Interfaces** 🔲

   | Interface | CPI (demo-cpi) | DevOps (demo-devops) |
   |-----------|----------------|----------------------|
   | **UI DevOps** | | |
   | Voir APIs tenant | ✅ | ✅ |
   | Créer/Modifier API | ✅ | ✅ |
   | Supprimer API | ✅ | ❌ |
   | Déployer API | ✅ | ✅ |
   | Gérer membres tenant | ✅ | ❌ |
   | Voir traces pipeline | ✅ | ✅ |
   | **Developer Portal** | | |
   | Voir APIs publiées | ✅ | ✅ |
   | Créer Application | ✅ | ✅ |
   | Souscrire API | ✅ | ✅ |
   | Gérer souscriptions | ✅ | ❌ (ses propres apps) |
   | Approuver souscriptions | ✅ | ❌ |

7. **Checklist Déploiement Phase 6** 🔲

   - [ ] Créer tenant-demo dans `iam/tenants.yaml` + commit GitLab
   - [ ] Sync IAM → Keycloak (créer groupe + users)
   - [ ] Configurer client `developer-portal` dans Keycloak
   - [ ] Configurer OIDC dans webMethods Portal
   - [ ] Créer APIs démo (petstore, weather) dans GitOps
   - [ ] Déployer APIs démo sur Gateway DEV
   - [ ] Publier APIs démo sur Portal
   - [ ] Tester parcours complet avec demo-cpi
   - [ ] Tester parcours complet avec demo-devops
   - [ ] Documenter accès beta testeurs

8. **Credentials Beta Testeurs**

   | User | URL | Login | Password |
   |------|-----|-------|----------|
   | Demo CPI | https://devops.apim.cab-i.com | demo-cpi@cab-i.com | DemoCPI2024! |
   | Demo CPI | https://portal.dev.apim.cab-i.com | (SSO) | (SSO) |
   | Demo DevOps | https://devops.apim.cab-i.com | demo-devops@cab-i.com | DemoDevOps2024! |
   | Demo DevOps | https://portal.dev.apim.cab-i.com | (SSO) | (SSO) |

   > **Note**: Les credentials seront stockés dans Vault après validation beta.

9. **Documentation Utilisateur** 🔲

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

   La plateforme APIM CAB-I dispose de deux interfaces principales:

   | Interface | URL | Description |
   |-----------|-----|-------------|
   | UI DevOps | https://devops.apim.cab-i.com | Gestion des APIs, déploiements, monitoring |
   | Developer Portal | https://portal.dev.apim.cab-i.com | Catalogue APIs, souscriptions, documentation |

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
   5. **Publiez** sur le Developer Portal
   6. **Testez** l'API depuis le Portal
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

   **03-developer-portal-guide.md**:
   ```markdown
   # Guide Developer Portal

   ## Catalogue d'APIs

   Le Developer Portal affiche toutes les APIs publiées auxquelles vous avez accès.

   ### Rechercher une API
   - Utilisez la barre de recherche
   - Filtrez par catégorie ou tenant
   - Consultez la documentation OpenAPI intégrée

   ## Applications

   Une **Application** représente votre client qui va consommer des APIs.

   ### Créer une Application
   1. Allez dans **Mes Applications**
   2. Cliquez sur **+ Nouvelle Application**
   3. Donnez un nom et une description
   4. Votre Application est créée avec des credentials (API Key)

   ### Souscrire à une API
   1. Trouvez l'API dans le catalogue
   2. Cliquez sur **Souscrire**
   3. Sélectionnez votre Application
   4. Choisissez le plan (Basic, Premium, etc.)
   5. Attendez l'approbation (si nécessaire)

   ## Tester une API

   Le Portal intègre un client de test:
   1. Ouvrez la documentation de l'API
   2. Sélectionnez un endpoint
   3. Remplissez les paramètres
   4. Cliquez sur **Try it out**
   5. Visualisez la réponse

   ## Vos Credentials

   ### API Key
   - Visible dans **Mes Applications > [App] > Credentials**
   - À inclure dans le header `X-API-Key`

   ### Exemple cURL
   ```bash
   curl -X GET "https://gateway.dev.apim.cab-i.com/petstore/v2/pet/1" \
        -H "X-API-Key: YOUR_API_KEY"
   ```
   ```

   **04-api-lifecycle.md**:
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
       - Developer Portal: user-guide/03-developer-portal-guide.md
       - Cycle de Vie API: user-guide/04-api-lifecycle.md
       - Rôles & Permissions: user-guide/05-rbac-roles.md
       - Dépannage: user-guide/06-troubleshooting.md
     - Tutoriels:
       - Créer sa première API: tutorials/create-first-api.md
       - Déployer une API: tutorials/deploy-api.md
       - Consommer une API: tutorials/consume-api.md
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
   - [ ] Écrire 03-developer-portal-guide.md avec screenshots
   - [ ] Écrire 04-api-lifecycle.md
   - [ ] Écrire 05-rbac-roles.md
   - [ ] Écrire 06-troubleshooting.md (FAQ)
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

| Phase | Description | Durée Estimée |
|-------|-------------|---------------|
| Phase 1 | Kafka/Redpanda + AWX Automation | À planifier |
| Phase 2 | GitOps + Variables d'Environnement + IAM | À planifier |
| Phase 3 | Vault + Gateway Alias | À planifier |
| Phase 4 | OpenSearch + Monitoring | À planifier |
| Phase 5 | Multi-environnements (dev/staging/prod) | À planifier |
| Phase 6 | Demo Tenant + SSO Unifié + Documentation | À planifier |
| Phase 7 | Sécurité Opérationnelle (Batch Jobs) | À planifier |
