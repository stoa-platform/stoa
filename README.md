# STOA Platform - UI RBAC + GitOps + Kafka

Multi-tenant API Management Platform with Control-Plane UI, GitOps and Event-Driven Architecture.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CLIENTS                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────┐│
│  │Console (UI)  │  │  Developer   │  │  Third-party │  │ Partners ││
│  │ (Keycloak)   │  │   Portal     │  │   (OAuth2)   │  │ (OAuth2) ││
│  │ API Provider │  │ API Consumer │  │              │  │          ││
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └────┬─────┘│
└─────────┼─────────────────┼──────────────────┼──────────────┼──────┘
          │                 │                    │              │
          │                 │                    │              │
          ▼                 ▼                    ▼              ▼
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

### Access Flow

| Client | Path | Auth | Purpose |
|--------|------|------|---------|
| Console UI | `apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0/*` | Keycloak OIDC | API Provider (Tenant/API management) |
| Developer Portal | `apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0/*` | Keycloak OIDC | API Consumer (Browse, Subscribe, Test) |
| Third-party/M2M | `apis.stoa.cab-i.com/gateway/*` | OAuth2 Client Credentials | Business API access |
| Business APIs | `apis.stoa.cab-i.com/gateway/{api}/*` | API Key / OAuth2 | Runtime API calls |

## Components

| Component | Description | Technology | URL |
|-----------|-------------|------------|-----|
| Console UI | RBAC Interface for API Provider (management) | React + TypeScript | console.stoa.cab-i.com |
| **Developer Portal** | API Consumer Portal (browse, subscribe, test) | React + TypeScript + Vite | portal.stoa.cab-i.com |
| Control-Plane API | REST Backend with RBAC | FastAPI (Python) | api.stoa.cab-i.com |
| MCP Gateway | AI-Native API Access (MCP Protocol) | FastAPI + OPA | mcp.stoa.cab-i.com |
| Keycloak | Identity Provider (OIDC) | Keycloak | auth.stoa.cab-i.com |
| GitLab | GitOps Source of Truth | GitLab | gitlab.com |
| Kafka | Event streaming | Redpanda | (internal) |
| AWX | Automation/Orchestration | AWX/Ansible | awx.stoa.cab-i.com |
| webMethods Gateway | API Gateway runtime | webMethods | apis.stoa.cab-i.com |

## RBAC Roles

| Role | Tenants | APIs | Apps | Deploy | Users |
|------|---------|------|------|--------|-------|
| CPI Admin | CRUD | CRUD | CRUD | All | All |
| Tenant Admin | Read own | CRUD | CRUD | All | Own tenant |
| DevOps | Read own | CRU | CRU | All | - |
| Viewer | Read own | Read | Read | - | - |

## Structure GitOps

```
stoa-gitops/
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

## Project Structure

```
stoa/
├── control-plane-api/       # FastAPI backend
│   ├── src/
│   │   ├── auth/            # RBAC & Keycloak
│   │   ├── routers/         # API endpoints (+ gateway.py pour admin proxy)
│   │   └── services/        # Business logic (GitLab, Kafka, Gateway, etc.)
│   ├── Dockerfile
│   └── requirements.txt
├── control-plane-ui/        # React frontend (Console - API Provider)
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── contexts/
│   │   └── services/
│   ├── Dockerfile
│   └── package.json
├── portal/                  # Developer Portal (API Consumer)
│   ├── src/
│   │   ├── components/     # UI components (layout, testing, apps)
│   │   ├── pages/          # Routes (apis, tools, subscriptions, apps)
│   │   ├── contexts/       # Auth context (Keycloak OIDC)
│   │   ├── hooks/          # React Query hooks
│   │   └── services/       # API services
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
├── scripts/                 # Installation scripts
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
│  GitHub: stoa           │     │  GitLab: stoa-gitops        │
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
                                    │  ├── stoa-system             │
                                    │  ├── stoa-{tenant}-dev       │
                                    │  └── stoa-{tenant}-prod      │
                                    └─────────────────────────────┘
```

## Deployment

### 1. AWS Infrastructure

```bash
# Create S3/DynamoDB backend (one-time setup)
aws s3 mb s3://stoa-terraform-state-dev --region eu-west-1
aws dynamodb create-table \
  --table-name stoa-terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST

# Deploy the infrastructure
cd terraform/environments/dev
terraform init
terraform plan
terraform apply
```

### 2. Configuration kubectl

```bash
aws eks update-kubeconfig --name stoa-dev-cluster --region eu-west-1
```

### 3. Helm Deployment

```bash
# Namespace
kubectl create namespace stoa

# Secrets ECR
kubectl create secret docker-registry ecr-secret \
  --docker-server=848853684735.dkr.ecr.eu-west-1.amazonaws.com \
  --docker-username=AWS \
  --docker-password=$(aws ecr get-login-password) \
  -n stoa

# Control Plane API
helm upgrade --install control-plane-api ./charts/control-plane-api \
  --namespace stoa \
  --set secrets.KEYCLOAK_CLIENT_SECRET=xxx

# Control Plane UI
helm upgrade --install control-plane-ui ./charts/control-plane-ui \
  --namespace stoa
```

### 4. Build and Push Images

```bash
# Login ECR
aws ecr get-login-password --region eu-west-1 | docker login --username AWS --password-stdin 848853684735.dkr.ecr.eu-west-1.amazonaws.com

# Build and push API
cd control-plane-api
docker build -t control-plane-api .
docker tag control-plane-api:latest 848853684735.dkr.ecr.eu-west-1.amazonaws.com/control-plane-api:latest
docker push 848853684735.dkr.ecr.eu-west-1.amazonaws.com/control-plane-api:latest

# Build and push UI
cd ../control-plane-ui
npm install && npm run build
docker build -t control-plane-ui .
docker tag control-plane-ui:latest 848853684735.dkr.ecr.eu-west-1.amazonaws.com/control-plane-ui:latest
docker push 848853684735.dkr.ecr.eu-west-1.amazonaws.com/control-plane-ui:latest
```

## URLs

### Production Environment

| Service | URL | Description |
|---------|-----|-------------|
| Console UI | https://console.stoa.cab-i.com | API Provider interface (tenant/API management) |
| **Developer Portal** | https://portal.stoa.cab-i.com | API Consumer portal (browse, subscribe, test) |
| Control Plane API (direct) | https://api.stoa.cab-i.com | REST API backend (direct access) |
| **API Gateway Runtime** | https://apis.stoa.cab-i.com | APIs via Gateway (OIDC auth) |
| **MCP Gateway** | https://mcp.stoa.cab-i.com | AI-Native MCP Protocol endpoint |
| Keycloak (Auth) | https://auth.stoa.cab-i.com | Identity Provider (OIDC) |
| Keycloak Admin | https://auth.stoa.cab-i.com/admin/ | Keycloak admin console |
| API Gateway UI | https://gateway.stoa.cab-i.com/apigatewayui/ | Gateway console (admin: Administrator/manage) |
| **ArgoCD** | https://argocd.stoa.cab-i.com | GitOps CD (admin/demo) |
| **AWX (Ansible)** | https://awx.stoa.cab-i.com | Automation (admin/demo) |
| Vault | https://vault.stoa.cab-i.com | HashiCorp Vault (secrets) |
| Redpanda Console | `kubectl port-forward svc/redpanda-console 8080:8080 -n stoa-system` | Kafka administration (internal) |
| **GitLab GitOps** | https://gitlab.com/cab6961310/stoa-gitops | Source of Truth (tenants)

> **Note**: The UI uses the API via Gateway (`apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0`) to benefit from centralized OIDC authentication.

### STAGING Environment (coming soon)

| Service | URL |
|---------|-----|
| Control Plane UI | https://devops.staging.stoa.cab-i.com |
| Control Plane API | https://api.staging.stoa.cab-i.com |
| Keycloak | https://auth.staging.stoa.cab-i.com |
| API Gateway | https://gateway.staging.stoa.cab-i.com |

## Default Users (DEMO Instance)

### Keycloak Admin Console

| Username | Password | Role | Description |
|----------|----------|------|-------------|
| `admin` | `demo` | Super Admin | Full access to Keycloak console |

### Control Plane UI

| Username | Password | Role | Description |
|----------|----------|------|-------------|
| `admin@stoa.local` | `demo` | CPI Admin | Full platform access |

> **Note**: These credentials are for the demo instance. In production, use strong passwords stored in AWS Secrets Manager.

## Estimated AWS Costs

### Architecture with Shared OpenSearch (DEV + STAGING)

| Service | Type | Monthly Cost |
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

### Connection Services (Internal URLs)

| Service | Internal URL | Notes |
|---------|--------------|-------|
| Elasticsearch | `elasticsearch-master:9200` | No auth (xpack.security.enabled: false) |
| Redpanda (Kafka) | `redpanda.stoa-system.svc.cluster.local:9092` | No auth |
| Keycloak | `https://auth.stoa.cab-i.com` | Realm: `stoa`, Client: `control-plane-api` |

### Control Plane UI Configuration - Tenant Mapping

The Control Plane UI retrieves tenant information from the Keycloak JWT token.

**Read-only information available**:
- Tenant name
- Associated CPI Admin
- Assigned DevOps

**Git configuration file** (CPI/DevOps/Tenant mapping):
```yaml
# stoa-gitops/config/tenant-mapping.yaml
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

> **Note**: CPI/DevOps/Tenant matching is done via configuration file in the GitOps repo. A future version may integrate this config directly into Keycloak (custom claims).

### Keycloak as Identity Provider (IdP)

Keycloak is configured as central IdP for OIDC authentication:

**Realm Configuration**:
- **Realm**: `stoa`
- **URL**: `https://auth.stoa.cab-i.com/realms/stoa`
- **Discovery**: `https://auth.stoa.cab-i.com/realms/stoa/.well-known/openid-configuration`

