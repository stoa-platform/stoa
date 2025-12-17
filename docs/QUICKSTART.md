# 🚀 Guide de démarrage rapide - APIM Platform

Ce guide vous permet de démarrer la plateforme APIM en moins de 30 minutes.

## Prérequis

- [ ] Compte AWS avec accès administrateur
- [ ] AWS CLI configuré (`aws configure`)
- [ ] Terraform >= 1.5.0 installé
- [ ] Docker installé
- [ ] Git installé

## Étape 1: Cloner le repository

```bash
git clone <repository-url>
cd apim-aws
```

## Étape 2: Bootstrap (5 min)

Créer les ressources AWS de base:

```bash
./scripts/bootstrap.sh dev eu-west-1
```

Ceci crée:
- ✅ Bucket S3 pour Terraform state
- ✅ Table DynamoDB pour Terraform locks
- ✅ Repository ECR pour Control Plane API

## Étape 3: Déployer l'infrastructure (15 min)

```bash
cd terraform/environments/dev

# Initialiser Terraform
terraform init

# Vérifier le plan
terraform plan

# Déployer
terraform apply -auto-approve
```

Ceci déploie:
- ✅ VPC avec subnets publics/privés
- ✅ Security Groups
- ✅ IAM Roles
- ✅ S3 Buckets pour artifacts/backups
- ✅ KMS Key pour Vault
- ✅ Cognito User Pool

## Étape 4: Récupérer les outputs Terraform

```bash
# Noter ces valeurs pour la suite
terraform output vpc_id
terraform output private_subnet_ids
terraform output kms_key_id

# Ou exporter dans un fichier
terraform output -json > ../../../outputs.json
```

## Étape 5: Créer les instances EC2 (Optionnel si manuel)

Si vous créez les instances manuellement via console:

1. Créer 4 instances EC2:
   - webMethods Gateway: t3.large, subnet privé, SG webmethods
   - Developer Portal: t3.medium, subnet privé, SG portal
   - Jenkins: t3.medium, subnet privé, SG jenkins
   - Vault: t3.small, subnet privé, SG vault

2. Attacher les instance profiles IAM correspondants

3. Noter les IPs privées des instances

## Étape 6: Configurer l'inventaire Ansible

```bash
cd ../../../ansible

# Éditer inventory/dev.ini
vim inventory/dev.ini
```

Remplacer les IPs:
```ini
[webmethods]
webmethods-gateway ansible_host=10.0.10.XX

[portal]
portal ansible_host=10.0.11.XX

[jenkins]
jenkins ansible_host=10.0.10.XX

[vault]
vault ansible_host=10.0.11.XX
```

## Étape 7: Exécuter Ansible (10 min)

```bash
# Tester la connectivité
ansible all -i inventory/dev.ini -m ping

# Déployer tous les services
ansible-playbook -i inventory/dev.ini playbooks/site.yml
```

## Étape 8: Déployer le Control Plane API (5 min)

```bash
cd ../control-plane-api

# Construire et déployer
./deploy.sh dev eu-west-1
```

## Étape 9: Vérification

### Vérifier que tout fonctionne:

```bash
# Health check Control Plane
curl https://api.apim-dev.votredomaine.com/health

# Vérifier webMethods (via ALB)
curl -k https://gateway.apim-dev.votredomaine.com

# Vérifier Jenkins
curl -k https://jenkins.apim-dev.votredomaine.com

# Vérifier le portail
curl -k https://portal.apim-dev.votredomaine.com
```

## Étape 10: Configuration initiale Cognito

### Créer les groupes:

```bash
aws cognito-idp create-group \
  --user-pool-id <USER_POOL_ID> \
  --group-name apim-cpi \
  --description "CPI Team"

aws cognito-idp create-group \
  --user-pool-id <USER_POOL_ID> \
  --group-name apim-devops \
  --description "DevOps Team"

aws cognito-idp create-group \
  --user-pool-id <USER_POOL_ID> \
  --group-name tenant-acme-developers \
  --description "ACME Developers"
```

### Créer un utilisateur de test:

```bash
aws cognito-idp admin-create-user \
  --user-pool-id <USER_POOL_ID> \
  --username admin@example.com \
  --user-attributes Name=email,Value=admin@example.com \
  --temporary-password TempPass123!

aws cognito-idp admin-add-user-to-group \
  --user-pool-id <USER_POOL_ID> \
  --username admin@example.com \
  --group-name apim-cpi
```

## Étape 11: Tester le Control Plane API

```bash
# Obtenir un token
TOKEN=$(curl -X POST "https://apim-dev.auth.eu-west-1.amazoncognito.com/oauth2/token" \
  --user "${CLIENT_ID}:${CLIENT_SECRET}" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&scope=apim/developer" | jq -r '.access_token')

# Créer un tenant
curl -X POST "https://api.apim-dev.votredomaine.com/v1/tenants" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": "acme", "name": "ACME Corporation"}'

# Lister les tenants
curl -X GET "https://api.apim-dev.votredomaine.com/v1/tenants" \
  -H "Authorization: Bearer ${TOKEN}"
```

## ✅ C'est terminé !

Votre plateforme APIM est maintenant opérationnelle !

## Prochaines étapes

1. **Configurer les DNS**: Pointer vos domaines vers l'ALB
2. **Obtenir les certificats SSL**: Utiliser AWS Certificate Manager
3. **Créer des APIs de test**: Utiliser le Control Plane API
4. **Configurer Jenkins**: Importer les pipelines depuis GitHub
5. **Setup monitoring**: Configurer les dashboards Kibana

## Dépannage

### Les instances ne sont pas accessibles

```bash
# Vérifier les security groups
aws ec2 describe-security-groups --filters "Name=tag:Project,Values=APIM"

# Vérifier les routes
aws ec2 describe-route-tables --filters "Name=tag:Project,Values=APIM"
```

### Control Plane API ne démarre pas

```bash
# Vérifier les logs ECS
aws logs tail /ecs/control-plane-api --follow

# Vérifier le service ECS
aws ecs describe-services --cluster apim-dev --services control-plane-api
```

### Ansible échoue

```bash
# Vérifier la connectivité SSM
aws ssm start-session --target i-xxxxx

# Vérifier les logs CloudWatch
aws logs tail /var/log/messages --follow
```

## Support

- Documentation complète: [PLAN_DETAILLE.md](../PLAN_DETAILLE.md)
- Architecture: [ARCHITECTURE.md](ARCHITECTURE.md)
- Runbook: [RUNBOOK.md](RUNBOOK.md)

---

Temps total estimé: **30-45 minutes** ⏱️
