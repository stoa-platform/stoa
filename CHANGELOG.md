# Changelog

Toutes les modifications notables de ce projet sont documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/).

---

## [Unreleased]

### Ajouté (Phase 2.5) - Validation E2E

- **Tenant APIM Platform** - Tenant administrateur avec accès cross-tenant
  - Fichier: `tenants/apim/` dans GitLab apim-gitops
  - User: APIMAdmin (role: cpi-admin, password temporaire: manage)
  - API: Control-Plane (proxy vers FastAPI via Gateway OIDC)

- **Playbooks Ansible** - Automation tenant lifecycle
  - `provision-tenant.yaml` - Crée groupes Keycloak, users, namespaces K8s
  - `register-api-gateway.yaml` - Import OpenAPI, OIDC, rate limiting, activation
  - `tasks/create-keycloak-user.yaml` - Création user avec roles

- **AWX Job Templates** - Nouveaux templates
  - `Provision Tenant` (ID: 12) - Provisioning tenant complet
  - `Register API Gateway` (ID: 13) - Enregistrement API dans Gateway

- **Control-Plane API** - Nouveaux handlers
  - Event `tenant-provisioning` → AWX Provision Tenant
  - Event `api-registration` → AWX Register API Gateway
  - awx_service: `provision_tenant()`, `register_api_gateway()`

- **Architecture clarifiée**
  - GitHub (apim-aws): Code source, développement, CI/CD
  - GitLab (apim-gitops): Runtime data, tenants, playbooks AWX

### Ajouté (Phase 2) - COMPLÉTÉ
- **GitOps Templates** (`gitops-templates/`) - Modèles pour initialiser GitLab
  - `_defaults.yaml` - Variables globales par défaut
  - `environments/{dev,staging,prod}/config.yaml` - Config par environnement
  - `templates/` - Templates API, Application, Tenant
  - **Note**: Les données tenants sont sur GitLab, pas ici

- **Variable Resolver Service** - Résolution de placeholders `${VAR}` et `${VAR:default}`
  - Support des références Vault: `vault:secret/path#key`
  - Merge de configs: global → env → tenant → inline defaults
  - Validation des variables requises

- **IAM Sync Service** - Synchronisation GitOps ↔ Keycloak
  - Sync groupes/utilisateurs par tenant
  - Création clients OAuth2 pour applications
  - Réconciliation et détection de drift
  - Rotation des secrets clients

- **Routers GitOps-Enabled**
  - APIs router: CRUD via GitLab + events Kafka
  - Tenants router: Multi-tenant avec RBAC

- **ArgoCD** - GitOps Continuous Delivery
  - Chart Helm avec SSO Keycloak
  - ApplicationSets pour multi-tenant auto-discovery
  - AppProjects avec RBAC par tenant
  - Scripts d'installation: `scripts/install-argocd.sh`
  - URL: https://argocd.apim.cab-i.com

- **Script Init GitLab** - `scripts/init-gitlab-gitops.sh`
  - Initialise le repo GitLab apim-gitops
  - Copie les templates et configurations

- **GitLab apim-gitops** - Repository configuré
  - URL: https://gitlab.com/PotoMitan1/apim-gitops
  - Structure: `_defaults.yaml`, `environments/`, `tenants/`
  - Connecté à ArgoCD pour GitOps

---

## [2.0.0] - 2024-12-21

### Phase 1: Event-Driven Architecture - COMPLÉTÉ

#### Ajouté
- **Redpanda (Kafka)** - Event streaming compatible Kafka
  - 1 broker sur EKS avec Redpanda Console
  - Storage: 10GB persistant (EBS gp2)
  - Topics: `api-created`, `api-updated`, `api-deleted`, `deploy-requests`, `deploy-results`, `audit-log`, `notifications`

- **AWX (Ansible Tower)** - Automation
  - AWX 24.6.1 via AWX Operator 2.19.1
  - URL: https://awx.apim.cab-i.com
  - Job Templates: Deploy API, Sync Gateway, Promote Portal, Rollback API

- **Control-Plane UI** - Interface React
  - Authentification Keycloak avec PKCE (Keycloak 25+)
  - Pages: Dashboard, Tenants, APIs, Applications, Deployments, Monitoring
  - URL: https://devops.apim.cab-i.com

- **Control-Plane API** - Backend FastAPI
  - Kafka Producer intégré (events sur CRUD)
  - Deployment Worker (consumer `deploy-requests`)
  - Webhook GitLab (Push, MR, Tag Push)
  - Pipeline Traces (in-memory store)
  - URL: https://api.apim.cab-i.com

- **Configuration Variabilisée**
  - UI: Variables `VITE_*` pour build-time config
  - API: Variables d'environnement via pydantic-settings
  - Dockerfiles avec build args pour personnalisation