**Configured Clients**:
| Client ID | Type | Usage |
|-----------|------|-------|
| `control-plane-api` | Confidential | Backend API authentication |
| `control-plane-ui` | Public | Console SPA (PKCE) - API Provider |
| `stoa-portal` | Public | Developer Portal SPA (PKCE) - API Consumer |
| `api-gateway` | Confidential | Gateway JWT validation |

**Realm Roles**:
| Role | Description |
|------|-------------|
| `cpi-admin` | Full platform administrator |
| `tenant-admin` | Admin for own tenant |
| `devops` | API deployment and promotion |
| `viewer` | Read-only access |

**Custom JWT Claims** (to implement):
```json
{
  "sub": "user-uuid",
  "preferred_username": "admin@stoa.local",
  "realm_access": { "roles": ["cpi-admin"] },
  "tenant_id": "tenant-finance",
  "tenant_role": "admin"
}
```

### Resource Estimation - Final Architecture

**Current configuration (DEV)**: 3x t3.large (2 vCPU / 8GB RAM each)

**Resources per component**:
| Component | CPU Request | Memory Request | Replicas | Total CPU | Total RAM |
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

**K8s system reserve**: ~600m CPU, ~1Gi RAM per node

**Available capacity** (3x t3.large = 6 vCPU / 24GB):
- CPU: 6000m - 1800m (system 3 nodes) = 4200m available → ✅ 2700m used (64%)
- RAM: 24GB - 3GB (system) = 21GB available → ✅ 7.8GB used (37%)

**Future scaling options**:
| Option | Monthly Cost | Capacity | Recommendation |
|--------|--------------|----------|----------------|
| Current: 3x t3.large | ~$180 | 6 vCPU / 24GB | ✅ DEV (current with AWX) |
| 3x t3.xlarge | ~$360 | 12 vCPU / 48GB | ✅ STAGING + replicas |
| 4x t3.large | ~$240 | 8 vCPU / 32GB | ✅ PROD HA |

> **Current DEV configuration**: 3x t3.large with AWX included. Pods remain standalone (replicas=1).
>
> **STAGING recommendation**: Upgrade to 3x t3.xlarge to support replicas=2 on critical components.
>
> **Gateway Cluster Note**: To scale the Gateway beyond 1 replica, Ignite must be configured for clustering.

### Network Security

Gateway and Portal pods are isolated from external network via NetworkPolicies:
- Blocked access to Internet (metering.softwareag.cloud, etc.)
- Communication allowed only within the cluster (VPC CIDR)

### Options Comparison

| Configuration | Cost/month | Advantages |
|--------------|-----------|-----------|
| ES 7.2.0 on EKS + OpenSearch analytics | ~$220 | Multi-tenant analytics, guaranteed compatibility |
| Production (ES 7 cluster + OpenSearch) | ~$280 | Full high availability |

## webMethods References

