# Plan Détaillé - Plateforme API Management as Code AWS (DEV/TEST)

## Vue d'ensemble
Plateforme API Management optimisée coûts pour environnement DEV/TEST comprenant:
- webMethods API Gateway
- Portail développeur
- OpenSearch pour analytics
- Jenkins pour CI/CD
- Control Plane avec IDP
- Infrastructure as Code (Terraform)
- Configuration Management (Ansible)
- Secrets Management (Vault)
- GitOps (GitHub)

---

## Phase 1: Préparation et Configuration Initiale

### Étape 1.1: Configuration des prérequis locaux
**Durée estimée: Setup initial**

**Actions:**
1. Installer les outils CLI nécessaires:
   ```bash
   # Terraform
   brew install terraform

   # Ansible
   pip3 install ansible

   # AWS CLI
   brew install awscli

   # Vault CLI
   brew install vault

   # kubectl (pour control plane)
   brew install kubectl
   ```

2. Configurer les credentials AWS:
   ```bash
   aws configure
   # Configurer avec des credentials ayant les permissions nécessaires
   ```

3. Créer le repository GitHub:
   - Repository principal: `apim-aws`
   - Branches: `main`, `develop`, `feature/*`
   - Protection sur `main` et `develop`

**Livrables:**
- [ ] Outils installés et configurés
- [ ] Credentials AWS opérationnels
- [ ] Repository GitHub créé

---

### Étape 1.2: Structure du projet
**Actions:**

Créer l'arborescence suivante:
```
apim-aws/
├── terraform/
│   ├── modules/
│   │   ├── vpc/
│   │   ├── ec2/
│   │   ├── opensearch/
│   │   ├── alb/
│   │   ├── s3/
│   │   └── iam/
│   ├── environments/
│   │   ├── dev/
│   │   └── test/
│   ├── backend.tf
│   └── variables.tf
├── ansible/
│   ├── playbooks/
│   │   ├── webmethods-gateway.yml
│   │   ├── developer-portal.yml
│   │   ├── jenkins.yml
│   │   └── vault.yml
│   ├── roles/
│   │   ├── common/
│   │   ├── webmethods/
│   │   ├── portal/
│   │   ├── jenkins/
│   │   └── vault/
│   └── inventory/
│       ├── dev.ini
│       └── test.ini
├── vault/
│   ├── policies/
│   └── config/
├── jenkins/
│   ├── pipelines/
│   └── jobs/
├── scripts/
│   ├── bootstrap.sh
│   └── deploy.sh
├── docs/
│   ├── architecture.md
│   └── runbook.md
└── .github/
    └── workflows/
        ├── terraform-plan.yml
        ├── terraform-apply.yml
        └── ansible-deploy.yml
```

**Livrables:**
- [ ] Structure de répertoires créée
- [ ] README.md à la racine

---

## Phase 2: Infrastructure AWS (Terraform)

### Étape 2.1: Configuration du backend Terraform
**Fichier: `terraform/backend.tf`**

**Actions:**
1. Créer un bucket S3 pour le state Terraform:
   ```hcl
   terraform {
     backend "s3" {
       bucket         = "apim-terraform-state-dev"
       key            = "apim/terraform.tfstate"
       region         = "eu-west-1"
       encrypt        = true
       dynamodb_table = "apim-terraform-locks"
     }
   }
   ```

2. Créer la table DynamoDB pour les locks:
   ```bash
   aws dynamodb create-table \
     --table-name apim-terraform-locks \
     --attribute-definitions AttributeName=LockID,AttributeType=S \
     --key-schema AttributeName=LockID,KeyType=HASH \
     --billing-mode PAY_PER_REQUEST
   ```

**Livrables:**
- [ ] Bucket S3 créé
- [ ] Table DynamoDB créée
- [ ] Backend configuré

---

### Étape 2.2: Module VPC (Optimisé coûts)
**Fichier: `terraform/modules/vpc/main.tf`**

**Spécifications pour économies:**
- 1 seul VPC pour DEV/TEST
- 2 AZ pour haute disponibilité minimale
- Subnets publics: 2 (pour ALB)
- Subnets privés: 2 (pour instances)
- NAT Gateway: 1 seul (économie vs 1 par AZ)
- VPC Endpoints: S3, SSM (gratuits/économiques)

**Configuration:**
```hcl
# CIDR: 10.0.0.0/16
# Public Subnets: 10.0.1.0/24, 10.0.2.0/24
# Private Subnets: 10.0.10.0/24, 10.0.11.0/24
# Database Subnets: 10.0.20.0/24, 10.0.21.0/24
```

**Ressources à créer:**
- VPC avec DNS enabled
- Internet Gateway
- 1 NAT Gateway (dans une seule AZ)
- Route Tables
- Security Groups définis par service
- VPC Endpoints (S3, SSM)

**Livrables:**
- [ ] Module VPC créé
- [ ] Variables définies
- [ ] Outputs configurés

---

### Étape 2.3: Module IAM
**Fichier: `terraform/modules/iam/main.tf`**

**Rôles à créer:**
1. **EC2 Instance Roles:**
   - `apim-webmethods-role`
   - `apim-portal-role`
   - `apim-jenkins-role`
   - `apim-vault-role`

2. **Policies nécessaires:**
   - SSM Access (pour Session Manager)
   - S3 Access (pour artifacts)
   - CloudWatch Logs
   - OpenSearch Access
   - Secrets Manager (Vault backup)

**Livrables:**
- [ ] Rôles IAM créés
- [ ] Policies attachées
- [ ] Instance Profiles configurés

---

### Étape 2.4: Module EC2 (Instances optimisées coûts)
**Fichier: `terraform/modules/ec2/main.tf`**

**Instances recommandées pour DEV/TEST:**

| Service | Type Instance | vCPU | RAM | Stockage | Coût/mois (eu-west-1) |
|---------|---------------|------|-----|----------|------------------------|
| webMethods Gateway | t3.large | 2 | 8 GB | 50 GB gp3 | ~$60 |
| Developer Portal | t3.medium | 2 | 4 GB | 30 GB gp3 | ~$30 |
| Jenkins Master | t3.medium | 2 | 4 GB | 50 GB gp3 | ~$30 |
| Vault | t3.small | 2 | 2 GB | 20 GB gp3 | ~$15 |

**Configuration:**
- AMI: Amazon Linux 2023 ou Ubuntu 22.04
- Instances dans subnets privés
- EBS optimized
- Detailed monitoring: désactivé (économie)
- Public IP: Non (accès via ALB/SSM)
- Stop automatique en dehors heures ouvrées (économie ~60%)

**Auto-scaling (optionnel pour économies):**
- Scheduled scaling: arrêt 19h-8h et weekends
- Script Lambda pour start/stop automatique

**Livrables:**
- [ ] Module EC2 créé avec variables
- [ ] User data scripts préparés
- [ ] Security groups configurés
- [ ] EBS volumes configurés

---

### Étape 2.5: Module Application Load Balancer
**Fichier: `terraform/modules/alb/main.tf`**

**Configuration:**
- 1 ALB pour tous les services (économie)
- Target Groups par service:
  - `apim-gateway-tg` (port 9072)
  - `apim-portal-tg` (port 18101)
  - `jenkins-tg` (port 8080)
- Listener Rules basés sur hostname
- SSL/TLS avec ACM certificate
- Health checks configurés

**Hostnames:**
```
gateway.apim-dev.votredomaine.com  -> webMethods Gateway
portal.apim-dev.votredomaine.com   -> Developer Portal
jenkins.apim-dev.votredomaine.com  -> Jenkins
```

**Livrables:**
- [ ] ALB créé
- [ ] Target Groups configurés
- [ ] Listener Rules définis
- [ ] Health checks configurés

---

### Étape 2.6: Module OpenSearch (Économique)
**Fichier: `terraform/modules/opensearch/main.tf`**

**Configuration économique:**
- Service: OpenSearch Managed
- Instance type: `t3.small.search` (1 instance pour DEV)
- Storage: 20 GB gp3
- Master nodes: Non (économie)
- Dedicated master: Non
- Replicas: 0 (DEV/TEST)
- Snapshot: S3 (1x par jour)

**Alternative ultra-économique:**
- OpenSearch sur EC2 t3.small avec Docker
- Coût: ~$15/mois vs ~$30/mois managed

**Accès:**
- VPC interne uniquement
- Kibana enabled
- Fine-grained access control

**Livrables:**
- [ ] Domain OpenSearch créé
- [ ] Access policies configurées
- [ ] Kibana accessible
- [ ] Index templates créés

---

### Étape 2.7: Module S3
**Fichier: `terraform/modules/s3/main.tf`**

**Buckets à créer:**
1. **apim-artifacts-{env}**: Artifacts Jenkins, packages
2. **apim-backups-{env}**: Backups Vault, configs
3. **apim-logs-{env}**: Logs applicatifs (optionnel)

**Configuration:**
- Versioning: enabled sur backups
- Lifecycle: 30 jours puis Glacier (économie)
- Encryption: SSE-S3
- Public access: blocked

**Livrables:**
- [ ] Buckets S3 créés
- [ ] Policies configurées
- [ ] Lifecycle rules définies

---

### Étape 2.8: Déploiement infrastructure
**Fichier: `terraform/environments/dev/main.tf`**

**Actions:**
```bash
cd terraform/environments/dev
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

**Variables à définir (`terraform.tfvars`):**
```hcl
environment         = "dev"
vpc_cidr           = "10.0.0.0/16"
aws_region         = "eu-west-1"
availability_zones = ["eu-west-1a", "eu-west-1b"]

# Instances
webmethods_instance_type = "t3.large"
portal_instance_type     = "t3.medium"
jenkins_instance_type    = "t3.medium"
vault_instance_type      = "t3.small"

# OpenSearch
opensearch_instance_type = "t3.small.search"
opensearch_volume_size   = 20

# Tags
tags = {
  Project     = "APIM"
  Environment = "dev"
  ManagedBy   = "Terraform"
}
```

**Livrables:**
- [ ] Infrastructure déployée
- [ ] Outputs récupérés (IPs, DNS, etc.)
- [ ] State sauvegardé dans S3

---

## Phase 3: HashiCorp Vault

### Étape 3.1: Installation Vault sur EC2
**Fichier: `ansible/playbooks/vault.yml`**

**Actions:**
1. Installer Vault sur instance t3.small
2. Configurer backend storage: S3 (économique)
3. Configurer seal: AWS KMS (automatique)
4. Initialize Vault
5. Configurer policies
6. Activer secret engines:
   - KV v2 (pour credentials)
   - AWS (pour dynamic credentials)
   - Database (pour OpenSearch)

**Configuration Vault (`/etc/vault/config.hcl`):**
```hcl
storage "s3" {
  bucket = "apim-vault-storage-dev"
  region = "eu-west-1"
}