#### Modifié
- Infrastructure: 3x t3.large (2 CPU / 8GB RAM) pour supporter Redpanda + AWX
- Keycloak: Realm `apim`, clients `control-plane-ui` et `control-plane-api`

#### Corrigé
- Authentification PKCE - `response_type: 'code'` + `pkce_method: 'S256'`
- URLs Keycloak - `auth.apim.cab-i.com` au lieu de `keycloak.dev.apim.cab-i.com`
- OpenAPI Tags - Harmonisation casse (`Traces` au lieu de `traces`)

---

## [1.0.0] - 2024-12-XX

### Infrastructure initiale

#### Ajouté
- **AWS Infrastructure** (Terraform)
  - VPC avec subnets publics/privés
  - EKS Cluster `apim-dev-cluster`
  - RDS PostgreSQL (db.t3.micro)
  - ECR Repositories

- **Kubernetes**
  - Nginx Ingress Controller
  - Cert-Manager (Let's Encrypt)
  - EBS CSI Driver

- **webMethods**
  - API Gateway (lean trial 10.15)
  - Developer Portal
  - Elasticsearch 8.11 (pour Gateway)

- **Keycloak** - Identity Provider
  - URL: https://auth.apim.cab-i.com
  - Realm: `apim`

---

## Roadmap

### Phase 2: GitOps + ArgoCD (Priorité Haute) - COMPLÉTÉ ✅
- [x] Structure GitOps par tenant (`gitops-templates/`)
- [x] Variable Resolver (templates avec placeholders `${VAR}`)
- [x] IAM Sync Service (Git → Keycloak)
- [x] Routers API/Tenants avec intégration GitLab
- [x] ArgoCD Helm chart avec SSO Keycloak
- [x] ApplicationSets multi-tenant
- [x] Installation ArgoCD sur EKS
- [x] Repository GitLab `apim-gitops` configuré

### Phase 2.5: Validation E2E - EN COURS 🔄
- [x] Playbook provision-tenant.yaml (Keycloak + K8s namespaces)
- [x] Playbook register-api-gateway.yaml (Gateway OIDC)
- [x] AWX Job Templates (Provision Tenant, Register API Gateway)
- [x] Tenant apim dans GitLab avec APIMAdmin
- [x] Control-Plane API handlers (tenant-provisioning, api-registration)
- [ ] Test E2E: Login APIMAdmin → voir tous les tenants
- [ ] API Control-Plane enregistrée dans Gateway

### Phase 3: Secrets & Gateway Alias (Priorité Moyenne)
- [ ] HashiCorp Vault
- [ ] Gateway Alias pour endpoints/credentials
- [ ] Jobs AWX sync-alias, rotate-credentials

### Phase 4: Observabilité (Priorité Moyenne)
- [ ] Amazon OpenSearch
- [ ] FluentBit (log shipping)
- [ ] Prometheus + Grafana
- [ ] OpenSearch Dashboards

### Phase 5: Multi-Environment (Priorité Basse)
- [ ] Environnement STAGING
- [ ] Promotion DEV → STAGING → PROD

### Phase 6: Beta Testing (Priorité Basse)
- [ ] Tenant démo
- [ ] SSO Developer Portal
- [ ] Documentation utilisateur (MkDocs)

### Phase 7: Sécurité Opérationnelle (Priorité Basse)
- [ ] Job 1: Certificate Checker (expiration TLS, Vault PKI, endpoints)
- [ ] Job 2: Secret Rotation (API Keys, OAuth, DB passwords via Vault)
- [ ] Job 3: Usage Reporting (métriques par tenant, PDF, email)
- [ ] Job 4: GitLab Security Scan (Gitleaks, Semgrep, Trivy)
- [ ] NotificationService (Email, Slack, PagerDuty)
- [ ] CronJobs Kubernetes (Helm chart)
- [ ] Intégration GitLab CI/CD (security-scan stage)
- [ ] Monitoring Jobs (Prometheus, Kafka, OpenSearch, Grafana Dashboard)
- [ ] Alertes (job failed, job not running, critical findings)

---

## URLs

| Service | URL | Notes |
|---------|-----|-------|
| Control Plane UI | https://devops.apim.cab-i.com | React + Keycloak |
| Control Plane API | https://api.apim.cab-i.com | FastAPI |
| Keycloak | https://auth.apim.cab-i.com | Realm: apim |
| AWX | https://awx.apim.cab-i.com | admin/demo |
| API Gateway | https://gateway.apim.cab-i.com | Administrator/manage |
| Developer Portal | https://portal.apim.cab-i.com | - |
| ArgoCD | https://argocd.apim.cab-i.com | GitOps CD |