- [webMethods API Gateway](https://github.com/ibm-wm-transition/webmethods-api-gateway) - Official documentation
- [webMethods API Gateway DevOps](https://github.com/SoftwareAG/webmethods-api-gateway-devops) - CI/CD and deployment scripts
- [Docker Compose Samples](https://github.com/ibm-wm-transition/webmethods-api-gateway/tree/master/samples/docker/deploymentscripts) - Docker examples

---

## Current State vs Target Architecture

### Deployed Components ✅

| Component | Status | Notes |
|-----------|--------|-------|
| EKS Cluster | ✅ Deployed | stoa-dev-cluster |
| VPC / Subnets | ✅ Deployed | 10.0.0.0/16 |
| RDS PostgreSQL | ✅ Deployed | db.t3.micro |
| ECR Repositories | ✅ Deployed | control-plane-api, control-plane-ui, stoa/* |
| Nginx Ingress | ✅ Deployed | with cert-manager |
| Cert-Manager | ✅ Deployed | Let's Encrypt prod |
| Keycloak | ✅ Deployed | https://auth.stoa.cab-i.com |
| Control-Plane API | ✅ Deployed | FastAPI backend |
| Control-Plane UI | ✅ Deployed | React frontend |
| Elasticsearch 8.11 | ✅ Deployed | On EKS, cluster SAG_EventDataStore (ES 8+ required for Gateway 10.15) |
| webMethods Gateway | ✅ Deployed | Lean trial image 10.15 |
| NetworkPolicies | ✅ Deployed | Blocks Internet access (metering.softwareag.cloud) |
| EBS CSI Driver | ✅ Deployed | For persistent volumes |
| **Redpanda (Kafka)** | ✅ Deployed | Event streaming, 1 broker, Redpanda Console |
| **Kafka Topics** | ✅ Deployed | api-created/updated/deleted, deploy-requests/results, audit-log, notifications |
| **Kafka Producer** | ✅ Deployed | Integrated in Control-Plane API (event emission on CRUD) |
| **AWX (Ansible Tower)** | ✅ Deployed | AWX 24.6.1 via Operator, https://awx.stoa.cab-i.com |

### Components To Deploy 🔲

| Component | Priority | Description |
|-----------|----------|-------------|
| AWX Job Templates | High | Jobs for API deployment (deploy-api, sync-gateway, etc.) |
| GitLab (GitOps) | High | Source of truth for configs |
| **ArgoCD** | High | GitOps operator, automatic K8s sync |
| Vault | Medium | Secrets management (clientSecret, apiKey) |
| Grafana + Prometheus | Medium | Monitoring and alerting |
| OpenSearch Analytics | Low | Multi-tenant analytics (Global Policies) |

### Next Steps - Roadmap

#### Phase 1: Event-Driven Architecture ✅ COMPLETED (Dec 21, 2024)

> **Infrastructure**: Nodes scaled to 3x t3.large (2 CPU / 8GB RAM each) to support Redpanda + AWX.

1. **Redpanda Deployed** ✅
   - Kafka-compatible, 1 broker on EKS
   - Redpanda Console for administration
   - Storage: 10GB persistent (EBS gp2)
   - Internal endpoint: `redpanda.stoa-system.svc.cluster.local:9092`

2. **Kafka Topics Created** ✅
   - `api-created` - API creation events
   - `api-updated` - API modification events
   - `api-deleted` - API deletion events
   - `deploy-requests` - Deployment requests
   - `deploy-results` - Deployment results
   - `audit-log` - Audit logs
   - `notifications` - Real-time notifications

3. **Kafka Producer Integrated** ✅
   - Control-Plane API emits Kafka events on each CRUD operation
   - Topics used: `api-created`, `api-updated`, `api-deleted`, `notifications`
   - Automatic audit events on `audit-log`
   - Connection: `redpanda.stoa-system.svc.cluster.local:9092`

   **End-to-End Pipeline Dashboard**:
   ```
   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
   │ Control-Plane│ → │   Kafka    │ → │   AWX/Ansible│ → │   Gateway   │
   │   (CRUD)    │    │  (Events)   │    │  (Deploy)   │    │  (Runtime)  │
   └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
         ✅                 ✅                  ✅                 ✅
   ```

4. **AWX (Ansible Tower)** ✅ DEPLOYED + CONFIGURED
   - AWX 24.6.1 via AWX Operator 2.19.1
   - URL: https://awx.stoa.cab-i.com
   - Login: admin / demo
   - Database: RDS PostgreSQL (shared with Keycloak)

   **Job Templates Configured** ✅:
   - `Deploy API` (id: 8) - Deploys an API on the Gateway
   - `Sync Gateway` (id: 9) - Synchronizes Gateway config
   - `Rollback API` (id: 11) - Rollback on failure

   **Kafka Integration** ✅:
   - Deployment Worker in Control-Plane API
   - Consumer on `deploy-requests` topic
   - AWX job monitoring with publish to `deploy-results`

5. **GitLab Webhook** ✅ CONFIGURED
   - Endpoint: `POST /webhooks/gitlab`
   - Supported events: Push, Merge Request, Tag Push
   - Auto-deploy on push to `main` branch
   - Configuration: see [docs/GITOPS-SETUP.md](docs/GITOPS-SETUP.md)

6. **Control-Plane UI** ✅ FUNCTIONAL
   - React interface with Keycloak authentication (PKCE)
   - Pages: Dashboard, Tenants, APIs, Applications, Deployments, Monitoring
   - URL: https://console.stoa.cab-i.com

7. **Variabilized Configuration** ✅ (Dec 21, 2024)
   - **UI** ([config.ts](control-plane-ui/src/config.ts)): All URLs and configs via `VITE_*` env vars
   - **API** ([config.py](control-plane-api/src/config.py)): Centralized settings with pydantic-settings
   - **Dockerfiles**: Build args for environment-specific customization

   **Available UI Variables**:
   | Variable | Description | Default |
   |----------|-------------|---------|
   | `VITE_BASE_DOMAIN` | Base domain | `stoa.cab-i.com` |
   | `VITE_API_URL` | Backend API URL | `https://api.{domain}` |
   | `VITE_KEYCLOAK_URL` | Keycloak URL | `https://auth.{domain}` |
   | `VITE_KEYCLOAK_REALM` | Keycloak Realm | `stoa` |
   | `VITE_GATEWAY_URL` | Gateway URL | `https://gateway.{domain}` |
   | `VITE_AWX_URL` | AWX URL | `https://awx.{domain}` |
   | `VITE_ENABLE_*` | Feature flags | `true` |

   **Available API Variables**:
   | Variable | Description | Default |
   |----------|-------------|---------|
   | `BASE_DOMAIN` | Base domain | `stoa.cab-i.com` |
   | `KEYCLOAK_URL` | Keycloak URL | `https://auth.{domain}` |
   | `KEYCLOAK_REALM` | Realm | `stoa` |
   | `KAFKA_BOOTSTRAP_SERVERS` | Kafka brokers | `redpanda:9092` |
   | `AWX_URL` | AWX URL | `https://awx.{domain}` |
   | `CORS_ORIGINS` | Allowed CORS origins | `https://devops.{domain}` |
   | `LOG_LEVEL` | Log level | `INFO` |

8. **PKCE Authentication** ✅ (Dec 21, 2024)
   - Keycloak 25+ requires PKCE for public clients
   - `oidc-client-ts` configuration with `response_type: 'code'` and `pkce_method: 'S256'`
   - Functional login via https://console.stoa.cab-i.com

#### Phase 2: GitOps + Environment Variables (High Priority)

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
   - Repository `stoa-gitops`
   - Structure: `tenants/{tenant}/apis/{api}/`
   - Branches: `main` (prod), `staging`, `dev`

2. **Deploy ArgoCD** 🔲
   - Helm chart: `argo/argo-cd`
   - ApplicationSets for multi-tenant
   - Automatic sync on GitLab push
   - Custom health checks for Gateway
   ```yaml
   # ArgoCD Application example
   apiVersion: argoproj.io/v1alpha1
   kind: Application
   metadata:
     name: stoa-tenant-finance
   spec:
     source:
       repoURL: https://gitlab.com/stoa/stoa-gitops
       path: tenants/tenant-finance
     destination:
       server: https://kubernetes.default.svc
     syncPolicy:
       automated:
         prune: true
         selfHeal: true
   ```

3. **Integrate Git in Control-Plane API**
   - Automatic commit on CRUD
   - Bidirectional sync
   - Git clone/pull via GitPython

4. **Webhooks GitLab → Control-Plane**
   - External changes synchronization
   - Trigger ArgoCD sync

5. **Environment Variables Management** 🔲

   **Problem**: An API must point to different backends per environment, without secrets in Git.

   ```
   ┌─────────────────────────────────────────────────────────────────────┐
   │  payment-api doit pointer vers :                                     │
   │    DEV     → https://payment-dev.internal.cab-i.com                  │
   │    STAGING → https://payment-staging.internal.cab-i.com              │
   │    PROD    → https://payment.internal.cab-i.com                      │
   │                                                                       │
   │  ✅ Solution: Templates with placeholders + Vault for secrets        │
   └─────────────────────────────────────────────────────────────────────┘
   ```

   **Extended GitOps Structure**:
   ```
   stoa-gitops/
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

   **API Template Example (api.yaml)**:
   ```yaml
   apiVersion: stoa.cab-i.com/v1
   kind: API
   metadata:
     name: payment-api
     tenant: tenant-finance
   spec:
     backend:
       url: "${BACKEND_URL}"                    # Resolved at deployment
       timeout: "${BACKEND_TIMEOUT:30s}"        # Default value: 30s
       authentication:
         type: "${BACKEND_AUTH_TYPE:oauth2}"
         credentials:
           clientIdRef: "${BACKEND_CLIENT_ID_REF}"      # Vault reference
           clientSecretRef: "${BACKEND_CLIENT_SECRET_REF}"
   ```

   **Environment Configuration Example (dev.yaml)**:
   ```yaml
   apiVersion: stoa.cab-i.com/v1
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

   **GitOps IAM Structure**:
   ```
   stoa-gitops/
   ├── iam/                              # Identity & Access Management
   │   ├── tenants.yaml                  # Tenants + members definition
   │   ├── global-admins.yaml            # Global CPI Admins
   │   └── service-accounts.yaml         # CI/CD, monitoring accounts
   │
   └── tenants/
       └── ...
   ```

   **tenants.yaml Example**:
   ```yaml
   apiVersion: stoa.cab-i.com/v1
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
             addedBy: "admin@stoa.local"
         devops:                            # Deploy & Promote
           - email: "pierre.durand@cab-i.com"
             name: "Pierre Durand"
             addedAt: "2024-01-20T14:00:00Z"
             addedBy: "jean.dupont@cab-i.com"
         viewers:                           # Read-only
           - email: "audit@cab-i.com"
             name: "Audit Team"
             addedAt: "2024-01-15T10:00:00Z"
             addedBy: "admin@stoa.local"
   ```

   **global-admins.yaml Example**:
   ```yaml
   apiVersion: stoa.cab-i.com/v1
   kind: GlobalAdminRegistry
   metadata:
     name: global-admins

   admins:
     - email: "admin@stoa.local"
       name: "Platform Admin"
       role: "cpi-admin"
       permissions: ["tenants:*", "apis:*", "users:*"]
   ```

   **IAM Sync Service** (CronJob every 5 min):
   - Parse `iam/tenants.yaml` from Git
   - Detect changes (diff)
   - Synchronize to Keycloak (users, groups, roles)
   - Publish `iam-sync` event to Kafka

   **IAM API Endpoints**:
   | Endpoint | Description |
   |----------|-------------|
   | `GET /v1/iam/tenants/{id}/members` | List tenant members |
   | `POST /v1/iam/tenants/{id}/members` | Add a member (Git commit + sync) |
   | `DELETE /v1/iam/tenants/{id}/members` | Remove a member |
   | `POST /v1/iam/sync` | Force Git → Keycloak synchronization |

   **Member Addition Workflow**:
   ```
   1. CPI adds a member via UI
            ↓
   2. API updates iam/tenants.yaml (Git commit)
            ↓
   3. IAM Sync CronJob (5 min) or immediate sync
            ↓
   4. Keycloak: User + Group + Role
            ↓
   5. User logs in → JWT with tenant_id + roles
   ```

   **Phase 2 (Target) - Enterprise Directory**:
   - LDAP/AD Federation in Keycloak
   - AD Groups: `GRP_APIM_{TENANT}_{ROLE}` (e.g., `GRP_APIM_FINANCE_CPI`)
   - Git = Override for external users and service accounts
   - Automatic department → tenant mapping

#### Phase 2.5: E2E Validation - COMPLETED ✅ (Dec 22, 2024)

> **Objective**: Validate the complete GitOps → Keycloak → Gateway flow with APIM tenant admin.

1. **Gateway OIDC Configuration** ✅
   - External Authorization Server `KeycloakOIDC` configured in Gateway
   - OAuth2 Strategies per application with JWT validation
   - Standardized scope mappings: `{AuthServer}:{Tenant}:{Api}:{Version}:{Scope}`
   - Secured APIs: Control-Plane-API, Gateway-Admin-API

2. **Gateway Admin Service** ✅
   - OIDC Proxy to Gateway administration (port 5555)
   - Token forwarding: User JWT transmitted to Gateway for audit trail
   - Basic Auth fallback for legacy compatibility
   - Router `/v1/gateway/*` in Control-Plane API
   - Config: `GATEWAY_USE_OIDC_PROXY=True` (default)

   **Available Endpoints**:
   | Endpoint | Description |
   |----------|-------------|
   | `GET /v1/gateway/apis` | Liste les APIs Gateway |
   | `POST /v1/gateway/apis` | Importe une API (OpenAPI spec) |
   | `GET /v1/gateway/applications` | Liste les applications |
   | `PUT /v1/gateway/apis/{id}/activate` | Active une API |
   | `POST /v1/gateway/configure-oidc` | Configure OIDC pour une API |

3. **Secrets Security** ✅ (AWS Secrets Manager + K8s)

   **Secrets Strategy**:
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
   │  Path: stoa/{env}/{secret-name}       Path: secret/data/{env}/{tenant}   │
   │  Managed by: Terraform                Managed by: Vault / K8s External   │
   └─────────────────────────────────────────────────────────────────────────┘
   ```

   **Terraform Module** (`terraform/modules/secrets/`):
   - Automatic secure password generation
   - Outputs for External Secrets Operator
   - Recovery window: 0 (dev), 30 days (prod)

   **Ansible Configuration** (`ansible/vars/secrets.yaml`):
   - Centralized variables for all playbooks
   - Mandatory validation of critical secrets
   - Support for env / Vault lookup

4. **STOA Platform Tenant** ✅
   - Admin tenant with cross-tenant access
   - User: `stoaadmin@cab-i.com` (role: cpi-admin)
   - Structure in GitLab stoa-gitops

5. **Ansible Playbooks** ✅
   - `provision-tenant.yaml` - Creates Keycloak groups, users, K8s namespaces
   - `register-api-gateway.yaml` - OpenAPI import, OIDC, rate limiting, activation
   - `configure-gateway-oidc.yaml` - Complete OIDC configuration
   - `deploy-api.yaml` - API import with OpenAPI 3.1→3.0 conversion + activation
   - All playbooks secured with `vars_files` (zero hardcoding)

6. **AWX Job Templates** ✅
   - `Provision Tenant` (ID: 12) - Complete tenant provisioning
   - `Register API Gateway` (ID: 13) - API registration in Gateway
   - `Deploy API` (ID: 8) - API import via OIDC proxy with OpenAPI conversion

7. **OpenAPI 3.1.0 Compatibility** ✅ (Dec 23, 2024)
   - webMethods Gateway 10.15 does not support OpenAPI 3.1.0
   - Automatic 3.1.x → 3.0.0 conversion in `deploy-api.yaml`
   - Native swagger 2.0 and OpenAPI 3.0.x support
   - POST /v1/gateway/apis - Proxy endpoint for API import
   - Test validated: Control-Plane-API-E2E v2.2 deployed and activated

#### Phase 3: Secrets & Gateway Alias (Medium Priority)

**Hybrid Approach: Git + Gateway Alias**

**webMethods Gateway Aliases** allow storing endpoints and credentials separately from APIs. The hybrid approach combines Git as source of truth with Aliases for runtime management.

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
│  │    └── credentials: *** (from Vault)                                 │    │
│  │                                                                      │    │
│  │  API: payment-api → backend_alias: payment-backend-dev               │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

1. **Deploy HashiCorp Vault** 🔲
   - Dynamic secrets for OAuth2 clients
   - API Keys rotation
   - AppRole per environment
   - Structure: `secret/data/{env}/{api}#key`

2. **GitOps Structure with Aliases** 🔲
   ```
   stoa-gitops/
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
   ├── aliases/                              # Gateway Alias definitions
   │   ├── dev/
   │   │   ├── payment-backend.yaml
   │   │   └── invoice-backend.yaml
   │   ├── staging/
   │   │   └── payment-backend.yaml
   │   └── prod/
   │       └── payment-backend.yaml
   ```

3. **Gateway Alias Definition (aliases/dev/payment-backend.yaml)** 🔲
   ```yaml
   apiVersion: stoa.cab-i.com/v1
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

4. **AWX Jobs for Alias Management** 🔲

   | Job | Trigger | Action |
   |-----|---------|--------|
   | `sync-alias` | Change in `aliases/**/*.yaml` | Create/Update alias on Gateway with Vault credentials |
   | `deploy-api` | Change in `apis/**/api.yaml` | Deploy API (uses existing alias) |
   | `rotate-credentials` | Scheduled (cron) or Manual | Refresh Vault credentials → Gateway Alias |
   | `full-deploy` | New tenant/API | sync-alias + deploy-api |

5. **Integrate Vault in Control-Plane API** 🔲
   - VaultService to retrieve secrets
   - Resolution of `vault:path#key` references
   - Cache with TTL for performance

6. **Benefits of the Hybrid Approach**

   | Aspect | Benefit |
   |--------|---------|
   | **Git = Source of Truth** | Everything versioned, auditable, Git rollback possible |
   | **Alias = Abstraction** | API decoupled from backend, simplified promotion |
   | **Credentials Rotation** | Update alias without touching the deployed API |
   | **No Drift** | Git defines aliases, AWX synchronizes to Gateway |
   | **Zero-Change Promotion** | Same API.yaml, only alias changes per env |

7. **DEV → STAGING Promotion Workflow**
   ```
   ┌─────────────────────────────────────────────────────────────────────────────┐
   │  1. API identical (api.yaml doesn't change)                                  │
   │  2. Only environments/staging.yaml differs: BACKEND_ALIAS: payment-backend-staging │
   │  3. payment-backend-staging alias already exists (provisioned by sync-alias) │
   │  4. AWX deploy-api resolves ${BACKEND_ALIAS} → payment-backend-staging       │
   │  ✅ Promotion without code modification, credentials secured                │
   └─────────────────────────────────────────────────────────────────────────────┘
   ```

#### Phase 4: Observability with OpenSearch (Medium Priority)

Complete observability stack for STOA Platform using **Amazon OpenSearch** for centralized storage of traces and metrics.

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
│  │  ├── stoa-traces-*       (Pipeline traces GitLab→Kafka→AWX→Gateway)  │    │
│  │  ├── stoa-logs-*         (Application logs)                          │    │
│  │  ├── stoa-metrics-*      (Time-series metrics)                       │    │
│  │  └── stoa-analytics-*    (API usage analytics par tenant)            │    │
│  │                                                                       │    │
│  │  Features:                                                            │    │
│  │  ├── Full-text search on commit messages, errors                     │    │
│  │  ├── Real-time aggregations (pipeline stats)                         │    │
│  │  ├── Automatic retention (30 days traces, 7 days logs)               │    │
│  │  └── Built-in alerting (anomaly detection)                           │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                              │                                                │
│                              ▼                                                │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │                    VISUALIZATION LAYER                                │    │
│  │                                                                       │    │
│  │  ┌────────────────────────────┐  ┌────────────────────────────┐      │    │
│  │  │   OpenSearch Dashboards    │  │    Control-Plane UI         │      │    │
│  │  │   (Kibana-compatible)      │  │    Monitoring Page          │      │    │
│  │  │   • Pre-built dashboards   │  │    • Pipeline timeline      │      │    │
│  │  │   • Alerting rules         │  │    • Real-time stats        │      │    │
│  │  │   • Anomaly detection      │  │    • Drill-down by trace    │      │    │
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
              │  Index: stoa-traces-2024.12                                 │
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

1. **Amazon OpenSearch Service** (~$35/month)
   - Instance: t3.small.search (1 shared node DEV+STAGING)
   - Storage: 20GB EBS gp3
   - Indices:
     - `stoa-traces-YYYY.MM` - Pipeline traces (30 days retention)
     - `stoa-logs-YYYY.MM.DD` - Application logs (7 days retention)
     - `stoa-metrics-*` - Metrics (14 days retention)
     - `stoa-analytics-{tenant}` - API Gateway analytics per tenant

2. **Control-Plane API → OpenSearch Integration**
   - OpenSearchService in `services/opensearch_service.py`
   - PipelineTrace indexing at each step
   - Real-time status update
   - Full-text search on commit messages, errors

3. **FluentBit** (Log Shipping)
   - DaemonSet sur EKS
   - Parse logs JSON de tous les pods
   - Enrichissement: tenant_id, api_name, trace_id
   - Output vers OpenSearch
   - Helm: `fluent/fluent-bit`

4. **Prometheus + Remote Write** (Metrics)
   - Prometheus for local collection
   - Remote Write to OpenSearch (via Prometheus Exporter)
   - Metrics: latency, error_rate, requests/sec
   - Alerting: AlertManager → OpenSearch → Slack

5. **OpenSearch Dashboards** (Visualization)
   - URL: https://opensearch.stoa.cab-i.com/_dashboards
   - Pre-built dashboards:
     - **Pipeline Overview**: Success rate, avg duration, errors/hour
     - **Deployment History**: Timeline per tenant/API
     - **Error Analysis**: Top errors, associated traces
     - **Commit Activity**: GitLab pushes heatmap
   - Anomaly Detection: Built-in ML for spike detection

6. **Control-Plane UI - Monitoring Page** (✅ Already implemented)
   - Read from OpenSearch instead of memory
   - Interactive timeline per trace
   - Filters: tenant, status, date range
   - CSV export of traces

7. **API Traces Endpoints** (to be updated)
   ```python
   # Currently: in-memory store (TraceStore)
   # Target: OpenSearch queries

   GET /v1/traces                    # OpenSearch query
   GET /v1/traces/{trace_id}         # OpenSearch get
   GET /v1/traces/stats              # OpenSearch aggregations
   GET /v1/traces/search             # Full-text search (new)
   ```

8. **Index Templates & ILM**
   ```json
   {
     "index_patterns": ["stoa-traces-*"],
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
   - Pipeline failed > 3 times/hour → Slack #stoa-alerts
   - Duration P95 > 30s → Warning
   - AWX job timeout → Critical
   - Kafka consumer lag > 100 → Warning

**OpenSearch vs in-memory Benefits**:
| Aspect | In-Memory (current) | OpenSearch (target) |
|--------|-------------------|-------------------|
| Persistence | ❌ Lost on restart | ✅ Persistent |
| Search | ❌ Basic | ✅ Full-text, aggregations |
| Retention | ❌ Limited (500 traces) | ✅ Configurable (30 days+) |
| Scalability | ❌ Single node | ✅ Cluster possible |
| Dashboards | ❌ Custom UI only | ✅ OpenSearch Dashboards |
| Cost | ✅ Free | ⚠️ ~$35/month |

**Observability URLs**:
| Service | URL |
|---------|-----|
| OpenSearch Dashboards | https://opensearch.stoa.cab-i.com/_dashboards |
| Control-Plane Monitoring | https://console.stoa.cab-i.com/monitoring |
| Prometheus (interne) | prometheus.stoa-system.svc.cluster.local:9090 |

#### Phase 4.5: Jenkins Orchestration Layer (High Priority - Enterprise)

**Objective**: Integrate Jenkins as an auditable orchestration layer between Kafka and AWX for an enterprise vision with complete traceability, approval gates and reporting.

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                      JENKINS ORCHESTRATION LAYER                                      │
│                                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────────────┐    │
│   │                         ENTERPRISE ARCHITECTURE                              │    │
│   │                                                                              │    │
│   │   ┌──────────────┐                                                          │    │
│   │   │     GUI      │  ← Business UI (API product, tenant, access)            │    │
│   │   └──────┬───────┘                                                          │    │
│   │          │ REST                                                              │    │
│   │   ┌──────▼────────┐                                                         │    │
│   │   │ Backend Python│  ← rules, validations, RBAC                            │    │
│   │   └──────┬────────┘                                                         │    │
│   │          │ EVENT (intent)                                                    │    │
│   │   ┌──────▼────────┐                                                         │    │
│   │   │     Kafka     │  ← event source                                         │    │
│   │   └──────┬────────┘                                                         │    │
│   │          │ subscribe                                                         │    │
│   │   ┌──────▼────────┐                                                         │    │
│   │   │    Jenkins    │  ← AUDITABLE ORCHESTRATOR                               │    │
│   │   │               │     • Pipeline as Code (Jenkinsfile)                    │    │
│   │   │               │     • Approval Gates                                     │    │
│   │   │               │     • Complete Audit Trail                              │    │
│   │   │               │     • Parallel execution                                │    │
│   │   │               │     • Retry & rollback                                  │    │
│   │   └──────┬────────┘                                                         │    │
│   │          │ trigger                                                           │    │
│   │   ┌──────▼────────┐                                                         │    │
│   │   │      AWX      │  ← infra / gateway EXECUTION                            │    │
│   │   └───────────────┘                                                         │    │
│   │                                                                              │    │
│   └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                       │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**Benefits of Jenkins as Orchestrator**:

| Aspect | Without Jenkins (Kafka→AWX direct) | With Jenkins |
|--------|--------------------------------|--------------|
| **Auditability** | Scattered logs | Centralized console, Blue Ocean UI |
| **Approval Gates** | ❌ No gates | ✅ `input` steps, RBAC approvers |
| **Retry/Rollback** | ❌ Manual | ✅ Stage retry, automatic rollback |
| **Parallelism** | ❌ Sequential | ✅ `parallel` stages |
| **Notification** | ❌ Custom | ✅ Native Slack/Email/Teams |
| **Compliance** | ❌ Kafka logs | ✅ Build artifacts, audit trail |
| **Pipeline as Code** | ❌ AWX config | ✅ Git-versioned Jenkinsfile |

**Detailed Architecture**:

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

**Jenkins Deployment on EKS**:

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

  # Essential plugins
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
              authorizationServerUrl: "https://auth.stoa.cab-i.com/realms/stoa"
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
  # Dynamic Kubernetes agents
  podTemplates:
    - name: "stoa-agent"
      label: "stoa-agent"
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
  hostName: jenkins.stoa.cab-i.com
  tls:
    - secretName: jenkins-tls
      hosts:
        - jenkins.stoa.cab-i.com
```

**Kafka Consumer → Jenkins Trigger**:

```python
# jenkins-trigger-service/main.py
from kafka import KafkaConsumer
import requests
import json

JENKINS_URL = "https://jenkins.stoa.cab-i.com"
JENKINS_TOKEN = os.getenv("JENKINS_API_TOKEN")

consumer = KafkaConsumer(
    'api.lifecycle.events',
    bootstrap_servers=['redpanda.stoa-system.svc.cluster.local:9092'],
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
            auth=("stoa-service", JENKINS_TOKEN),
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
    agent { label 'stoa-agent' }

    parameters {
        string(name: 'TENANT_ID', description: 'Tenant ID')
        string(name: 'API_NAME', description: 'API Name')
        string(name: 'API_VERSION', description: 'API Version')
        string(name: 'ENVIRONMENT', description: 'Target Environment')
        string(name: 'TRACE_ID', description: 'Trace ID for correlation')
    }

    environment {
        AWX_HOST = 'https://awx.stoa.cab-i.com'
        AWX_TOKEN = credentials('awx-api-token')
        KAFKA_BOOTSTRAP = 'redpanda.stoa-system.svc.cluster.local:9092'
        SLACK_CHANNEL = '#stoa-deployments'
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

                    // Verify that the API exists in GitLab
                    def apiSpec = sh(
                        script: """
                            curl -s "https://api.stoa.cab-i.com/v1/tenants/${TENANT_ID}/apis/${API_NAME}" \
                                -H "Authorization: Bearer ${API_TOKEN}"
                        """,
                        returnStdout: true
                    ).trim()

                    if (!apiSpec) {
                        error "API ${API_NAME} not found for tenant ${TENANT_ID}"
                    }

                    // Publish Kafka event: validation-passed
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
                    // Wait for the API to be accessible
                    retry(5) {
                        sleep(time: 10, unit: 'SECONDS')

                        def healthCheck = sh(
                            script: """
                                curl -s -o /dev/null -w '%{http_code}' \
                                    "https://gateway.${params.ENVIRONMENT}.stoa.cab-i.com/${params.TENANT_ID}/${params.API_NAME}/health"
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
                            --api-url="https://gateway.${params.ENVIRONMENT}.stoa.cab-i.com/${params.TENANT_ID}/${params.API_NAME}" \
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
    agent { label 'stoa-agent' }

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
                        // Retrieve previous version from GitLab
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
                    // Health check after rollback
                    retry(3) {
                        sleep 5
                        sh """
                            curl -f "https://gateway.${params.ENVIRONMENT}.stoa.cab-i.com/${params.TENANT_ID}/${params.API_NAME}/health"
                        """
                    }
                }
            }
        }
    }

    post {
        always {
            script {
                // Create an incident ticket for rollback
                sh """
                    curl -X POST "https://api.stoa.cab-i.com/v1/incidents" \
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

**Jenkins Shared Library** (for reuse):

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
        channel: '#stoa-deployments',
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

**Jenkins Dashboard - Metrics**:

| Metric | Description | Target |
|--------|-------------|--------|
| **Deployment Success Rate** | % successful pipelines | > 95% |
| **Mean Time to Deploy (MTTD)** | Average pipeline duration | < 10 min |
| **Approval Wait Time** | Approval waiting time | < 4h |
| **Rollback Frequency** | Rollbacks/week | < 2 |
| **Pipeline Queue Time** | Queue waiting time | < 5 min |

**Phase 4.5 Checklist**:
- [ ] Jenkins deployed on EKS (Helm jenkins/jenkins)
- [ ] JCasC Configuration (Jenkins Configuration as Code)
- [ ] Keycloak SSO Integration (OIDC)
- [ ] Kafka Consumer → Jenkins Trigger Service
- [ ] Jenkinsfile `deploy-api` with approval gates
- [ ] Jenkinsfile `rollback-api` with emergency bypass
- [ ] Jenkinsfile `promote-api` for cross-env promotion
- [ ] Jenkinsfile `delete-api` with confirmation
- [ ] Shared Library (kafkaPublish, awxLaunch, notifyDeployment)
- [ ] Blue Ocean UI accessible
- [ ] Slack notifications configured
- [ ] Jenkins metrics dashboard
- [ ] AWX/Kafka/Keycloak credentials in Jenkins Credentials Store
- [ ] Jenkins config backup (PVC + S3)

**URLs Jenkins**:
| Service | URL |
|---------|-----|
| Jenkins UI | https://jenkins.stoa.cab-i.com |
| Blue Ocean | https://jenkins.stoa.cab-i.com/blue |
| API | https://jenkins.stoa.cab-i.com/api/json |

#### Phase 5: Multi-Environment (Low Priority)
1. **STAGING Environment**
   - DEV → STAGING Promotion
   - Portal publication

2. **OpenSearch Analytics**
   - Global Policy per tenant
   - Index pattern: {env}-{tenant}-analytics

#### Phase 6: Demo Tenant & Documentation (Beta Testing)

**Objective**: Create a demonstration tenant with beta tester users and generate user documentation (MkDocs).

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           BETA TESTING - DEMO TENANT                                 │
│                                                                                      │
│                        ┌──────────────────────────┐                                 │
│                        │       KEYCLOAK           │                                 │
│                        │   Realm: stoa-platform   │                                 │
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
│             │   UI Console    │       │ Control-Plane   │                          │
│             │   (React)       │       │     API         │                          │
│             │                 │       │   (FastAPI)     │                          │
│             │ console.stoa... │       │  api.stoa...    │                          │
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
│                    │  Demo APIs:               │                                   │
│                    │  ├── petstore-api         │                                   │
│                    │  └── weather-api          │                                   │
│                    └───────────────────────────┘                                   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

> **Note**: The Developer Portal will be developed in Phase 8 as a custom React portal.

1. **Create Demo Tenant in GitOps** 🔲

   ```yaml
   # iam/tenants.yaml - Add tenant-demo
   tenants:
     - id: tenant-demo
       displayName: "Demo Tenant (Beta Testing)"
       description: "Demonstration tenant for beta testers"
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
             addedBy: "admin@stoa.local"

         devops:
           - email: "demo-devops@cab-i.com"
             name: "Demo DevOps"
             addedAt: "2024-12-21T00:00:00Z"
             addedBy: "admin@stoa.local"

         viewers: []
   ```

2. **Create Beta Users in Keycloak** 🔲

   | User | Email | Role | Access |
   |------|-------|------|-------|
   | Demo CPI | demo-cpi@cab-i.com | `tenant-admin` | UI DevOps (full CRUD) |
   | Demo DevOps | demo-devops@cab-i.com | `devops` | UI DevOps (deploy only) |

   **Configuration Keycloak**:
   ```yaml
   # Group: tenant-demo
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

3. **Pre-deployed Demo APIs** 🔲

   Create demonstration APIs in tenant-demo so beta testers can explore them.

   ```
   stoa-gitops/
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
   apiVersion: stoa.cab-i.com/v1
   kind: API
   metadata:
     name: petstore-api
     tenant: tenant-demo
   spec:
     displayName: "Petstore API (Demo)"
     version: "1.0.0"
     description: "Demo API based on Swagger Petstore"
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

4. **Beta Tester Workflow** 🔲

   ```
   ┌─────────────────────────────────────────────────────────────────────────────────────┐
   │                        BETA TESTER JOURNEY                                           │
   │                                                                                      │
   │  1. LOGIN                                                                            │
   │     ┌─────────────────────────────────────────────────────────────────────────────┐ │
   │     │  Access: https://console.stoa.cab-i.com                                      │ │
   │     │  → Redirect to Keycloak                                                     │ │
   │     │  → Login: demo-cpi@cab-i.com / DemoCPI2024!                                 │ │
   │     │  → Redirect to DevOps UI (JWT with tenant_id=tenant-demo)                  │ │
   │     └─────────────────────────────────────────────────────────────────────────────┘ │
   │                                                                                      │
   │  2. DEVOPS UI - API MANAGEMENT                                                      │
   │     ┌─────────────────────────────────────────────────────────────────────────────┐ │
   │     │  • View tenant-demo APIs (petstore-api, weather-api)                       │ │
   │     │  • Create a new test API                                                   │ │
   │     │  • Deploy to DEV environment                                               │ │
   │     │  • View pipeline traces (GitLab → Kafka → AWX → Gateway)                  │ │
   │     └─────────────────────────────────────────────────────────────────────────────┘ │
   │                                                                                      │
   └─────────────────────────────────────────────────────────────────────────────────────┘
   ```

   > **Note**: The Developer Portal will be added in Phase 8.

5. **Permissions by Role (DevOps UI)** 🔲

   | Action | CPI (demo-cpi) | DevOps (demo-devops) |
   |--------|----------------|----------------------|
   | View tenant APIs | ✅ | ✅ |
   | Create/Modify API | ✅ | ✅ |
   | Delete API | ✅ | ❌ |
   | Deploy API | ✅ | ✅ |
   | Manage tenant members | ✅ | ❌ |
   | View pipeline traces | ✅ | ✅ |

6. **Phase 6 Deployment Checklist** 🔲

   - [ ] Create tenant-demo in `iam/tenants.yaml` + commit to GitLab
   - [ ] Sync IAM → Keycloak (create group + users)
   - [ ] Create demo APIs (petstore, weather) in GitOps
   - [ ] Deploy demo APIs on DEV Gateway
   - [ ] Test complete workflow with demo-cpi
   - [ ] Test complete workflow with demo-devops
   - [ ] Document beta tester access

7. **Beta Tester Credentials**

   | User | URL | Login | Password |
   |------|-----|-------|----------|
   | Demo CPI | https://console.stoa.cab-i.com | demo-cpi@cab-i.com | DemoCPI2024! |
   | Demo DevOps | https://console.stoa.cab-i.com | demo-devops@cab-i.com | DemoDevOps2024! |

   > **Note**: Credentials will be stored in Vault after beta validation.

8. **User Documentation (MkDocs)** 🔲

   Generate comprehensive documentation for beta testers and future platform users.

   **Documentation Structure**:
   ```
   docs/
   ├── user-guide/
   │   ├── README.md                    # Index documentation
   │   ├── 01-getting-started.md        # Getting started
   │   ├── 02-ui-devops-guide.md        # DevOps UI Guide
   │   ├── 03-developer-portal-guide.md # Developer Portal Guide
   │   ├── 04-api-lifecycle.md          # API lifecycle
   │   ├── 05-rbac-roles.md             # Roles and permissions
   │   └── 06-troubleshooting.md        # Troubleshooting
   │
   ├── tutorials/
   │   ├── create-first-api.md          # Tutorial: Create your first API
   │   ├── deploy-api.md                # Tutorial: Deploy an API
   │   ├── consume-api.md               # Tutorial: Consume an API
   │   └── manage-team.md               # Tutorial: Manage your team
   │
   └── images/
       ├── login-flow.png
       ├── ui-dashboard.png
       └── portal-subscribe.png
   ```

   **01-getting-started.md**:
   ```markdown
   # Quick Start Guide

   ## APIM Platform Access

   The CAB-I APIM platform has one main interface:

   | Interface | URL | Description |
   |-----------|-----|-------------|
   | DevOps UI | https://console.stoa.cab-i.com | API management, deployments, monitoring |

   > **Note**: The custom Developer Portal will be available in Phase 8.

   ## Login (Keycloak SSO)

   All interfaces use **Keycloak** for authentication.
   A single login gives you access to all applications.

   ### Login steps:
   1. Access the desired interface URL
   2. You are redirected to the Keycloak login page
   3. Enter your email and password
   4. You are redirected to the application

   ### User Roles

   | Role | Description | Permissions |
   |------|-------------|-------------|
   | **CPI (Tenant Admin)** | Tenant administrator | Full CRUD on APIs, Apps, Users |
   | **DevOps** | Developer/Operator | Create/Modify APIs, Deploy |
   | **Viewer** | Read-only | View APIs and statistics |

   ## Your First Deployment

   1. **Log in** to the DevOps UI
   2. **Create an API** via the form or OpenAPI import
   3. **Deploy** to the DEV environment
   4. **Verify** the deployment in the Monitoring page
   5. **Test** the API via the Gateway
   ```

   **02-ui-devops-guide.md**:
   ```markdown
   # DevOps UI Guide

   ## Dashboard

   The dashboard displays an overview of your tenant:
   - Number of APIs
   - Recent deployments
   - Pipeline status
   - Active alerts

   ## API Management

   ### Create an API
   1. Click on **+ New API**
   2. Fill in the information:
      - Name (unique within the tenant)
      - Version
      - Description
      - Backend URL
   3. (Optional) Import an OpenAPI file
   4. Click **Create**

   ### Deploy an API
   1. Select the API from the list
   2. Click **Deploy**
   3. Choose the environment (DEV, STAGING, PROD)
   4. Confirm the deployment
   5. Follow the pipeline in the **Monitoring** tab

   ### Deployment Pipeline
   ```
   GitLab Commit → Kafka Event → AWX Job → Gateway Deploy
   ```
   Each step is visible in real-time on the Monitoring page.

   ## Monitoring

   ### Pipeline Timeline
   - Chronological view of all deployments
   - Filters by status, API, environment
   - Detail of each step with duration

   ### Statuses
   - 🟢 **Success**: Successful deployment
   - 🟡 **Pending**: In progress
   - 🔴 **Failed**: Failed (click to see the error)

   ## Team Management (CPI only)

   ### Add a member
   1. Go to **Settings > Team**
   2. Click on **+ Add member**
   3. Enter the email and name
   4. Select the role (CPI, DevOps, Viewer)
   5. Confirm

   The user will receive access automatically after Keycloak synchronization.
   ```

   > **Note**: The Developer Portal guide will be added after Phase 8.

   **03-api-lifecycle.md**:
   ```markdown
   # API Lifecycle

   ## API States

   ```
   ┌─────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
   │  DRAFT  │ →  │   DEV    │ →  │ STAGING  │ →  │   PROD   │
   └─────────┘    └──────────┘    └──────────┘    └──────────┘
        │              │               │               │
        │              │               │               │
   Created in     Deployed DEV    Promotion       Production
   Git            Internal tests   UAT            Live
   ```

   ## Promotion Workflow

   1. **Development (DEV)**
      - Create the API in the DevOps UI
      - Automatic commit to GitLab
      - Deploy to DEV Gateway
      - Integration tests

   2. **Staging (STAGING)**
      - Promote from DEV
      - Acceptance tests (UAT)
      - Business validation

   3. **Production (PROD)**
      - Approval required
      - Blue-Green deployment
      - Enhanced monitoring

   ## Rollback

   In case of issues:
   1. Go to **Monitoring > History**
   2. Select a previous version
   3. Click **Rollback**
   4. Confirm
   ```

   **Automatic Generation (MkDocs)**:
   ```yaml
   # mkdocs.yml
   site_name: STOA Platform - Documentation
   site_url: https://docs.stoa.cab-i.com
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
     - mkdocstrings  # Auto-generates docs from Python code
   ```

   **Documentation Deployment**:
   - URL: https://docs.stoa.cab-i.com
   - CI/CD: GitLab Pages ou S3 + CloudFront
   - Build: `mkdocs build`

   **Documentation Checklist**:
   - [ ] Write 01-getting-started.md
   - [ ] Write 02-ui-devops-guide.md with screenshots
   - [ ] Write 03-api-lifecycle.md
   - [ ] Write 04-rbac-roles.md
   - [ ] Write 05-troubleshooting.md (FAQ)
   - [ ] Create step-by-step tutorials
   - [ ] Capture interface screenshots
   - [ ] Configure MkDocs + Material theme
   - [ ] Deploy on GitLab Pages
   - [ ] Add "Documentation" link in DevOps UI

#### Phase 7: Operational Security (Batch Jobs)

**Objective**: Set up automated jobs for operational security: certificate expiration checks, secret rotation, usage reporting, and GitLab security scanning.

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

1. **Job 1: Certificate Expiration Check** 🔲

   **Sources checked**:
   | Source | Type | Exemple |
   |--------|------|---------|
   | Kubernetes | TLS Secrets | Ingress certificates, mTLS |
   | Vault | PKI Certificates | API certs, Client certs |
   | External | Endpoints HTTPS | Backend URLs, Partner APIs |

   **Alert thresholds**:
   | Level | Days remaining | Action |
   |--------|----------------|--------|
   | 🔴 CRITICAL | < 7 days | Email + Slack + PagerDuty |
   | 🟠 WARNING | < 30 days | Email + Slack |
   | 🟡 INFO | < 60 days | Slack |
   | 🟢 OK | > 60 days | - |

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
                 image: stoa-security-jobs:latest
                 command: ["python", "-m", "src.jobs.certificate_checker"]
   ```

2. **Job 2: Automatic Secret Rotation** 🔲

   **Rotation policies**:
   | Secret Type | Frequency | Auto-Rotate | Notify before |
   |----------------|-----------|-------------|----------------|
   | API Keys | 30 days | ✅ Yes | 7 days |
   | OAuth Client Secrets | 90 days | ✅ Yes | 14 days |
   | Database Passwords | 90 days | ✅ Yes | 14 days |
   | Service Accounts | 180 days | ✅ Yes | 30 days |
   | Encryption Keys | 365 days | ❌ Manual | 60 days |

   **Features**:
   - Generate new secrets (alphanumeric, special chars)
   - Update in Vault with metadata (last_rotated, rotated_by)
   - Propagate to Kubernetes Secrets and Keycloak Clients
   - Post-rotation actions (restart deployments if needed)

   **CronJobs**:
   - Weekly: Sunday 2AM
   - Monthly (forced): 1st of month 3AM

3. **Job 3: Usage Reporting per Tenant** 🔲

   **Metrics collected**:
   | Category | Metrics |
   |-----------|-----------|
   | API Calls | Total, Success, Failed, Error Rate |
   | Bandwidth | Inbound MB, Outbound MB, Total |
   | Latency | Avg, P50, P95, P99 |
   | Resources | Active APIs, Apps, Users |
   | Quota | Usage %, Exceeded |

   **Data sources**:
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
   - Daily: 1AM (daily report)
   - Weekly: Monday 2AM (weekly PDF report)

4. **Job 4: GitLab Security Scan** 🔲

   **Scan types**:
   | Scan | Tool | Detection |
   |------|-------|-----------|
   | Secret Detection | Gitleaks | API Keys, Passwords, Tokens, Certs |
   | SAST | Semgrep | SQL Injection, XSS, Hardcoded creds |
   | Dependency Check | Trivy | CVE, Outdated packages |
   | License Compliance | pip-licenses | GPL/LGPL, Proprietary |

   **Gitleaks rules** (`.gitleaks.toml`):
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

5. **Notification Service** 🔲

   | Level | Channels |
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
       channel: "#stoa-alerts"
     pagerduty:
       routing_key: vault:secret/data/notifications#pagerduty_key
   ```

6. **Job Structure** 🔲

   ```
   control-plane-api/
   └── src/
       └── jobs/
           ├── __init__.py
           ├── certificate_checker.py      # Job 1
           ├── secret_rotation.py          # Job 2
           ├── usage_reporting.py          # Job 3
           └── security_scanner.py         # Job 4

   charts/stoa-platform/
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
     image: stoa-security-jobs:latest

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

8. **Phase 7 Deployment Checklist** 🔲

   - [ ] Create Docker image `stoa-security-jobs` with Python + tools
   - [ ] Implement `certificate_checker.py`
   - [ ] Implement `secret_rotation.py` with Vault integration
   - [ ] Implement `usage_reporting.py` with PDF generation
   - [ ] Implement `security_scanner.py` with Gitleaks/Semgrep/Trivy
   - [ ] Create `NotificationService` (Email/Slack/PagerDuty)
   - [ ] Add CronJobs in Helm chart
   - [ ] Configure `.gitleaks.toml` in GitLab repos
   - [ ] Add security-scan stages in `.gitlab-ci.yml`
   - [ ] Configure alerting in Grafana
   - [ ] Test each job manually
   - [ ] Document alert response procedures

9. **Security Jobs Monitoring** 🔲

   **Jobs Observability Architecture**:
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

   **Prometheus metrics exposed by each job**:
   ```python
   # src/jobs/base_job.py
   from prometheus_client import Counter, Histogram, Gauge, push_to_gateway

   class BaseSecurityJob:
       # Common metrics for all jobs
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
   # Published at the end of each job
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

   **Prometheus Alerts (AlertManager)**:
   ```yaml
   # prometheus-rules.yaml
   groups:
     - name: security-jobs
       rules:
         # Alert if a job hasn't run for 2x its interval
         - alert: SecurityJobNotRunning
           expr: |
             time() - security_job_last_run_timestamp > 2 * 86400
           for: 5m
           labels:
             severity: warning
           annotations:
             summary: "Security job {{ $labels.job_name }} not running"
             description: "Job has not run for more than 2 days"

         # Alert if a job fails
         - alert: SecurityJobFailed
           expr: |
             increase(security_job_runs_total{status="failure"}[1h]) > 0
           for: 0m
           labels:
             severity: critical
           annotations:
             summary: "Security job {{ $labels.job_name }} failed"
             description: "Job execution failed in the last hour"

         # Alert if critical findings detected
         - alert: SecurityCriticalFindings
           expr: |
             security_job_findings_total{severity="critical"} > 0
           for: 0m
           labels:
             severity: critical
           annotations:
             summary: "Critical security findings in {{ $labels.job_name }}"
             description: "{{ $value }} critical findings detected"

         # Alert if job takes too long
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

   **Helm Values for Monitoring**:
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

   **Monitoring Checklist**:
   - [ ] Deploy Prometheus Pushgateway
   - [ ] Implement `BaseSecurityJob` with metrics
   - [ ] Create Kafka topic `security-job-results`
   - [ ] Configure OpenSearch index template
   - [ ] Create AlertManager rules
   - [ ] Import Grafana dashboard
   - [ ] Test alerts (job failure, critical findings)
   - [ ] Configure OpenSearch retention (90 days)

#### Phase 8: Custom Developer Portal (React)

**Objective**: Develop a custom React Developer Portal integrated with the APIM GitOps architecture with unified Keycloak SSO.

> **Detailed plan**: See [docs/DEVELOPER-PORTAL-PLAN.md](docs/DEVELOPER-PORTAL-PLAN.md)

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

**Technical Stack**:
| Component | Technology |
|-----------|-------------|
| Frontend | React 18 + TypeScript + Vite |
| Styling | TailwindCSS |
| Auth | Keycloak OIDC (same realm as DevOps UI) |
| API Docs | Swagger-UI React |
| Code Editor | Monaco Editor |
| Backend | Control-Plane API (FastAPI) - new `/portal/*` endpoints |

**Key Features**:

1. **API Catalog** 🔲
   - List of published APIs with search
   - Filters by category, tenant
   - Cards with name, version, description

2. **API Detail** 🔲
   - General information
   - OpenAPI documentation (Swagger-UI)
   - "Subscribe" button
   - Code samples (curl, Python, JavaScript)

3. **Application Management** 🔲
   - Create an application (generates client_id, client_secret, api_key)
   - View my applications
   - API Key rotation
   - Delete application

4. **Subscriptions** 🔲
   - Subscribe an application to an API
   - View my subscriptions
   - Unsubscribe

5. **Try-It Console** 🔲
   - HTTP method, path, headers selection
   - JSON body editor (Monaco)
   - Send request via backend proxy
   - Response display (status, headers, body, timing)

**Backend Endpoints to Add** (Control-Plane API):
```
# Catalog
GET    /portal/apis                    # List published APIs
GET    /portal/apis/{api_id}           # API detail
GET    /portal/apis/{api_id}/spec      # OpenAPI spec

# Applications
GET    /portal/my/applications         # My applications
POST   /portal/applications            # Create application
DELETE /portal/applications/{app_id}   # Delete
POST   /portal/applications/{app_id}/rotate-key  # Rotation

# Subscriptions
GET    /portal/my/subscriptions        # My subscriptions
POST   /portal/subscriptions           # Subscribe
DELETE /portal/subscriptions/{sub_id}  # Unsubscribe

# Try-It
POST   /portal/try-it                  # Proxy to Gateway
```

**Keycloak - New Client**:
```yaml
client_id: developer-portal
client_type: public
valid_redirect_uris:
  - https://portal.stoa.cab-i.com/*
  - http://localhost:3001/*
roles:
  - developer  # Portal access
```

**Kafka Integration**:
- `application-created` → Audit + GitLab sync
- `subscription-created` → Audit + Gateway provisioning
- `api-key-rotated` → Audit + cache invalidation

**Phase 8 Checklist**:
- [ ] Setup Vite + React + TypeScript + TailwindCSS project
- [ ] Configure Keycloak OIDC (developer-portal client)
- [ ] Responsive layout (Header, Sidebar, Footer)
- [ ] API Catalog page with search/filters
- [ ] API Detail page with Swagger-UI
- [ ] My Applications page (CRUD)
- [ ] Secure credentials display (visible once)
- [ ] Subscriptions page
- [ ] Try-It Console with Monaco Editor
- [ ] Code Samples (curl, Python, JS)
- [ ] `/portal/*` endpoints in Control-Plane API
- [ ] Kafka events for audit
- [ ] Kubernetes deployment (Helm)
- [ ] URL: https://portal.stoa.cab-i.com

#### Phase 9: Ticketing System (Production Requests)

**Objective**: Implement a manual validation workflow for PROD promotions with complete traceability and anti-self-approval rule.

> **Detailed plan**: See [docs/TICKETING-SYSTEM-PLAN.md](docs/TICKETING-SYSTEM-PLAN.md)

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
│   │  DevOps ──▶ Create request ──▶ Git (requests/prod/) ──▶ Kafka Event          │   │
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

**Key Features**:

| Feature | Description |
|----------------|-------------|
| Create request | DevOps submits a STAGING → PROD promotion request |
| RBAC validation | Only CPI/Admins can approve |
| Anti-self-approval | Requester cannot approve their own request |
| Automated workflow | Approval → AWX Job → PROD deployment |
| Notifications | Email + Slack at each step |
| Complete history | Audit trail in Git |

**GitOps Structure**:
```
stoa-gitops/
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
apiVersion: stoa.cab-i.com/v1
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

| Role | Create request | Approve | Reject | View |
|------|----------------|---------|--------|------|
| DevOps | ✅ Own tenant | ❌ | ❌ | Own requests |
| CPI (Tenant Admin) | ✅ Own tenant | ✅ Own tenant* | ✅ Own tenant | Own tenant |
| CPI Admin | ✅ All | ✅ All* | ✅ All | All |

*\* Except own requests (anti-self-approval)*

**Endpoints API**:
```
# List and search
GET    /v1/requests/prod?state=pending&tenant=...

# My requests
GET    /v1/requests/prod/my

# Pending requests for me (approver)
GET    /v1/requests/prod/pending

# Create a request
POST   /v1/requests/prod

# Detail
GET    /v1/requests/prod/{id}

# Approve (triggers AWX automatically)
POST   /v1/requests/prod/{id}/approve

# Reject (reason required)
POST   /v1/requests/prod/{id}/reject

# Stats dashboard
GET    /v1/requests/prod/stats
```

**Kafka Integration**:
- `request-created` → Notify approvers
- `request-approved` → Trigger AWX + notify requester
- `request-rejected` → Notify requester
- `deployment-started` → Notify requester + approver
- `deployment-succeeded` → Notify all
- `deployment-failed` → Notify all + ops

**Phase 9 Checklist**:
- [ ] Pydantic model `PromotionRequest`
- [ ] Git service for CRUD requests
- [ ] CRUD endpoints `/v1/requests/prod`
- [ ] Approve endpoint with anti-self-approval
- [ ] Reject endpoint with required reason
- [ ] Trigger AWX on approval
- [ ] AWX webhook callback → update status
- [ ] UI - Request list page with filters
- [ ] UI - New request form
- [ ] UI - Detail page with timeline
- [ ] UI - Approve/Reject buttons
- [ ] Kafka events for notifications
- [ ] Email templates (created, approved, rejected, deployed, failed)
- [ ] Slack notifications

#### Phase 9.5: Production Readiness

**Objective**: Prepare the APIM platform for production with all guarantees of reliability, security, and operability.

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

**Target SLOs**:

| Metric | Objective | Measurement |
|--------|-----------|-------------|
| Availability | 99.9% | < 8.76h downtime/year |
| API Latency p95 | < 500ms | Prometheus |
| Deployment Success Rate | > 99% | Jenkins metrics |
| MTTR (P1 incidents) | < 1h | Runbook SLA |
| Error Rate | < 0.1% | Grafana dashboard |

**Production Readiness Components**:

| Component | Description | Priority |
|-----------|-------------|----------|
| Backup AWX | CronJob backup PostgreSQL → S3 | P0 |
| Backup Vault | Snapshot storage + unseal keys | P0 |
| Load Testing | K6/Gatling pipeline with thresholds | P0 |
| Runbooks | Operational procedures | P0 |
| Security Audit | OWASP ZAP scan + remediation | P0 |
| Chaos Testing | Litmus/Chaos Mesh validation | P1 |
| SLO Dashboard | Grafana + alerting | P0 |

**Runbooks to Document**:
- Incident: API Gateway down
- Incident: AWX job failure
- Incident: Vault sealed
- Incident: High Kafka lag
- Procedure: Emergency rollback
- Procedure: Horizontal scaling
- Procedure: Secret rotation
- Procedure: DR failover

**Phase 9.5 Checklist**:
- [ ] AWX database backup script (PostgreSQL) → S3
- [ ] Vault snapshot backup script → S3 + KMS
- [ ] Kubernetes CronJob for daily backups
- [ ] Restore procedures documented and tested
- [ ] Load Testing pipeline (K6 or Gatling)
- [ ] Performance thresholds defined (p95, p99)
- [ ] Operational runbooks (docs/runbooks/)
- [ ] OWASP ZAP scan on API and UI
- [ ] Critical vulnerability remediation
- [ ] Chaos Testing (pod kill, network latency)
- [ ] Kubernetes auto-healing validation
- [ ] SLO/SLA documented
- [ ] SLO Dashboard in Grafana
- [ ] Alerts configured on SLO breach

#### Phase 10: Resource Lifecycle Management (Non-Production Auto-Teardown)

**Objective**: Implement a mandatory tagging strategy and auto-deletion of non-production resources to optimize costs and avoid accumulation of orphaned resources.

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

**Mandatory Tags**:

| Tag | Description | Possible Values | Required |
|-----|-------------|-----------------|----------|
| `environment` | Target environment | `dev`, `staging`, `sandbox`, `demo` | ✅ |
| `owner` | Responsible person's email | Valid email | ✅ |
| `project` | Project/tenant name | String | ✅ |
| `cost-center` | Cost center code | Numeric code | ✅ |
| `ttl` | Time to live | `7d`, `14d`, `30d` (max) | ✅ Non-prod |
| `created_at` | Creation date | ISO 8601 (auto-generated) | ✅ Auto |
| `auto-teardown` | Auto deletion | `true`, `false` | ✅ Non-prod |
| `data-class` | Data classification | `public`, `internal`, `confidential`, `restricted` | ✅ |

**Guardrails (Protection Rules)**:

1. **Tag Validation** - Reject any deployment without mandatory tags
2. **Maximum TTL** - 30 days max for non-prod environments
3. **Data Classification** - `restricted` resources excluded from auto-teardown
4. **Owner Notification** - 48h before expiration → 24h → deletion
5. **Audit Trail** - All deletions logged to Kafka + S3

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

**Terraform Usage**:
```hcl
# terraform/environments/dev/main.tf
module "tags" {
  source = "../../modules/common_tags"

  environment   = "dev"
  owner         = "devteam@cab-i.com"
  project       = "stoa-platform"
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
- For multi-cloud environments (AWS + Azure + GCP)
- Visual workflow with configurable nodes
- Slack/Teams integration for notifications
- Expired resources reporting dashboard

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
      - stoa-system  # Core platform excluded
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

**Kafka Integration**:
- `resource-created` → Log creation with tags
- `resource-expiring` → Notification 48h/24h before expiration
- `resource-deleted` → Deletion audit trail
- `tag-violation` → Alert on deployment without tags

**Phase 10 Checklist**:
- [ ] Terraform module `common_tags` with validations
- [ ] Lambda `resource-cleanup` with EventBridge schedule
- [ ] Owner notifications (48h → 24h → delete)
- [ ] OPA Gatekeeper policies for Kubernetes
- [ ] GitHub Actions workflow `tag-governance.yaml`
- [ ] Grafana dashboard "Resource Lifecycle"
- [ ] Kafka events (resource-created, expiring, deleted)
- [ ] Exclude `data-class=restricted` resources
- [ ] Exclude `prod` environment (auto-teardown=false)
- [ ] Tagging policy documentation
- [ ] Alternative n8n workflow for multi-cloud (optional)

#### Phase 11: Resource Lifecycle Advanced (Advanced Governance)

**Objective**: Complete Phase 10 with advanced governance features: quotas, whitelist, ordered destruction, cost metrics, and self-service TTL extension.

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
│   │   ├── arn:aws:rds:*:*:db:stoa-*              # BDD plateforme              │    │
│   │   ├── arn:aws:s3:::stoa-artifacts-*          # Buckets artifacts           │    │
│   │   ├── namespace:stoa-system                   # K8s core namespace         │    │
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
│   │   │  Lien: https://api.stoa.cab-i.com/v1/resources/{id}/extend?days=7 │     │    │
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

**Quotas per Project** (Terraform):
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

# AWS Service Quotas + validation before deployment
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
  # By ARN pattern
  aws_resources:
    - "arn:aws:ec2:*:*:instance/i-stoa-*"
    - "arn:aws:rds:*:*:db:stoa-prod-*"
    - "arn:aws:s3:::stoa-artifacts"
    - "arn:aws:s3:::stoa-backups"
    - "arn:aws:lambda:*:*:function:stoa-core-*"

  # By tag
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
      - stoa-system
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
    extend_days: int  # 7 or 14
    reason: str

@router.patch("/{resource_id}/ttl")
async def extend_ttl(resource_id: str, request: TTLExtendRequest, user: User = Depends(get_current_user)):
    """
    Extend TTL of a resource (max 2 extensions, 60 days total).
    """
    resource = await get_resource(resource_id)

    # Check ownership
    if resource.tags.get("owner") != user.email:
        raise HTTPException(403, "Only resource owner can extend TTL")

    # Check extension limit
    if resource.extension_count >= 2:
        raise HTTPException(400, "Maximum 2 extensions allowed (60 days total)")

    # Check requested days
    if request.extend_days not in [7, 14]:
        raise HTTPException(400, "Extension must be 7 or 14 days")

    # Update TTL tag
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

**Lambda Ordered Destruction**:
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

**Cost Avoided Metrics** (Grafana/Prometheus):
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

**Complete n8n Workflow with Notion Board**:
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

**Phase 11 Checklist**:
- [ ] Per-project quota system (Terraform + AWS Service Quotas)
- [ ] Whitelist configuration (YAML + validation)
- [ ] Ordered destruction (AWS dependencies)
- [ ] Self-service TTL extension API (`PATCH /v1/resources/{id}/ttl`)
- [ ] Snooze buttons in emails (7d, 14d)
- [ ] Max 2 extensions limit (60d total)
- [ ] Cost avoided calculation (AWS pricing)
- [ ] Grafana dashboard "Cost Savings"
- [ ] Prometheus metrics (resources_deleted, cost_avoided_usd)
- [ ] Complete n8n workflow with Notion board
- [ ] Hourly cron (instead of daily) for pre-alerts
- [ ] Kafka event `resource-ttl-extended`

---

### Complete Target Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         UTILISATEURS                                 │
│   CPI Admin │ Tenant Admin │ DevOps │ Viewer                        │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    UI Control-Plane (React + Keycloak)               │
│                    https://console.stoa.cab-i.com                     │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Control-Plane API (FastAPI)                       │
│                    https://api.stoa.cab-i.com                        │
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

### Development Time Estimation

| Phase | Description | Estimated Duration |
|-------|-------------|-------------------|
| Phase 1 | Kafka/Redpanda + AWX Automation | To be planned |
| Phase 2 | GitOps + Environment Variables + IAM | To be planned |
| Phase 3 | Vault + Gateway Alias | To be planned |
| Phase 4 | OpenSearch + Monitoring | To be planned |
| Phase 5 | Multi-environments (dev/staging/prod) | To be planned |
| Phase 6 | Demo Tenant + Unified SSO + Documentation | To be planned |
| Phase 7 | Operational Security (Batch Jobs) | To be planned |
| Phase 8 | Custom Developer Portal (React) | To be planned |
| Phase 9 | Ticketing (Production Requests) | To be planned |
| Phase 9.5 | Production Readiness | To be planned |
| Phase 10 | Resource Lifecycle (Tagging + Auto-Teardown) | To be planned |