seal "awskms" {
  kms_key_id = "arn:aws:kms:eu-west-1:ACCOUNT:key/KEY_ID"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = 0
  tls_cert_file = "/etc/vault/tls/cert.pem"
  tls_key_file  = "/etc/vault/tls/key.pem"
}
```

**Secrets à stocker:**
- Credentials webMethods (admin, users)
- Credentials OpenSearch
- GitHub tokens
- IDP credentials
- Database passwords
- API keys

**Livrables:**
- [ ] Vault installé et initialisé
- [ ] Root tokens sauvegardés en sécurité
- [ ] Unseal keys sauvegardées
- [ ] Secret engines activés
- [ ] Policies créées

---

### Étape 3.2: Intégration Vault avec services
**Actions:**
1. Configurer AppRole authentication pour chaque service
2. Créer policies par service
3. Configurer Vault Agent sur chaque instance
4. Templates pour injection de secrets

**Exemple policy webMethods:**
```hcl
path "secret/data/webmethods/*" {
  capabilities = ["read"]
}

path "database/creds/opensearch" {
  capabilities = ["read"]
}
```

**Livrables:**
- [ ] AppRoles créés
- [ ] Vault Agents configurés
- [ ] Templates de secrets déployés

---

## Phase 4: Configuration des Services (Ansible)

### Étape 4.1: Playbook Common
**Fichier: `ansible/roles/common/tasks/main.yml`**

**Tâches:**
- Mise à jour système
- Installation packages de base (jq, curl, wget, vim)
- Configuration timezone
- Configuration NTP
- Installation CloudWatch Agent
- Configuration SSH hardening
- Installation Vault Agent
- Configuration logs vers CloudWatch

**Livrables:**
- [ ] Role common créé
- [ ] Playbook testé

---

### Étape 4.2: Installation webMethods Gateway
**Fichier: `ansible/roles/webmethods/tasks/main.yml`**

**Prérequis:**
- Licence webMethods (DEV/TEST)
- Installer webMethods (téléchargement depuis Software AG)

**Tâches:**
1. Installer Java 11 (requis par webMethods)
2. Télécharger webMethods API Gateway installer
3. Installation silencieuse:
   ```bash
   ./install.sh -console -options response.txt
   ```
4. Configuration des ports:
   - UI: 9072
   - Runtime: 5555
   - Elasticsearch interne: 9240
5. Configurer connexion à OpenSearch externe
6. Configurer intégration IDP (OIDC/SAML)
7. Importer API definitions depuis GitHub
8. Configurer policies de base

**Configuration webMethods:**
```yaml
webmethods_home: /opt/softwareag
webmethods_port: 9072
webmethods_admin_user: "{{ vault_webmethods_admin }}"
webmethods_admin_password: "{{ vault_webmethods_password }}"
opensearch_endpoint: "{{ opensearch_domain_endpoint }}"
```

**Livrables:**
- [ ] webMethods Gateway installé
- [ ] Configuration de base appliquée
- [ ] Connexion OpenSearch validée
- [ ] Service systemd créé

---

### Étape 4.3: Installation Developer Portal
**Fichier: `ansible/roles/portal/tasks/main.yml`**

**Tâches:**
1. Installer webMethods Developer Portal
2. Configuration ports: 18101 (HTTPS), 18102 (HTTP)
3. Connexion au Gateway
4. Configuration SMTP (pour notifications)
5. Branding personnalisé
6. Configuration IDP (SSO)

**Configuration:**
```yaml
portal_home: /opt/softwareag
portal_port: 18101
gateway_url: "https://gateway.apim-dev.votredomaine.com"
smtp_host: "{{ vault_smtp_host }}"
smtp_user: "{{ vault_smtp_user }}"
```

**Livrables:**
- [ ] Developer Portal installé
- [ ] Connecté au Gateway
- [ ] Personnalisation appliquée
- [ ] SSO configuré

---

### Étape 4.4: Installation Jenkins
**Fichier: `ansible/roles/jenkins/tasks/main.yml`**

**Tâches:**
1. Installer Java 17
2. Installer Jenkins LTS
3. Installer plugins essentiels:
   - Pipeline
   - Git
   - Ansible
   - Terraform
   - AWS
   - Vault
   - Blue Ocean
4. Configuration JCasC (Jenkins Configuration as Code)
5. Créer credentials pour:
   - GitHub
   - AWS
   - Vault
   - webMethods

**Plugins requis:**
```
pipeline-stage-view
git
ansible
terraform
aws-credentials
hashicorp-vault-plugin
blueocean
pipeline-utility-steps
```

**Configuration JCasC (`jenkins.yaml`):**
```yaml
jenkins:
  systemMessage: "API Management CI/CD Platform"
  securityRealm:
    oidc:
      clientId: "${OIDC_CLIENT_ID}"
      clientSecret: "${OIDC_CLIENT_SECRET}"
  authorizationStrategy:
    projectMatrix:
      permissions:
        - "Overall/Administer:admin"
        - "Overall/Read:authenticated"
```

**Livrables:**
- [ ] Jenkins installé
- [ ] Plugins installés
- [ ] JCasC configuré
- [ ] Credentials créés
- [ ] Pipelines importés

---

### Étape 4.5: Configuration OpenSearch
**Fichier: `ansible/playbooks/opensearch-config.yml`**

**Tâches:**
1. Créer index templates pour:
   - API Gateway logs
   - Transaction logs
   - Performance metrics
   - Audit logs
2. Créer dashboards Kibana:
   - API Traffic
   - Error rates
   - Response times
   - Top consumers
3. Configurer alerting (optionnel)
4. Configurer retention (30 jours pour DEV)

**Index templates:**
```json
{
  "index_patterns": ["apim-gateway-logs-*"],
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 0
  },
  "mappings": {
    "properties": {
      "timestamp": { "type": "date" },
      "api_name": { "type": "keyword" },
      "response_time": { "type": "integer" },
      "status_code": { "type": "integer" }
    }
  }
}
```

**Livrables:**
- [ ] Index templates créés
- [ ] Dashboards importés
- [ ] Retention configurée
- [ ] Accès validé depuis Gateway

---

## Phase 5: Identity Provider (IDP)

### Étape 5.1: Configuration IDP
**Options recommandées (coût DEV/TEST):**

**Option 1: Keycloak (Gratuit, self-hosted)**
- Installation sur t3.small
- Base de données: RDS PostgreSQL db.t3.micro (~$15/mois)
- Haute disponibilité: Non (DEV/TEST)

**Option 2: AWS Cognito (Pay-as-you-go)**
- Coût: Gratuit jusqu'à 50,000 MAU
- Recommandé pour DEV/TEST
- Intégration native AWS

**Option 3: Okta Developer (Gratuit)**
- Jusqu'à 1000 users
- Idéal pour DEV/TEST

**Recommandation: AWS Cognito pour DEV/TEST**

**Configuration Cognito:**
```hcl
# terraform/modules/cognito/main.tf
resource "aws_cognito_user_pool" "apim" {
  name = "apim-dev-users"

  password_policy {
    minimum_length    = 8
    require_uppercase = true
    require_lowercase = true
    require_numbers   = true
  }

  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
  }

  # Custom attributes pour les tenants et rôles
  schema {
    name                     = "tenant_id"
    attribute_data_type      = "String"
    mutable                  = true
    required                 = false
  }

  schema {
    name                     = "role"
    attribute_data_type      = "String"
    mutable                  = true
    required                 = false
  }
}

resource "aws_cognito_user_pool_client" "gateway" {
  name         = "webmethods-gateway"
  user_pool_id = aws_cognito_user_pool.apim.id

  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  allowed_oauth_flows_user_pool_client = true
  callback_urls                        = ["https://gateway.apim-dev.votredomaine.com/callback"]

  # JWT customization
  id_token_validity  = 60  # minutes
  access_token_validity = 60
  refresh_token_validity = 30  # days
}

resource "aws_cognito_user_pool_client" "control_plane" {
  name         = "control-plane-api"
  user_pool_id = aws_cognito_user_pool.apim.id

  allowed_oauth_flows                  = ["client_credentials"]
  allowed_oauth_scopes                 = ["apim/admin", "apim/developer"]
  allowed_oauth_flows_user_pool_client = true

  generate_secret = true
}

# Resource Server pour scopes personnalisés
resource "aws_cognito_resource_server" "apim" {
  identifier   = "apim"
  name         = "APIM Resource Server"
  user_pool_id = aws_cognito_user_pool.apim.id

  scope {
    scope_name        = "admin"
    scope_description = "Full admin access to APIM platform"
  }

  scope {
    scope_name        = "developer"
    scope_description = "Developer access to manage APIs in their tenant"
  }

  scope {
    scope_name        = "devops"
    scope_description = "DevOps access for CI/CD operations"
  }
}
```

**Groupes Cognito à créer:**
- `apim-admins`: Admin complet plateforme
- `apim-cpi`: Équipe CPI (peut gérer tous les tenants)
- `apim-devops`: Équipe DevOps (CI/CD, monitoring)
- `tenant-{tenant-id}-admins`: Admin d'un tenant spécifique
- `tenant-{tenant-id}-developers`: Développeurs d'un tenant

**Applications à intégrer:**
- webMethods Gateway (OIDC)
- Developer Portal (OIDC)
- Jenkins (OIDC)
- Kibana (OIDC)
- Control Plane API (OAuth2 Client Credentials)

**Livrables:**
- [ ] IDP configuré (Cognito)
- [ ] User pool créé avec custom attributes
- [ ] Resource Server et scopes créés
- [ ] App clients créés (Gateway, Portal, Jenkins, Control Plane)
- [ ] Groupes créés
- [ ] Utilisateurs de test créés par groupe
- [ ] SSO testé sur chaque service

---

### Étape 5.2: Multi-Tenancy webMethods
**Configuration des tenants dans webMethods:**

webMethods API Gateway ne supporte pas nativement le multi-tenancy complet, mais on peut le simuler via:

1. **API Scopes et Teams:**
   - Créer des "Teams" dans webMethods = Tenants
   - Assigner des APIs à des Teams
   - Gérer les permissions par Team

2. **Custom Attributes JWT:**
   - Configurer webMethods pour extraire `tenant_id` du JWT
   - Appliquer des policies basées sur le tenant
   - Filtrer les APIs visibles par tenant dans le Portal

**Configuration webMethods (`application.properties`):**
```properties
# JWT Configuration
apigw.jwt.issuer=https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_XXXXX
apigw.jwt.audience=control-plane-api
apigw.jwt.claims.tenant=custom:tenant_id
apigw.jwt.claims.role=custom:role

