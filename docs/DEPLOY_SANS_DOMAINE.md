# 🚀 Déploiement APIM sans domaine personnalisé

Guide pour déployer la plateforme APIM en utilisant les DNS AWS automatiques (gratuit).

## ✅ Avantages

- **Gratuit** : Pas besoin d'acheter un domaine
- **Immédiat** : Pas de configuration DNS
- **Parfait pour DEV/TEST** : Idéal pour tester la plateforme

## 📋 Prérequis

1. **Compte AWS** avec credentials configurés
2. **Terraform** >= 1.5.0
3. **AWS CLI** configuré

```bash
# Vérifier vos credentials
aws sts get-caller-identity

# Devrait retourner votre Account ID et User
```

## 🚀 Déploiement en 3 étapes (20 minutes)

### Étape 1: Bootstrap AWS (5 min)

```bash
cd /Users/torpedo/apim-aws

# Créer S3 bucket, DynamoDB table, ECR repository
./scripts/bootstrap.sh dev eu-west-1
```

**Ce qui est créé** :
- ✅ S3 bucket: `apim-terraform-state-dev`
- ✅ DynamoDB table: `apim-terraform-locks`
- ✅ ECR repository: `apim-control-plane`

### Étape 2: Déployer l'infrastructure (15 min)

```bash
cd terraform/environments/dev

# Initialiser Terraform
terraform init

# Vérifier le plan (optionnel mais recommandé)
terraform plan

# Déployer !
terraform apply
```

Terraform va créer **automatiquement** :
- ✅ VPC avec subnets (publics/privés)
- ✅ NAT Gateway
- ✅ Internet Gateway
- ✅ Security Groups
- ✅ IAM Roles et Policies
- ✅ S3 Buckets (artifacts, backups, vault)
- ✅ KMS Key pour Vault

**Durée** : ~10-15 minutes

### Étape 3: Récupérer le DNS de l'ALB

```bash
# Une fois le déploiement terminé
terraform output

# Vous verrez le VPC ID, subnets, etc.
# Note: L'ALB sera créé plus tard avec les modules manquants
```

## 🔧 Accéder aux services

### Sans ALB (temporaire - SSM Session Manager)

En attendant de créer les modules EC2 et ALB, vous pouvez accéder aux instances via SSM :

```bash
# Lister les instances
aws ec2 describe-instances \
  --filters "Name=tag:Project,Values=APIM" \
  --query 'Reservations[].Instances[].{ID:InstanceId,Name:Tags[?Key==`Name`].Value|[0],IP:PrivateIpAddress}' \
  --output table

# Se connecter à une instance
aws ssm start-session --target i-XXXXXXXXX
```

### Avec ALB (après création du module)

Une fois l'ALB créé, vous accéderez via :

```
http://apim-alb-dev-123456789.eu-west-1.elb.amazonaws.com
```

Ports par service :
- **Control Plane API**: `:8000`
- **webMethods**: `:9072`
- **Jenkins**: `:8080`
- **Developer Portal**: `:18101`

## 📊 Vérifier les coûts

```bash
# Estimer les coûts actuels
aws ce get-cost-and-usage \
  --time-period Start=2025-12-01,End=2025-12-31 \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --filter file://cost-filter.json
```

**Coût attendu** : ~$130-150/mois avec auto-stop

## 🛑 Économiser de l'argent

### Arrêter les instances en dehors des heures de travail

```bash
# Arrêter toutes les instances DEV
./scripts/stop-instances.sh dev

# Économie: ~60% sur les coûts EC2
```

### Redémarrer le matin

```bash
# Démarrer toutes les instances DEV
./scripts/start-instances.sh dev
```

### Automatiser avec EventBridge (optionnel)

Créer des règles pour arrêter/démarrer automatiquement :

```bash
# Arrêt à 19h en semaine
aws events put-rule \
  --name apim-stop-dev-weeknight \
  --schedule-expression "cron(0 19 ? * MON-FRI *)" \
  --state ENABLED

# Démarrage à 8h en semaine
aws events put-rule \
  --name apim-start-dev-morning \
  --schedule-expression "cron(0 8 ? * MON-FRI *)" \
  --state ENABLED
```

## 🔐 Certificat SSL (optionnel)

Si vous voulez du HTTPS sans domaine :

### Option 1: Certificat auto-signé (test uniquement)

```bash
# Générer un certificat auto-signé
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /tmp/selfsigned.key \
  -out /tmp/selfsigned.crt \
  -subj "/CN=apim-dev.local"

# Uploader dans ACM
aws acm import-certificate \
  --certificate fileb:///tmp/selfsigned.crt \
  --private-key fileb:///tmp/selfsigned.key \
  --region eu-west-1
```

### Option 2: Let's Encrypt avec DNS challenge (avancé)

Nécessite un domaine, voir documentation séparée.

## 🎯 Prochaines étapes

1. **Créer les modules manquants** :
   - [ ] Module EC2 (instances webMethods, Jenkins, etc.)
   - [ ] Module ALB (Application Load Balancer)
   - [ ] Module Cognito (authentification)
   - [ ] Module Control Plane (ECS Fargate)

2. **Configurer Ansible** :
   ```bash
   cd ansible
   # Éditer inventory/dev.ini avec les IPs
   ansible-playbook -i inventory/dev.ini playbooks/site.yml
   ```

3. **Déployer le Control Plane API** :
   ```bash
   cd control-plane-api
   ./deploy.sh dev
   ```

## 🆘 Troubleshooting

### Erreur: Bucket S3 déjà existant

```bash
# Le bucket existe déjà, c'est normal après bootstrap
# Continuez avec terraform init
```

### Erreur: Credentials AWS

```bash
# Reconfigurer
aws configure

# Ou utiliser des variables d'environnement
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
export AWS_DEFAULT_REGION="eu-west-1"
```

### Voir les logs Terraform

```bash
export TF_LOG=DEBUG
terraform apply
```

## 💡 Conseils

1. **Commencez petit** : Déployez juste le VPC et IAM d'abord
2. **Vérifiez les coûts** : Utilisez AWS Cost Explorer régulièrement
3. **Auto-stop** : Configurez l'arrêt automatique dès le début
4. **Backups** : Les états Terraform sont dans S3 avec versioning

## 📞 Support

- Documentation complète: [PLAN_DETAILLE.md](../PLAN_DETAILLE.md)
- Guide général: [QUICKSTART.md](QUICKSTART.md)
- Structure projet: [STRUCTURE.md](../STRUCTURE.md)

---

**Prêt à déployer ?** Lancez `./scripts/bootstrap.sh dev` ! 🚀
