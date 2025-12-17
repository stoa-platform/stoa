# 🚀 APIM Platform - API Management as Code sur AWS

Plateforme complète d'API Management pour DEV/TEST avec webMethods, Control Plane API, et infrastructure as code.

## 📋 Vue d'ensemble

Cette plateforme fournit:
- **webMethods API Gateway** avec support multi-tenant
- **Developer Portal** pour les consommateurs d'APIs
- **Control Plane API** pour gestion programmatique via JWT
- **Jenkins** pour CI/CD
- **HashiCorp Vault** pour gestion des secrets
- **OpenSearch** pour analytics et monitoring
- **Infrastructure as Code** avec Terraform
- **Configuration Management** avec Ansible

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    AWS Cloud (eu-west-1)                │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │                 VPC (10.0.0.0/16)                  │ │
│  │                                                    │ │
│  │  ALB → webMethods Gateway (EC2)                   │ │
│  │     → Developer Portal (EC2)                       │ │
│  │     → Jenkins (EC2)                                │ │
│  │     → Control Plane API (ECS Fargate)             │ │
│  │                                                    │ │
│  │  Private: Vault (EC2)                             │ │
│  │          OpenSearch (Managed)                     │ │
│  │                                                    │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│  Services: Cognito, DynamoDB, S3, KMS                   │
└─────────────────────────────────────────────────────────┘
```

## 💰 Coûts estimés (DEV/TEST)

| Service | Coût mensuel |
|---------|--------------|
| EC2 Instances (avec stop/start) | ~$60 |
| ECS Fargate Spot | ~$15 |
| OpenSearch t3.small | ~$30 |
| ALB | ~$20 |
| NAT Gateway | ~$35 |
| DynamoDB, S3, autres | ~$15 |
| **Total** | **~$175/mois** |

Avec arrêt automatique 19h-8h + weekends: **~$130-150/mois**

## 🚀 Démarrage rapide

### Prérequis

- AWS CLI configuré
- Terraform >= 1.5.0
- Ansible >= 2.15
- Docker
- Python 3.11+

### 1. Bootstrap de l'infrastructure

```bash
# Créer les ressources de base (S3, DynamoDB, ECR)
./scripts/bootstrap.sh dev eu-west-1
```

### 2. Déployer l'infrastructure Terraform

```bash
cd terraform/environments/dev
terraform init
terraform plan
terraform apply
```

### 3. Configurer les services avec Ansible

```bash
cd ansible
# Mettre à jour inventory/dev.ini avec les IPs des instances

ansible-playbook -i inventory/dev.ini playbooks/site.yml
```

### 4. Déployer le Control Plane API

```bash
cd control-plane-api
./deploy.sh dev eu-west-1
```

## 📖 Documentation

- [Plan détaillé](PLAN_DETAILLE.md) - Plan d'implémentation complet
- [Guide de déploiement](docs/DEPLOYMENT.md) - Instructions de déploiement
- [Guide utilisateur Control Plane](docs/CONTROL_PLANE.md) - Utilisation de l'API
- [Runbook opérationnel](docs/RUNBOOK.md) - Procédures d'exploitation
- [Architecture technique](docs/ARCHITECTURE.md) - Détails d'architecture

## 🔐 Sécurité

- Authentification via AWS Cognito (OIDC/JWT)
- RBAC multi-tenant avec groupes Cognito
- Secrets gérés par HashiCorp Vault
- Chiffrement en transit (TLS) et au repos (KMS)
- Security Groups restrictifs
- Pas d'accès public direct aux instances (SSM Session Manager)

## 🛠️ Scripts utilitaires

```bash
# Déploiement complet
./scripts/deploy.sh dev all

# Déployer uniquement Terraform
./scripts/deploy.sh dev terraform

# Arrêter les instances (économie)
./scripts/stop-instances.sh dev

# Démarrer les instances
./scripts/start-instances.sh dev
```

## 📊 Monitoring

- **CloudWatch**: Métriques infrastructure et applications
- **OpenSearch/Kibana**: Logs et analytics des APIs
- **Dashboards**: Traffic, erreurs, performance

Accès: https://kibana.apim-dev.votredomaine.com

## 🔄 CI/CD

### Pipelines Jenkins

- **deploy-control-plane**: Déploiement Control Plane API
- **deploy-api**: Déploiement d'une API via Control Plane
- **infrastructure-update**: Mise à jour Terraform

### GitHub Actions

- **terraform-plan**: Plan sur PR
- **deploy-control-plane**: Déploiement automatique sur push main

## 🌐 Endpoints

| Service | URL | Port |
|---------|-----|------|
| Control Plane API | https://api.apim-dev.votredomaine.com | 443 |
| webMethods Gateway | https://gateway.apim-dev.votredomaine.com | 443 |
| Developer Portal | https://portal.apim-dev.votredomaine.com | 443 |
| Jenkins | https://jenkins.apim-dev.votredomaine.com | 443 |
| Kibana | https://kibana.apim-dev.votredomaine.com | 443 |

## 🔧 Control Plane API

### Authentification

```bash
# Obtenir un token JWT depuis Cognito
TOKEN=$(curl -X POST "https://apim-dev.auth.eu-west-1.amazoncognito.com/oauth2/token" \
  --user "${CLIENT_ID}:${CLIENT_SECRET}" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&scope=apim/developer" | jq -r '.access_token')
```

### Créer un tenant (CPI seulement)

```bash
curl -X POST "https://api.apim-dev.votredomaine.com/v1/tenants" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": "acme", "name": "ACME Corp"}'
```

### Créer une API

```bash
curl -X POST "https://api.apim-dev.votredomaine.com/v1/tenants/acme/apis" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d @api-definition.json
```

Voir [PLAN_DETAILLE.md - Annexe E](PLAN_DETAILLE.md#annexe-e-guide-dutilisation-control-plane-api) pour plus d'exemples.

## 🤝 Contribution

1. Créer une feature branch depuis `develop`
2. Faire les modifications
3. Créer une PR vers `develop`
4. Après review et tests, merge vers `main`

## 📝 Licence

Propriétaire - Tous droits réservés

## 👥 Support

- Email: platform-team@votreentreprise.com
- Slack: #apim-platform
- Issues: GitHub Issues

---

**Version**: 1.0.0
**Dernière mise à jour**: 2025-12-17