# Multi-tenancy
apigw.multitenancy.enabled=true
apigw.multitenancy.claim=custom:tenant_id
```

**Playbook Ansible pour configuration:**
```yaml
# ansible/roles/webmethods/tasks/multitenancy.yml
---
- name: Configure JWT validation
  template:
    src: application.properties.j2
    dest: /opt/softwareag/IntegrationServer/instances/default/config/application.properties
  notify: restart webmethods

- name: Create default teams (tenants)
  uri:
    url: "https://localhost:9072/rest/apigateway/teams"
    method: POST
    user: "{{ webmethods_admin_user }}"
    password: "{{ webmethods_admin_password }}"
    body_format: json
    body:
      name: "{{ item.name }}"
      description: "{{ item.description }}"
      teamMembers: []
    validate_certs: no
  loop:
    - { name: "tenant-acme", description: "ACME Corporation Tenant" }
    - { name: "tenant-globex", description: "Globex Inc Tenant" }
  ignore_errors: yes  # Ignore if already exists
```

**Livrables:**
- [ ] Teams/Tenants créés dans webMethods
- [ ] JWT validation configurée
- [ ] Mapping tenant_id <-> Team configuré
- [ ] Policies de filtrage par tenant créées
- [ ] Tests de séparation des données par tenant

---

## Phase 5.5: Control Plane API

### Étape 5.5.1: Architecture du Control Plane
**Objectif:** API de gestion permettant aux équipes CPI et DevOps de gérer leur tenant webMethods via token JWT.

**Stack technique recommandée:**
- **Langage**: Python (FastAPI) ou Node.js (Express)
- **Authentication**: JWT via AWS Cognito
- **Authorization**: RBAC basé sur groupes Cognito
- **Storage**: DynamoDB (pour métadonnées) + S3 (artifacts)
- **Déploiement**: ECS Fargate ou Lambda + API Gateway

**Option 1: ECS Fargate (Recommandée pour DEV/TEST)**
- Coût: ~$15-20/mois (Fargate Spot)
- Plus flexible, stateful possible
- Logs CloudWatch natifs

**Option 2: Lambda + API Gateway**
- Coût: ~$5-10/mois (très faible trafic)
- Serverless, scaling automatique
- Cold start possible

**Recommandation: ECS Fargate pour simplicité et coûts prévisibles**

**Composants:**
```
┌─────────────────────────────────────────────────────┐
│                  Control Plane API                   │
│                                                      │
│  ┌────────────┐      ┌─────────────┐               │
│  │  Auth      │      │  Tenant     │               │
│  │  Service   │──────│  Service    │               │
│  └────────────┘      └─────────────┘               │
│        │                    │                       │
│        │             ┌──────┴──────┐                │
│        │             │             │                │
│  ┌────────────┐  ┌────────────┐ ┌────────────┐    │
│  │  API       │  │  App       │ │  Policy    │    │
│  │  Service   │  │  Service   │ │  Service   │    │
│  └────────────┘  └────────────┘ └────────────┘    │
│        │                │              │           │
│        └────────────────┴──────────────┘           │
│                         │                          │
│              ┌──────────┴──────────┐               │
│              │                     │               │
│         webMethods            DynamoDB            │
│         REST API          (metadata cache)         │
│                                                     │
└─────────────────────────────────────────────────────┘
```

**Livrables:**
- [ ] Architecture validée
- [ ] Stack technique choisie
- [ ] Schéma de données DynamoDB défini

---

### Étape 5.5.2: Développement Control Plane API
**Structure du projet:**
```
control-plane-api/
├── src/
│   ├── main.py
│   ├── config/
│   │   └── settings.py
│   ├── middleware/
│   │   ├── auth.py
│   │   └── rbac.py
│   ├── models/
│   │   ├── api.py
│   │   ├── application.py
│   │   ├── tenant.py
│   │   └── policy.py
│   ├── services/
│   │   ├── webmethods_client.py
│   │   ├── cognito_service.py
│   │   └── dynamodb_service.py
│   ├── routers/
│   │   ├── apis.py
│   │   ├── applications.py
│   │   ├── tenants.py
│   │   └── policies.py
│   └── utils/
│       ├── jwt_validator.py
│       └── logger.py
├── tests/
├── Dockerfile
├── requirements.txt
└── README.md
```

**Exemple API endpoints:**
```python
# src/main.py
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List, Optional
import jwt
import boto3
import httpx

app = FastAPI(title="APIM Control Plane API")
security = HTTPBearer()

# JWT Validation Middleware
async def validate_jwt(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        # Validate JWT with Cognito
        payload = jwt.decode(
            token,
            options={"verify_signature": False}  # In prod: verify with Cognito public keys
        )

        # Extract tenant_id and role
        tenant_id = payload.get("custom:tenant_id")
        role = payload.get("custom:role")
        groups = payload.get("cognito:groups", [])

        return {
            "user_id": payload.get("sub"),
            "tenant_id": tenant_id,
            "role": role,
            "groups": groups,
            "email": payload.get("email")
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# Check RBAC permissions
def check_permission(required_role: str):
    def permission_checker(user = Depends(validate_jwt)):
        # Admin can do anything
        if "apim-admins" in user["groups"] or "apim-cpi" in user["groups"]:
            return user

        # Check specific role
        if user["role"] == required_role or f"apim-{required_role}" in user["groups"]:
            return user

        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return permission_checker

# webMethods Client
class WebMethodsClient:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url
        self.auth = (username, password)

    async def create_api(self, api_data: dict, tenant_id: str):
        """Create API in webMethods and assign to tenant team"""
        async with httpx.AsyncClient() as client:
            # Create API
            response = await client.post(
                f"{self.base_url}/rest/apigateway/apis",
                json=api_data,
                auth=self.auth
            )

            if response.status_code != 201:
                raise HTTPException(status_code=response.status_code, detail="Failed to create API")

            api_id = response.json()["apiResponse"]["api"]["id"]

            # Assign to team (tenant)
            await client.put(
                f"{self.base_url}/rest/apigateway/apis/{api_id}/teams/{tenant_id}",
                auth=self.auth
            )

            return response.json()

    async def list_apis(self, tenant_id: str):
        """List APIs for a specific tenant"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/rest/apigateway/apis",
                params={"teamName": tenant_id},
                auth=self.auth
            )
            return response.json()

# Initialize webMethods client (get credentials from Vault)
wm_client = WebMethodsClient(
    base_url="https://gateway.apim-dev.votredomaine.com",
    username="admin",  # From Vault
    password="password"  # From Vault
)

# ============= API Endpoints =============

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

# ------------- APIs Management -------------

@app.post("/v1/tenants/{tenant_id}/apis", status_code=201)
async def create_api(
    tenant_id: str,
    api_data: dict,
    user = Depends(check_permission("developer"))
):
    """
    Create a new API in the tenant

    Requires: developer or devops role
    """
    # Verify user has access to this tenant
    if user["tenant_id"] != tenant_id and "apim-cpi" not in user["groups"]:
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    # Create API via webMethods
    result = await wm_client.create_api(api_data, f"tenant-{tenant_id}")

    # Store metadata in DynamoDB
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('apim-apis-metadata')
    table.put_item(Item={
        "api_id": result["apiResponse"]["api"]["id"],
        "tenant_id": tenant_id,
        "created_by": user["email"],
        "created_at": result["apiResponse"]["api"]["createdDate"],
        "status": "active"
    })

    return result

@app.get("/v1/tenants/{tenant_id}/apis")
async def list_apis(
    tenant_id: str,
    user = Depends(validate_jwt)
):
    """
    List all APIs in the tenant

    Users can only see APIs from their tenant
    """
    # Verify access
    if user["tenant_id"] != tenant_id and "apim-cpi" not in user["groups"]:
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    apis = await wm_client.list_apis(f"tenant-{tenant_id}")
    return apis

@app.delete("/v1/tenants/{tenant_id}/apis/{api_id}")
async def delete_api(
    tenant_id: str,
    api_id: str,
    user = Depends(check_permission("developer"))
):
    """Delete an API from the tenant"""
    # Verify ownership
    if user["tenant_id"] != tenant_id and "apim-cpi" not in user["groups"]:
        raise HTTPException(status_code=403, detail="Access denied")

    async with httpx.AsyncClient() as client:
        response = await client.delete(
            f"{wm_client.base_url}/rest/apigateway/apis/{api_id}",
            auth=wm_client.auth
        )

        if response.status_code != 204:
            raise HTTPException(status_code=response.status_code, detail="Failed to delete API")

    return {"message": "API deleted successfully"}

# ------------- Applications Management -------------

@app.post("/v1/tenants/{tenant_id}/applications", status_code=201)
async def create_application(
    tenant_id: str,
    app_data: dict,
    user = Depends(check_permission("developer"))
):
    """
    Create a new application (API consumer) in the tenant
    """
    if user["tenant_id"] != tenant_id and "apim-cpi" not in user["groups"]:
        raise HTTPException(status_code=403, detail="Access denied")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{wm_client.base_url}/rest/apigateway/applications",
            json={**app_data, "teamName": f"tenant-{tenant_id}"},
            auth=wm_client.auth
        )

        if response.status_code != 201:
            raise HTTPException(status_code=response.status_code, detail="Failed to create application")

        return response.json()

@app.get("/v1/tenants/{tenant_id}/applications")
async def list_applications(
    tenant_id: str,
    user = Depends(validate_jwt)
):
    """List all applications in the tenant"""
    if user["tenant_id"] != tenant_id and "apim-cpi" not in user["groups"]:
        raise HTTPException(status_code=403, detail="Access denied")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{wm_client.base_url}/rest/apigateway/applications",
            params={"teamName": f"tenant-{tenant_id}"},
            auth=wm_client.auth
        )
        return response.json()

# ------------- Policies Management -------------

@app.put("/v1/tenants/{tenant_id}/apis/{api_id}/policies")
async def update_api_policies(
    tenant_id: str,
    api_id: str,
    policies: List[dict],
    user = Depends(check_permission("devops"))
):
    """
    Update policies for an API

    Requires: devops role
    """
    if user["tenant_id"] != tenant_id and "apim-cpi" not in user["groups"]:
        raise HTTPException(status_code=403, detail="Access denied")

    async with httpx.AsyncClient() as client:
        response = await client.put(
            f"{wm_client.base_url}/rest/apigateway/apis/{api_id}/policies",
            json={"policy": policies},
            auth=wm_client.auth
        )

        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Failed to update policies")

        return response.json()

# ------------- Tenant Management (CPI only) -------------

@app.post("/v1/tenants", status_code=201)
async def create_tenant(
    tenant_data: dict,
    user = Depends(check_permission("cpi"))
):
    """
    Create a new tenant (CPI only)
    """
    tenant_id = tenant_data["tenant_id"]

    # Create Team in webMethods
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{wm_client.base_url}/rest/apigateway/teams",
            json={
                "name": f"tenant-{tenant_id}",
                "description": tenant_data.get("description", "")
            },
            auth=wm_client.auth
        )

        if response.status_code != 201:
            raise HTTPException(status_code=response.status_code, detail="Failed to create tenant")

    # Create Cognito group
    cognito = boto3.client('cognito-idp')
    cognito.create_group(
        UserPoolId='eu-west-1_XXXXX',
        GroupName=f"tenant-{tenant_id}-admins",
        Description=f"Admins for tenant {tenant_id}"
    )
    cognito.create_group(
        UserPoolId='eu-west-1_XXXXX',
        GroupName=f"tenant-{tenant_id}-developers",
        Description=f"Developers for tenant {tenant_id}"
    )

    # Store in DynamoDB
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('apim-tenants')
    table.put_item(Item={
        "tenant_id": tenant_id,
        "name": tenant_data["name"],
        "created_by": user["email"],
        "status": "active"
    })

    return {"tenant_id": tenant_id, "status": "created"}

@app.get("/v1/tenants")
async def list_tenants(user = Depends(validate_jwt)):
    """
    List tenants

    - CPI: see all tenants
    - Others: see only their tenant
    """
    if "apim-cpi" in user["groups"] or "apim-admins" in user["groups"]:
        # Return all tenants
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table('apim-tenants')
        response = table.scan()
        return response['Items']
    else:
        # Return only user's tenant
        return [{"tenant_id": user["tenant_id"]}]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

**Dockerfile:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**requirements.txt:**
```
fastapi==0.104.1
uvicorn[standard]==0.24.0
python-jose[cryptography]==3.3.0
boto3==1.29.7
httpx==0.25.1
pydantic==2.5.0
pydantic-settings==2.1.0
```

**Livrables:**
- [ ] API Control Plane développée
- [ ] Endpoints CRUD pour APIs, Apps, Policies
- [ ] JWT validation implémentée
- [ ] RBAC par tenant et rôle
- [ ] Tests unitaires
- [ ] Documentation OpenAPI/Swagger

---

### Étape 5.5.3: Déploiement Control Plane sur ECS Fargate
**Fichier: `terraform/modules/control-plane/main.tf`**

```hcl
# ECR Repository
resource "aws_ecr_repository" "control_plane" {
  name                 = "apim-control-plane"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

# ECS Cluster
resource "aws_ecs_cluster" "apim" {
  name = "apim-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

# Task Definition
resource "aws_ecs_task_definition" "control_plane" {
  family                   = "control-plane-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "control-plane-api"
      image     = "${aws_ecr_repository.control_plane.repository_url}:latest"
      essential = true

      portMappings = [
        {
          containerPort = 8000
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "ENVIRONMENT"
          value = var.environment
        },
        {
          name  = "WEBMETHODS_URL"
          value = "https://gateway.apim-dev.votredomaine.com"
        },
        {
          name  = "COGNITO_USER_POOL_ID"
          value = var.cognito_user_pool_id
        },
        {
          name  = "COGNITO_REGION"
          value = var.aws_region
        }
      ]

      secrets = [
        {
          name      = "WEBMETHODS_USERNAME"
          valueFrom = "${var.vault_arn}:webmethods_username::"
        },
        {
          name      = "WEBMETHODS_PASSWORD"
          valueFrom = "${var.vault_arn}:webmethods_password::"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/control-plane-api"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
    }
  ])
}

# ECS Service
resource "aws_ecs_service" "control_plane" {
  name            = "control-plane-api"
  cluster         = aws_ecs_cluster.apim.id
  task_definition = aws_ecs_task_definition.control_plane.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = var.private_subnet_ids
    security_groups = [aws_security_group.control_plane.id]
  }

  load_balancer {
    target_group_arn = var.control_plane_target_group_arn
    container_name   = "control-plane-api"
    container_port   = 8000
  }

  # For DEV: Use Fargate Spot for cost savings
  capacity_provider_strategy {
    capacity_provider = "FARGATE_SPOT"
    weight            = 100
  }
}

# Security Group
resource "aws_security_group" "control_plane" {
  name        = "control-plane-api-${var.environment}"
  description = "Security group for Control Plane API"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [var.alb_security_group_id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# DynamoDB Tables
resource "aws_dynamodb_table" "tenants" {
  name           = "apim-tenants-${var.environment}"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "tenant_id"

  attribute {
    name = "tenant_id"
    type = "S"
  }

  tags = var.tags
}

resource "aws_dynamodb_table" "apis_metadata" {
  name           = "apim-apis-metadata-${var.environment}"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "api_id"
  range_key      = "tenant_id"

  attribute {
    name = "api_id"
    type = "S"
  }

  attribute {
    name = "tenant_id"
    type = "S"
  }

  global_secondary_index {
    name            = "tenant-index"
    hash_key        = "tenant_id"
    projection_type = "ALL"
  }

  tags = var.tags
}

# IAM Roles
resource "aws_iam_role" "ecs_execution" {
  name = "control-plane-ecs-execution-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "ecs_task" {
  name = "control-plane-ecs-task-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "ecs_task" {
  name = "control-plane-task-policy"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.tenants.arn,
          aws_dynamodb_table.apis_metadata.arn,
          "${aws_dynamodb_table.apis_metadata.arn}/index/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "cognito-idp:AdminCreateUser",
          "cognito-idp:AdminDeleteUser",
          "cognito-idp:CreateGroup",
          "cognito-idp:AdminAddUserToGroup"
        ]
        Resource = var.cognito_user_pool_arn
      }
    ]
  })
}
```

**Ajout du Target Group dans ALB:**
```hcl
# terraform/modules/alb/main.tf
resource "aws_lb_target_group" "control_plane" {
  name        = "control-plane-tg-${var.environment}"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    enabled             = true
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    matcher             = "200"
  }
}

resource "aws_lb_listener_rule" "control_plane" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 40

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.control_plane.arn
  }

  condition {
    host_header {
      values = ["api.apim-dev.votredomaine.com"]
    }
  }
}
```

**Livrables:**
- [ ] ECR repository créé
- [ ] ECS Cluster et Service déployés
- [ ] DynamoDB tables créées
- [ ] IAM roles configurés
- [ ] Target Group ALB configuré
- [ ] DNS api.apim-dev.votredomaine.com pointant vers ALB

---

### Étape 5.5.4: Scripts de déploiement
**Fichier: `control-plane-api/deploy.sh`**

```bash
#!/bin/bash

set -e

ENVIRONMENT=${1:-dev}
AWS_REGION=${2:-eu-west-1}
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/apim-control-plane"

echo "Building Control Plane API..."
docker build -t apim-control-plane:latest .

echo "Tagging image..."
docker tag apim-control-plane:latest ${ECR_REPO}:latest
docker tag apim-control-plane:latest ${ECR_REPO}:${ENVIRONMENT}-$(date +%Y%m%d-%H%M%S)

echo "Logging into ECR..."
aws ecr get-login-password --region ${AWS_REGION} | \
  docker login --username AWS --password-stdin ${ECR_REPO}

echo "Pushing image to ECR..."
docker push ${ECR_REPO}:latest
docker push ${ECR_REPO}:${ENVIRONMENT}-$(date +%Y%m%d-%H%M%S)

echo "Updating ECS service..."
aws ecs update-service \
  --cluster apim-${ENVIRONMENT} \
  --service control-plane-api \
  --force-new-deployment \
  --region ${AWS_REGION}

echo "Deployment initiated. Check ECS console for progress."
```

**Pipeline Jenkins:**
```groovy
// jenkins/pipelines/deploy-control-plane.jenkinsfile
pipeline {
    agent any

    environment {
        AWS_REGION = 'eu-west-1'
        ENVIRONMENT = 'dev'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Test') {
            steps {
                dir('control-plane-api') {
                    sh '''
                        python -m venv venv
                        . venv/bin/activate
                        pip install -r requirements.txt
                        pip install pytest pytest-cov
                        pytest tests/ --cov=src
                    '''
                }
            }
        }

        stage('Build & Deploy') {
            steps {
                dir('control-plane-api') {
                    sh './deploy.sh ${ENVIRONMENT} ${AWS_REGION}'
                }
            }
        }

        stage('Verify Deployment') {
            steps {
                sh '''
                    sleep 30
                    curl -f https://api.apim-dev.votredomaine.com/health || exit 1
                '''
            }
        }
    }

    post {
        always {
            cleanWs()
        }
    }
}
```

**Livrables:**
- [ ] Script de déploiement créé
- [ ] Pipeline Jenkins configuré
- [ ] Tests automatisés en place
- [ ] Health check validé après déploiement

---

## Phase 6: CI/CD et GitOps

### Étape 6.1: Structure GitHub
**Repository structure:**
```
apim-apis/
├── apis/
│   ├── petstore/
│   │   ├── swagger.yaml
│   │   ├── policies.json
│   │   └── metadata.json
│   └── payment/
│       ├── swagger.yaml
│       ├── policies.json
│       └── metadata.json
├── policies/
│   ├── rate-limiting.json
│   ├── authentication.json
│   └── logging.json
└── pipelines/
    └── deploy-api.jenkinsfile
```

**Branches:**
- `main`: Production (pour futur PROD)
- `develop`: Integration
- `feature/*`: Développement

**Livrables:**
- [ ] Repository apim-apis créé
- [ ] Structure mise en place
- [ ] Branch protection configurée

---

### Étape 6.2: Pipelines Jenkins
**Fichier: `jenkins/pipelines/deploy-api.jenkinsfile`**

**Pipeline: Déploiement d'API**
```groovy
pipeline {
    agent any

    environment {
        VAULT_ADDR = 'https://vault.apim-dev.votredomaine.com'
        GATEWAY_URL = 'https://gateway.apim-dev.votredomaine.com'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Validate API Definition') {
            steps {
                sh '''
                    # Validate Swagger/OpenAPI
                    swagger-cli validate apis/${API_NAME}/swagger.yaml
                '''
            }
        }

        stage('Get Secrets from Vault') {
            steps {
                withVault([
                    vaultSecrets: [[
                        path: 'secret/webmethods',
                        secretValues: [
                            [envVar: 'GATEWAY_USER', vaultKey: 'username'],
                            [envVar: 'GATEWAY_PASS', vaultKey: 'password']
                        ]
                    ]]
                ]) {
                    sh 'echo "Secrets retrieved"'
                }
            }
        }

        stage('Deploy to Gateway') {
            steps {
                script {
                    sh '''
                        curl -X POST ${GATEWAY_URL}/rest/apigateway/apis \
                            -u ${GATEWAY_USER}:${GATEWAY_PASS} \
                            -H "Content-Type: application/json" \
                            -d @apis/${API_NAME}/swagger.yaml
                    '''
                }
            }
        }

        stage('Apply Policies') {
            steps {
                sh '''
                    curl -X PUT ${GATEWAY_URL}/rest/apigateway/apis/${API_ID}/policies \
                        -u ${GATEWAY_USER}:${GATEWAY_PASS} \
                        -H "Content-Type: application/json" \
                        -d @apis/${API_NAME}/policies.json
                '''
            }
        }

        stage('Test API') {
            steps {
                sh '''
                    # Run basic smoke tests
                    newman run tests/${API_NAME}/postman_collection.json
                '''
            }
        }
    }

    post {
        always {
            cleanWs()
        }
    }
}
```

**Pipelines à créer:**
1. `deploy-api`: Déploiement d'API
2. `update-policies`: Mise à jour policies
3. `backup-gateway`: Backup configuration
4. `infrastructure-update`: Terraform apply
5. `security-scan`: Scan sécurité APIs

**Livrables:**
- [ ] Pipelines créés dans Jenkins
- [ ] Webhooks GitHub configurés
- [ ] Tests automatisés
- [ ] Notifications configurées

---

### Étape 6.3: GitHub Actions pour Terraform
**Fichier: `.github/workflows/terraform-plan.yml`**

```yaml
name: Terraform Plan

on:
  pull_request:
    paths:
      - 'terraform/**'

jobs:
  terraform-plan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v2

      - name: Terraform Init
        run: terraform init
        working-directory: terraform/environments/dev

      - name: Terraform Plan
        run: terraform plan -out=tfplan
        working-directory: terraform/environments/dev
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}

      - name: Post Plan to PR
        uses: actions/github-script@v6
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: 'Terraform plan completed. Review the plan before merging.'
            })
```

**Workflows à créer:**
1. `terraform-plan.yml`: Plan sur PR
2. `terraform-apply.yml`: Apply sur merge vers main
3. `ansible-lint.yml`: Lint Ansible playbooks
4. `security-scan.yml`: Scan de sécurité

**Livrables:**
- [ ] GitHub Actions configurées
- [ ] Secrets GitHub configurés
- [ ] Workflows testés

---

## Phase 7: Monitoring et Observabilité

### Étape 7.1: CloudWatch Configuration
**Métriques à monitorer:**
1. **Infrastructure:**
   - CPU, Memory, Disk EC2
   - ALB request count, latency
   - NAT Gateway data processed

2. **Applications:**
   - webMethods: API calls, errors, latency
   - Jenkins: Build success/failure
   - OpenSearch: Cluster health

3. **Coûts:**
   - AWS Cost Explorer
   - Budget alerts

**CloudWatch Dashboards:**
```hcl
# terraform/modules/monitoring/dashboards.tf
resource "aws_cloudwatch_dashboard" "apim" {
  dashboard_name = "APIM-DEV-Overview"

  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/EC2", "CPUUtilization", {stat = "Average"}],
            ["AWS/ApplicationELB", "RequestCount"]
          ]
          period = 300
          region = "eu-west-1"
          title  = "Infrastructure Overview"
        }
      }
    ]
  })
}
```

**Alarms critiques:**
- High CPU (>80%)
- Disk space (<20%)
- API Gateway errors (>5%)
- Health check failures

**Livrables:**
- [ ] CloudWatch Dashboards créés
- [ ] Alarms configurées
- [ ] SNS topics pour notifications
- [ ] Budget alerts activés

---

### Étape 7.2: OpenSearch Dashboards
**Dashboards Kibana à créer:**

1. **API Traffic Overview:**
   - Total requests
   - Requests by API
   - Error rate
   - P95/P99 latency

2. **Error Analysis:**
   - Errors by type
   - Failed requests timeline
   - Top error endpoints

3. **Consumer Analytics:**
   - Top consumers
   - Requests by consumer
   - Consumer quotas

4. **Performance:**
   - Response time distribution
   - Slowest endpoints
   - Backend latency

**Livrables:**
- [ ] Dashboards créés
- [ ] Visualizations configurées
- [ ] Saved searches créées
- [ ] Export des dashboards en JSON

---

## Phase 8: Sécurité et Hardening

### Étape 8.1: Security Groups
**Règles strictes:**

**ALB Security Group:**
```
Inbound:
  - 443 from 0.0.0.0/0 (HTTPS public)
  - 80 from 0.0.0.0/0 (redirect to HTTPS)
Outbound:
  - All to VPC CIDR
```

**webMethods Security Group:**
```
Inbound:
  - 9072 from ALB SG
  - 5555 from VPC CIDR
Outbound:
  - 443 to 0.0.0.0/0 (updates, etc.)
  - 9200 to OpenSearch SG
```

**Livrables:**
- [ ] Security Groups configurés
- [ ] Principe du moindre privilège appliqué
- [ ] NACLs configurées (optionnel)

---

### Étape 8.2: Secrets Rotation
**Vault policies pour rotation:**
```hcl
# Rotation automatique tous les 90 jours
resource "vault_generic_secret" "webmethods_admin" {
  path = "secret/webmethods/admin"

  data_json = jsonencode({
    username = "admin"
    password = random_password.webmethods.result
  })
}

resource "random_password" "webmethods" {
  length  = 16
  special = true

  keepers = {
    rotation = timestamp()
  }
}
```

**Services à automatiser:**
- Database credentials
- API keys
- Admin passwords
- Certificates

**Livrables:**
- [ ] Rotation automatique configurée
- [ ] Notifications de rotation
- [ ] Procédure de rollback

---

### Étape 8.3: Backups
**Stratégie de backup:**

1. **Vault:**
   - Snapshot quotidien vers S3
   - Encryption avec KMS
   - Retention: 30 jours

2. **webMethods:**
   - Export configuration quotidien
   - API definitions backup
   - Stockage S3

3. **Jenkins:**
   - Backup jobs/configs
   - Plugin ThinBackup
   - Stockage S3

4. **OpenSearch:**
   - Snapshot repository S3
   - Snapshot quotidien
   - Retention: 7 jours DEV

**Scripts de backup:**
```bash
#!/bin/bash
# backup-gateway.sh
DATE=$(date +%Y%m%d)
BACKUP_DIR=/tmp/webmethods-backup-${DATE}

# Export APIs
curl -u admin:${PASSWORD} \
  https://gateway/rest/apigateway/archive \
  -o ${BACKUP_DIR}/apis.zip

# Upload to S3
aws s3 cp ${BACKUP_DIR}/apis.zip \
  s3://apim-backups-dev/webmethods/${DATE}/
```

**Livrables:**
- [ ] Scripts de backup créés
- [ ] Cron jobs configurés
- [ ] Tests de restore effectués
- [ ] Documentation restore

---

## Phase 9: Documentation et Formation

### Étape 9.1: Documentation Technique
**Documents à créer:**

1. **Architecture Diagram** (`docs/architecture.md`)
   - Schéma réseau
   - Flux de données
   - Composants et interactions

2. **Runbook** (`docs/runbook.md`)
   - Procédures de déploiement
   - Troubleshooting commun
   - Commandes utiles
   - Contacts escalade

3. **API Developer Guide** (`docs/api-guide.md`)
   - Comment créer une API
   - Standards et conventions
   - Exemples
   - Testing

4. **Operations Guide** (`docs/operations.md`)
   - Monitoring
   - Scaling
   - Backups/Restore
   - Incident response

**Livrables:**
- [ ] Documentation complète
- [ ] Diagrammes d'architecture
- [ ] Runbooks opérationnels
- [ ] Guides développeurs

---

### Étape 9.2: Formation Équipe
**Sessions de formation:**

1. **Infrastructure as Code:**
   - Terraform basics
   - Module management
   - State management

2. **Configuration Management:**
   - Ansible playbooks
   - Roles and variables
   - Vault integration

3. **API Management:**
   - webMethods Gateway
   - Policy configuration
   - Developer Portal usage

4. **CI/CD:**
   - Jenkins pipelines
   - GitOps workflow
   - Deployment procedures

**Livrables:**
- [ ] Supports de formation créés
- [ ] Sessions animées
- [ ] Hands-on labs
- [ ] Quiz de validation

---

## Phase 10: Tests et Validation

### Étape 10.1: Tests d'intégration
**Scénarios à tester:**

1. **Déploiement d'API:**
   - Commit dans GitHub
   - Trigger pipeline Jenkins
   - Déploiement sur Gateway
   - Validation dans Portal

2. **Authentification:**
   - Login via IDP
   - Token JWT généré
   - Accès aux APIs protégées

3. **Monitoring:**
   - Requêtes API
   - Logs dans OpenSearch
   - Métriques CloudWatch
   - Dashboards à jour

4. **Secrets Management:**
   - Rotation de credentials
   - Injection via Vault
   - Pas de secrets en clair

**Livrables:**
- [ ] Test plans créés
- [ ] Tests exécutés
- [ ] Résultats documentés
- [ ] Issues résolues

---

### Étape 10.2: Tests de charge (optionnel)
**Outils:**
- Apache JMeter
- K6
- Gatling

**Scénarios:**
- 100 req/s pendant 5 minutes
- Spike test
- Soak test (30 minutes)

**Métriques:**
- Response time P95/P99
- Error rate
- Throughput
- Resource utilization

**Livrables:**
- [ ] Tests de charge exécutés
- [ ] Résultats analysés
- [ ] Optimisations identifiées
- [ ] Baseline établie

---

## Phase 11: Optimisation des Coûts

### Étape 11.1: Cost Analysis
**Coût mensuel estimé (DEV):**

| Service | Type | Coût mensuel |
|---------|------|--------------|
| EC2 Instances | 4x (t3.large, t3.medium x2, t3.small) | ~$135 |
| OpenSearch | t3.small.search | ~$30 |
| ALB | 1 ALB | ~$20 |
| NAT Gateway | 1 NAT | ~$35 |
| S3 | ~100 GB | ~$3 |
| RDS (si Keycloak) | db.t3.micro | ~$15 |
| Data Transfer | ~50 GB | ~$5 |
| CloudWatch | Logs + Metrics | ~$10 |
| KMS | Keys | ~$5 |
| **TOTAL** | | **~$258/mois** |

**Avec optimisations (arrêt 19h-8h + weekends):**
- **Économie: ~60%**
- **Coût mensuel: ~$130-150**

---

### Étape 11.2: Actions d'optimisation
**Mesures à mettre en place:**

1. **Scheduled Stop/Start:**
   ```python
   # Lambda function
   import boto3

   def lambda_handler(event, context):
       ec2 = boto3.client('ec2')

       # Stop instances tagged with Environment=dev
       instances = ec2.describe_instances(
           Filters=[{'Name': 'tag:Environment', 'Values': ['dev']}]
       )

       if event['action'] == 'stop':
           for reservation in instances['Reservations']:
               for instance in reservation['Instances']:
                   ec2.stop_instances(InstanceIds=[instance['InstanceId']])
   ```

2. **EventBridge Rules:**
   - Stop: Lundi-Vendredi 19h
   - Start: Lundi-Vendredi 8h
   - Stop: Vendredi 19h (weekend)
   - Start: Lundi 8h

3. **S3 Lifecycle:**
   - 30 jours: Move to IA
   - 90 jours: Move to Glacier
   - 180 jours: Delete

4. **CloudWatch Logs Retention:**
   - DEV: 7 jours
   - TEST: 14 jours

5. **OpenSearch alternatives:**
   - Option 1: Managed t3.small.search (~$30)
   - Option 2: Self-hosted sur EC2 t3.small (~$15)
   - Recommandation: Self-hosted pour MAX économies

**Livrables:**
- [ ] Lambda stop/start déployée
- [ ] EventBridge rules créées
- [ ] S3 lifecycle configurée
- [ ] Logs retention ajustée
- [ ] Monitoring des coûts actif

---

## Phase 12: Go-Live et Handover

### Étape 12.1: Checklist de mise en production
**Infrastructure:**
- [ ] Toutes les instances running et healthy
- [ ] ALB healthy targets
- [ ] DNS configurés et résolus
- [ ] SSL certificates valides
- [ ] Security groups validés

**Services:**
- [ ] webMethods Gateway opérationnel
- [ ] Developer Portal accessible
- [ ] Jenkins fonctionnel
- [ ] Vault unsealed et accessible
- [ ] OpenSearch cluster green

**Sécurité:**
- [ ] Tous les secrets dans Vault
- [ ] Pas de credentials hardcodés
- [ ] MFA activée pour admins
- [ ] Backups configurés et testés
- [ ] Monitoring et alerting actifs

**CI/CD:**
- [ ] Pipelines Jenkins testés
- [ ] GitHub webhooks opérationnels
- [ ] GitOps workflow validé
- [ ] Rollback procedure testée

**Documentation:**
- [ ] Architecture documentée
- [ ] Runbooks complets
- [ ] Guides utilisateurs disponibles
- [ ] Procédures d'urgence définies

**Formation:**
- [ ] Équipe formée
- [ ] Access provisionnés
- [ ] Support de niveau 1 prêt

---

### Étape 12.2: Handover
**Livrables finaux:**

1. **Credentials et Accès:**
   - Liste des comptes créés
   - Vault root tokens (sealed envelope)
   - AWS Console access
   - GitHub admin access

2. **Documentation complète:**
   - Architecture diagrams
   - Network diagrams
   - Runbooks opérationnels
   - API documentation

3. **Code source:**
   - Repository GitHub: apim-aws
   - Repository GitHub: apim-apis
   - Tous les scripts et playbooks

4. **Support post Go-Live:**
   - 2 semaines de support
   - Hotline pour incidents
   - Transfer de connaissances

---

## Annexes

### Annexe A: Commandes Utiles

**Terraform:**
```bash
# Plan et Apply
cd terraform/environments/dev
terraform init
terraform plan -out=tfplan
terraform apply tfplan

# Destroy
terraform destroy -auto-approve

# State
terraform state list
terraform state show aws_instance.webmethods
```

**Ansible:**
```bash
# Run playbook
ansible-playbook -i inventory/dev.ini playbooks/webmethods-gateway.yml

# Check mode (dry-run)
ansible-playbook --check playbooks/site.yml

# Specific tags
ansible-playbook playbooks/site.yml --tags webmethods
```

**Vault:**
```bash
# Unseal
vault operator unseal

# Login
vault login

# Read secret
vault kv get secret/webmethods/admin

# Write secret
vault kv put secret/webmethods/admin username=admin password=secret
```

**AWS CLI:**
```bash
# List instances
aws ec2 describe-instances --filters "Name=tag:Environment,Values=dev"

# Stop instances
aws ec2 stop-instances --instance-ids i-1234567890abcdef0

# CloudWatch logs
aws logs tail /aws/ec2/webmethods --follow
```

---

### Annexe B: Dépannage Courant

**Problème: Instance ne démarre pas**
```bash
# Check system log
aws ec2 get-console-output --instance-id i-xxxxx

# Connect via SSM
aws ssm start-session --target i-xxxxx
```

**Problème: Vault sealed**
```bash
# Unseal with 3 keys
vault operator unseal <key1>
vault operator unseal <key2>
vault operator unseal <key3>
```

**Problème: webMethods ne répond pas**
```bash
# Check logs
tail -f /opt/softwareag/IntegrationServer/logs/server.log

# Restart service
systemctl restart webmethods-gateway
```

**Problème: OpenSearch cluster red**
```bash
# Check cluster health
curl -XGET 'https://opensearch-endpoint:9200/_cluster/health?pretty'

# Check indices
curl -XGET 'https://opensearch-endpoint:9200/_cat/indices?v'
```

---

### Annexe C: Architecture Réseau Détaillée

```
┌──────────────────────────────────────────────────────────────────────┐
│                        AWS Cloud (eu-west-1)                         │
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                    VPC (10.0.0.0/16)                           │ │
│  │                                                                │ │
│  │  ┌──────────────────┐    ┌──────────────────┐                │ │
│  │  │  Public Subnet   │    │  Public Subnet   │                │ │
│  │  │   10.0.1.0/24    │    │   10.0.2.0/24    │                │ │
│  │  │   AZ-1a          │    │   AZ-1b          │                │ │
│  │  │                  │    │                  │                │ │
│  │  │  ┌────────────┐  │    │                  │                │ │
│  │  │  │    ALB     │◄─┼────┼─── HTTPS ────────────┐            │ │
│  │  │  │  Routes:   │  │    │                      │            │ │
│  │  │  │  /gateway  │  │    │                      │            │ │
│  │  │  │  /portal   │  │    │    Internet         │            │ │
│  │  │  │  /jenkins  │  │    │    Users            │            │ │
│  │  │  │  /api (CP) │  │    │    CPI/DevOps       │            │ │
│  │  │  └──────┬─────┘  │    │                      │            │ │
│  │  │         │        │    │                      │            │ │
│  │  │  ┌──────┴─────┐  │    │                      │            │ │
│  │  │  │ NAT Gateway│  │    │                      │            │ │
│  │  │  └────────────┘  │    │                      │            │ │
│  │  └──────────────────┘    └──────────────────────┘            │ │
│  │           │                       │                          │ │
│  │  ┌──────────────────┐    ┌──────────────────┐               │ │
│  │  │  Private Subnet  │    │  Private Subnet  │               │ │
│  │  │   10.0.10.0/24   │    │   10.0.11.0/24   │               │ │
│  │  │   AZ-1a          │    │   AZ-1b          │               │ │
│  │  │                  │    │                  │               │ │
│  │  │  ┌────────────┐  │    │  ┌────────────┐  │               │ │
│  │  │  │ webMethods │  │    │  │   Portal   │  │               │ │
│  │  │  │  Gateway   │◄─┼────┼──┤ Developer  │  │               │ │
│  │  │  │  + Teams   │  │    │  │            │  │               │ │
│  │  │  └─────▲──────┘  │    │  └────────────┘  │               │ │
│  │  │        │         │    │                  │               │ │
│  │  │  ┌────────────┐  │    │  ┌────────────┐  │               │ │
│  │  │  │  Jenkins   │  │    │  │   Vault    │  │               │ │
│  │  │  │  CI/CD     │  │    │  │  Secrets   │  │               │ │
│  │  │  └────────────┘  │    │  └────────────┘  │               │ │
│  │  │                  │    │                  │               │ │
│  │  │  ┌──────────────────────────────────┐   │               │ │
│  │  │  │  ECS Fargate (Control Plane API)  │   │               │ │
│  │  │  │  ┌────────────────────────────┐   │   │               │ │
│  │  │  │  │ Control Plane Container    │   │   │               │ │
│  │  │  │  │ - JWT Auth (Cognito)       │───┼───┼───┐           │ │
│  │  │  │  │ - RBAC (tenant + role)     │   │   │   │           │ │
│  │  │  │  │ - webMethods REST client   │───┼───────┤           │ │
│  │  │  │  └────────────────────────────┘   │   │   │           │ │
│  │  │  └──────────────▲───────────────────┘   │   │           │ │
│  │  └─────────────────┼──────┘    └───────────┘   │           │ │
│  │                    │                            │           │ │
│  │  ┌──────────────────┐    ┌──────────────────┐  │           │ │
│  │  │  Database Subnet │    │  Database Subnet │  │           │ │
│  │  │   10.0.20.0/24   │    │   10.0.21.0/24   │  │           │ │
│  │  │   AZ-1a          │    │   AZ-1b          │  │           │ │
│  │  │                  │    │                  │  │           │ │
│  │  │  ┌────────────┐  │    │                  │  │           │ │
│  │  │  │ OpenSearch │◄─┼────┼──────────────────────┘           │ │
│  │  │  │ Analytics  │  │    │                                  │ │
│  │  │  └────────────┘  │    │                                  │ │
│  │  └──────────────────┘    └──────────────────┘               │ │
│  │                                                              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                    │
│  External Services:                                                │
│  ┌────────────────┐  ┌────────────┐  ┌────────┐  ┌──────────┐    │
│  │ AWS Cognito    │  │  DynamoDB  │  │   S3   │  │   KMS    │    │
│  │ - User Pool    │  │  - Tenants │  │ Backup │  │ Encrypt  │    │
│  │ - Groups       │  │  - APIs    │  │ Logs   │  │          │    │
│  │ - JWT Tokens   │  │            │  │        │  │          │    │
│  └────────────────┘  └────────────┘  └────────┘  └──────────┘    │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘

Flux Control Plane:
1. CPI/DevOps obtient JWT depuis Cognito (avec tenant_id + role)
2. Appel API Control Plane: POST /v1/tenants/{tenant-id}/apis
3. Control Plane valide JWT + permissions RBAC
4. Control Plane appelle webMethods REST API
5. API créée et assignée au Team (tenant)
6. Métadonnées stockées dans DynamoDB
7. Logs envoyés à OpenSearch
```

---

### Annexe D: Flux de Déploiement d'API

```
1. Developer commits API definition to GitHub (feature branch)
   ↓
2. GitHub webhook triggers Jenkins pipeline
   ↓
3. Jenkins:
   a. Validates API definition (Swagger/OpenAPI)
   b. Runs security scan
   c. Creates PR automatically
   ↓
4. Code review + approval
   ↓
5. Merge to develop branch
   ↓
6. Jenkins deployment pipeline:
   a. Retrieves secrets from Vault
   b. Deploys API to webMethods Gateway
   c. Applies policies
   d. Runs smoke tests
   e. Publishes to Developer Portal
   ↓
7. API available for developers
   ↓
8. Logs sent to OpenSearch
   ↓
9. Metrics visible in Kibana + CloudWatch
```

---

## Estimation Globale

### Timeline
- **Phase 1-2 (Infrastructure)**: 3-5 jours
- **Phase 3 (Vault)**: 1-2 jours
- **Phase 4 (Services)**: 5-7 jours
- **Phase 5 (IDP)**: 2-3 jours
- **Phase 6 (CI/CD)**: 3-4 jours
- **Phase 7 (Monitoring)**: 2 jours
- **Phase 8 (Sécurité)**: 2-3 jours
- **Phase 9 (Documentation)**: 2-3 jours
- **Phase 10 (Tests)**: 2-3 jours
- **Phase 11-12 (Optimisation & Go-Live)**: 2 jours

**Total: 24-34 jours (1-1.5 mois)**

### Coût Mensuel (DEV/TEST)
- **Sans optimisation**: ~$260/mois
- **Avec auto-stop/start**: ~$130-150/mois
- **Première année**: ~$1,800-2,000 + coûts ponctuels setup

### Ressources Humaines
- **DevOps Engineer**: Lead technique
- **Cloud Architect**: Design et revue
- **API Developer**: Tests et validation
- **Security Engineer**: Hardening (ponctuel)

---

## Prochaines Étapes

1. **Valider le plan** avec l'équipe et stakeholders
2. **Obtenir les licences** webMethods (DEV/TEST)
3. **Provisionner AWS account** dédié
4. **Créer le repository GitHub**
5. **Commencer Phase 1**

---

### Annexe E: Guide d'utilisation Control Plane API

#### E.1: Authentification

**Obtenir un JWT token depuis Cognito:**

```bash
# Variables
CLIENT_ID="your-cognito-client-id"
CLIENT_SECRET="your-cognito-client-secret"
COGNITO_DOMAIN="https://apim-dev.auth.eu-west-1.amazoncognito.com"

# Méthode 1: OAuth2 Client Credentials (pour scripts/CI/CD)
curl -X POST "${COGNITO_DOMAIN}/oauth2/token" \
  --user "${CLIENT_ID}:${CLIENT_SECRET}" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&scope=apim/developer"

# Réponse:
{
  "access_token": "eyJraWQiOiJ...",
  "expires_in": 3600,
  "token_type": "Bearer"
}

# Méthode 2: Username/Password (pour utilisateurs interactifs)
curl -X POST "${COGNITO_DOMAIN}/oauth2/token" \
  --user "${CLIENT_ID}:${CLIENT_SECRET}" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&username=user@example.com&password=Password123!"

# Stocker le token
export JWT_TOKEN="eyJraWQiOiJ..."
```

#### E.2: Gestion des Tenants (CPI uniquement)

**Créer un nouveau tenant:**

```bash
curl -X POST "https://api.apim-dev.votredomaine.com/v1/tenants" \
  -H "Authorization: Bearer ${JWT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "acme",
    "name": "ACME Corporation",
    "description": "ACME Corp API tenant",
    "contact_email": "admin@acme.com"
  }'

# Réponse:
{
  "tenant_id": "acme",
  "status": "created",
  "message": "Tenant created successfully"
}
```

**Lister tous les tenants:**

```bash
# CPI voit tous les tenants
curl -X GET "https://api.apim-dev.votredomaine.com/v1/tenants" \
  -H "Authorization: Bearer ${JWT_TOKEN}"

# Réponse:
[
  {
    "tenant_id": "acme",
    "name": "ACME Corporation",
    "created_at": "2025-01-15T10:00:00Z",
    "status": "active"
  },
  {
    "tenant_id": "globex",
    "name": "Globex Inc",
    "created_at": "2025-01-16T14:30:00Z",
    "status": "active"
  }
]
```

#### E.3: Gestion des APIs

**Créer une nouvelle API:**

```bash
curl -X POST "https://api.apim-dev.votredomaine.com/v1/tenants/acme/apis" \
  -H "Authorization: Bearer ${JWT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "apiDefinition": {
      "type": "swagger",
      "value": "{\"swagger\":\"2.0\",\"info\":{\"title\":\"Customer API\",\"version\":\"1.0.0\"},\"host\":\"api.acme.com\",\"basePath\":\"/v1\",\"schemes\":[\"https\"],\"paths\":{\"/customers\":{\"get\":{\"summary\":\"List customers\",\"responses\":{\"200\":{\"description\":\"Success\"}}}}}}"
    },
    "apiName": "Customer API",
    "apiVersion": "1.0.0",
    "apiDescription": "API to manage customers",
    "isActive": true,
    "tags": ["customer", "crm"]
  }'

# Réponse:
{
  "apiResponse": {
    "api": {
      "id": "abc123",
      "apiName": "Customer API",
      "apiVersion": "1.0.0",
      "isActive": true,
      "createdDate": "2025-01-20T09:15:00Z",
      "teamName": "tenant-acme"
    }
  }
}
```

**Lister les APIs du tenant:**

```bash
curl -X GET "https://api.apim-dev.votredomaine.com/v1/tenants/acme/apis" \
  -H "Authorization: Bearer ${JWT_TOKEN}"

# Réponse:
{
  "api": [
    {
      "id": "abc123",
      "apiName": "Customer API",
      "apiVersion": "1.0.0",
      "isActive": true,
      "type": "REST",
      "teamName": "tenant-acme"
    }
  ]
}
```

**Obtenir les détails d'une API:**

```bash
curl -X GET "https://api.apim-dev.votredomaine.com/v1/tenants/acme/apis/abc123" \
  -H "Authorization: Bearer ${JWT_TOKEN}"
```

**Supprimer une API:**

```bash
curl -X DELETE "https://api.apim-dev.votredomaine.com/v1/tenants/acme/apis/abc123" \
  -H "Authorization: Bearer ${JWT_TOKEN}"

# Réponse:
{
  "message": "API deleted successfully"
}
```

#### E.4: Gestion des Applications (Consommateurs d'APIs)

**Créer une application:**

```bash
curl -X POST "https://api.apim-dev.votredomaine.com/v1/tenants/acme/applications" \
  -H "Authorization: Bearer ${JWT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Mobile App",
    "description": "ACME mobile application",
    "contactEmails": ["mobile-team@acme.com"],
    "identifiers": [
      {
        "key": "apiKey"
      }
    ]
  }'

# Réponse:
{
  "applicationResponse": {
    "application": {
      "id": "app456",
      "name": "Mobile App",
      "description": "ACME mobile application",
      "teamName": "tenant-acme",
      "apiAccessKey": "7f3d8e9a-1234-5678-9abc-def012345678",
      "createdDate": "2025-01-20T10:00:00Z"
    }
  }
}
```

**Lister les applications:**

```bash
curl -X GET "https://api.apim-dev.votredomaine.com/v1/tenants/acme/applications" \
  -H "Authorization: Bearer ${JWT_TOKEN}"
```

**Associer une API à une application (subscription):**

```bash
curl -X POST "https://api.apim-dev.votredomaine.com/v1/tenants/acme/applications/app456/apis" \
  -H "Authorization: Bearer ${JWT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "apiIds": ["abc123"]
  }'
```

#### E.5: Gestion des Policies

**Appliquer des policies à une API:**

```bash
curl -X PUT "https://api.apim-dev.votredomaine.com/v1/tenants/acme/apis/abc123/policies" \
  -H "Authorization: Bearer ${JWT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "policies": [
      {
        "policyName": "Traffic Monitoring",
        "policyType": "trafficMonitoring",
        "policyScope": "GLOBAL",
        "isActive": true
      },
      {
        "policyName": "Rate Limiting",
        "policyType": "throttling",
        "policyScope": "GLOBAL",
        "isActive": true,
        "parameters": {
          "maximumRequests": "100",
          "interval": "60",
          "unit": "seconds"
        }
      },
      {
        "policyName": "API Key Authentication",
        "policyType": "identifyAndAuthorize",
        "policyScope": "GLOBAL",
        "isActive": true,
        "parameters": {
          "identificationKey": "apiKey",
          "authenticationScheme": "apiKey"
        }
      }
    ]
  }'

# Réponse:
{
  "policy": [
    {
      "id": "policy123",
      "policyName": "Traffic Monitoring",
      "isActive": true
    },
    {
      "id": "policy124",
      "policyName": "Rate Limiting",
      "isActive": true
    },
    {
      "id": "policy125",
      "policyName": "API Key Authentication",
      "isActive": true
    }
  ]
}
```

**Policies disponibles courantes:**
- `trafficMonitoring`: Monitoring du trafic
- `throttling`: Rate limiting
- `identifyAndAuthorize`: Authentification (API Key, OAuth, JWT)
- `requestTransformation`: Transformation requête
- `responseTransformation`: Transformation réponse
- `logInvocation`: Logging détaillé
- `validateAPI`: Validation schema
- `cors`: Configuration CORS

#### E.6: Exemples d'Intégration CI/CD

**Script Bash pour déploiement automatique:**

```bash
#!/bin/bash
# deploy-api.sh

set -e

API_SPEC_FILE=$1
TENANT_ID=$2

# Get JWT token from Cognito
JWT_TOKEN=$(curl -s -X POST "${COGNITO_DOMAIN}/oauth2/token" \
  --user "${CLIENT_ID}:${CLIENT_SECRET}" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&scope=apim/devops" | jq -r '.access_token')

# Read API spec
API_SPEC=$(cat ${API_SPEC_FILE} | jq -c .)

# Create API
RESPONSE=$(curl -s -X POST "https://api.apim-dev.votredomaine.com/v1/tenants/${TENANT_ID}/apis" \
  -H "Authorization: Bearer ${JWT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{
    \"apiDefinition\": {
      \"type\": \"swagger\",
      \"value\": ${API_SPEC}
    },
    \"apiName\": \"$(jq -r '.info.title' ${API_SPEC_FILE})\",
    \"apiVersion\": \"$(jq -r '.info.version' ${API_SPEC_FILE})\",
    \"isActive\": true
  }")

API_ID=$(echo $RESPONSE | jq -r '.apiResponse.api.id')
echo "API created with ID: ${API_ID}"

# Apply default policies
curl -X PUT "https://api.apim-dev.votredomaine.com/v1/tenants/${TENANT_ID}/apis/${API_ID}/policies" \
  -H "Authorization: Bearer ${JWT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d @policies/default-policies.json

echo "Policies applied successfully"
```

**Pipeline Jenkins Jenkinsfile:**

```groovy
pipeline {
    agent any

    environment {
        CONTROL_PLANE_API = 'https://api.apim-dev.votredomaine.com'
        TENANT_ID = 'acme'
        COGNITO_DOMAIN = credentials('cognito-domain')
        CLIENT_ID = credentials('cognito-client-id')
        CLIENT_SECRET = credentials('cognito-client-secret')
    }

    stages {
        stage('Get JWT Token') {
            steps {
                script {
                    def response = sh(
                        script: """
                            curl -s -X POST "\${COGNITO_DOMAIN}/oauth2/token" \
                              --user "\${CLIENT_ID}:\${CLIENT_SECRET}" \
                              -H "Content-Type: application/x-www-form-urlencoded" \
                              -d "grant_type=client_credentials&scope=apim/devops"
                        """,
                        returnStdout: true
                    ).trim()

                    def json = readJSON text: response
                    env.JWT_TOKEN = json.access_token
                }
            }
        }

        stage('Validate API Spec') {
            steps {
                sh '''
                    swagger-cli validate api-spec.yaml
                '''
            }
        }

        stage('Deploy API') {
            steps {
                script {
                    def apiSpec = readFile('api-spec.yaml')
                    def apiSpecJson = sh(
                        script: "yq eval -o=json api-spec.yaml",
                        returnStdout: true
                    ).trim()

                    def payload = """
                    {
                      "apiDefinition": {
                        "type": "swagger",
                        "value": ${apiSpecJson}
                      },
                      "apiName": "Customer API",
                      "apiVersion": "1.0.0",
                      "isActive": true
                    }
                    """

                    def response = sh(
                        script: """
                            curl -s -X POST "\${CONTROL_PLANE_API}/v1/tenants/\${TENANT_ID}/apis" \
                              -H "Authorization: Bearer \${JWT_TOKEN}" \
                              -H "Content-Type: application/json" \
                              -d '${payload}'
                        """,
                        returnStdout: true
                    ).trim()

                    def json = readJSON text: response
                    env.API_ID = json.apiResponse.api.id
                    echo "API deployed with ID: ${env.API_ID}"
                }
            }
        }

        stage('Apply Policies') {
            steps {
                sh '''
                    curl -X PUT "${CONTROL_PLANE_API}/v1/tenants/${TENANT_ID}/apis/${API_ID}/policies" \
                      -H "Authorization: Bearer ${JWT_TOKEN}" \
                      -H "Content-Type: application/json" \
                      -d @policies.json
                '''
            }
        }

        stage('Smoke Test') {
            steps {
                sh '''
                    # Wait for API to be active
                    sleep 10

                    # Test API endpoint
                    curl -f "https://gateway.apim-dev.votredomaine.com/customers" \
                      -H "X-API-Key: test-key" || exit 1
                '''
            }
        }
    }

    post {
        success {
            echo "API deployed successfully!"
        }
        failure {
            echo "API deployment failed!"
        }
    }
}
```

**GitHub Actions Workflow:**

```yaml
# .github/workflows/deploy-api.yml
name: Deploy API to APIM

on:
  push:
    branches:
      - main
    paths:
      - 'apis/**'

jobs:
  deploy:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Get JWT Token
        id: auth
        run: |
          RESPONSE=$(curl -s -X POST "${{ secrets.COGNITO_DOMAIN }}/oauth2/token" \
            --user "${{ secrets.CLIENT_ID }}:${{ secrets.CLIENT_SECRET }}" \
            -H "Content-Type: application/x-www-form-urlencoded" \
            -d "grant_type=client_credentials&scope=apim/devops")

          JWT_TOKEN=$(echo $RESPONSE | jq -r '.access_token')
          echo "::add-mask::$JWT_TOKEN"
          echo "JWT_TOKEN=$JWT_TOKEN" >> $GITHUB_ENV

      - name: Validate API Spec
        run: |
          npx swagger-cli validate apis/customer-api/swagger.yaml

      - name: Deploy API
        run: |
          API_SPEC=$(cat apis/customer-api/swagger.yaml | yq eval -o=json)

          RESPONSE=$(curl -s -X POST "${{ secrets.CONTROL_PLANE_API }}/v1/tenants/${{ secrets.TENANT_ID }}/apis" \
            -H "Authorization: Bearer ${JWT_TOKEN}" \
            -H "Content-Type: application/json" \
            -d "{
              \"apiDefinition\": {
                \"type\": \"swagger\",
                \"value\": $(echo $API_SPEC | jq -c .)
              },
              \"apiName\": \"Customer API\",
              \"apiVersion\": \"1.0.0\",
              \"isActive\": true
            }")

          API_ID=$(echo $RESPONSE | jq -r '.apiResponse.api.id')
          echo "API_ID=$API_ID" >> $GITHUB_ENV
          echo "Deployed API ID: $API_ID"

      - name: Apply Policies
        run: |
          curl -X PUT "${{ secrets.CONTROL_PLANE_API }}/v1/tenants/${{ secrets.TENANT_ID }}/apis/${API_ID}/policies" \
            -H "Authorization: Bearer ${JWT_TOKEN}" \
            -H "Content-Type: application/json" \
            -d @apis/customer-api/policies.json
```

#### E.7: SDK Python pour Control Plane

**Exemple de SDK Python:**

```python
# apim_sdk.py
import requests
from typing import Dict, List, Optional
import json

class APIMClient:
    def __init__(self, base_url: str, cognito_domain: str, client_id: str, client_secret: str):
        self.base_url = base_url
        self.cognito_domain = cognito_domain
        self.client_id = client_id
        self.client_secret = client_secret
        self._token = None

    def authenticate(self, scope: str = "apim/developer"):
        """Get JWT token from Cognito"""
        response = requests.post(
            f"{self.cognito_domain}/oauth2/token",
            auth=(self.client_id, self.client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials", "scope": scope}
        )
        response.raise_for_status()
        self._token = response.json()["access_token"]

    @property
    def headers(self):
        if not self._token:
            self.authenticate()
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json"
        }

    def create_api(self, tenant_id: str, api_spec: Dict, api_name: str, api_version: str) -> Dict:
        """Create a new API"""
        payload = {
            "apiDefinition": {
                "type": "swagger",
                "value": json.dumps(api_spec)
            },
            "apiName": api_name,
            "apiVersion": api_version,
            "isActive": True
        }

        response = requests.post(
            f"{self.base_url}/v1/tenants/{tenant_id}/apis",
            headers=self.headers,
            json=payload
        )
        response.raise_for_status()
        return response.json()

    def list_apis(self, tenant_id: str) -> List[Dict]:
        """List all APIs in tenant"""
        response = requests.get(
            f"{self.base_url}/v1/tenants/{tenant_id}/apis",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json().get("api", [])

    def delete_api(self, tenant_id: str, api_id: str):
        """Delete an API"""
        response = requests.delete(
            f"{self.base_url}/v1/tenants/{tenant_id}/apis/{api_id}",
            headers=self.headers
        )
        response.raise_for_status()

    def apply_policies(self, tenant_id: str, api_id: str, policies: List[Dict]):
        """Apply policies to an API"""
        response = requests.put(
            f"{self.base_url}/v1/tenants/{tenant_id}/apis/{api_id}/policies",
            headers=self.headers,
            json={"policies": policies}
        )
        response.raise_for_status()
        return response.json()

# Usage
if __name__ == "__main__":
    client = APIMClient(
        base_url="https://api.apim-dev.votredomaine.com",
        cognito_domain="https://apim-dev.auth.eu-west-1.amazoncognito.com",
        client_id="your-client-id",
        client_secret="your-client-secret"
    )

    # Create API
    with open("swagger.yaml", "r") as f:
        import yaml
        api_spec = yaml.safe_load(f)

    result = client.create_api(
        tenant_id="acme",
        api_spec=api_spec,
        api_name="Customer API",
        api_version="1.0.0"
    )

    api_id = result["apiResponse"]["api"]["id"]
    print(f"API created: {api_id}")

    # Apply policies
    policies = [
        {
            "policyName": "Rate Limiting",
            "policyType": "throttling",
            "isActive": True,
            "parameters": {
                "maximumRequests": "100",
                "interval": "60"
            }
        }
    ]

    client.apply_policies("acme", api_id, policies)
    print("Policies applied")
```

#### E.8: Permissions et RBAC

**Matrice de permissions par rôle:**

| Endpoint | CPI | DevOps | Developer | Tenant Admin |
|----------|-----|--------|-----------|--------------|
| POST /v1/tenants | ✅ | ❌ | ❌ | ❌ |
| GET /v1/tenants | ✅ (all) | ✅ (own) | ✅ (own) | ✅ (own) |
| POST /v1/tenants/{id}/apis | ✅ | ✅ | ✅ | ✅ |
| GET /v1/tenants/{id}/apis | ✅ | ✅ | ✅ | ✅ |
| DELETE /v1/tenants/{id}/apis/{api-id} | ✅ | ✅ | ✅ | ✅ |
| PUT /v1/tenants/{id}/apis/{api-id}/policies | ✅ | ✅ | ❌ | ✅ |
| POST /v1/tenants/{id}/applications | ✅ | ✅ | ✅ | ✅ |
| GET /v1/tenants/{id}/applications | ✅ | ✅ | ✅ | ✅ |

**Groupes Cognito et mappings:**

- `apim-cpi`: Accès complet multi-tenant
- `apim-devops`: DevOps operations (tous tenants)
- `apim-admins`: Admin plateforme
- `tenant-{id}-admins`: Admin du tenant spécifique
- `tenant-{id}-developers`: Développeurs du tenant

---

**Document créé le**: 2025-12-17
**Version**: 1.1
**Auteur**: Claude Code
**Statut**: Draft pour revue - Control Plane API ajoutée
