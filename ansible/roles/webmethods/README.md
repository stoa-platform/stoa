# webMethods API Gateway Ansible Role

Ce rôle installe et configure webMethods API Gateway sur une instance EC2.

## Prérequis

1. **Installer webMethods en amont** :
   - Téléchargez l'installer webMethods depuis le site Software AG
   - Uploadez-le dans le bucket S3 `apim-artifacts-dev/installers/webmethods/`
   - Nommez-le selon la variable `webmethods_installer` (défaut: `webmethods-apigateway-10.15.zip`)

2. **License webMethods** :
   - Stockez la license dans HashiCorp Vault : `secret/webmethods/license`
   - Ou placez-la manuellement dans `/opt/softwareag/license.xml`

3. **Instance EC2** :
   - Type recommandé : t3.large minimum (2 vCPU, 8 GB RAM)
   - Rôle IAM avec accès S3, Vault, CloudWatch

## Variables

### Obligatoires
Aucune - toutes les variables ont des valeurs par défaut

### Optionnelles

```yaml
# Installation
webmethods_installer: "webmethods-apigateway-10.15.zip"
artifacts_bucket: "apim-artifacts-dev"
backup_bucket: "apim-backups-dev"

# Mémoire Java
webmethods_java_min_mem: "512m"
webmethods_java_max_mem: "2048m"

# Ports
webmethods_admin_port: 9072
webmethods_runtime_port: 5555

# OpenSearch externe
use_external_opensearch: true
opensearch_endpoint: "https://opensearch.apim-dev.local:9200"

# Vault
vault_addr: "https://vault.apim-dev.local:8200"

# Mot de passe admin (utilisez Vault en production!)
webmethods_admin_password: "SuperSecretPassword123!"

# Teams multi-tenant
api_gateway_teams:
  - name: "tenant-cpi"
    description: "Équipe CPI"
  - name: "tenant-devops"
    description: "Équipe DevOps"
```

## Utilisation

### 1. Inventaire Ansible

```ini
[webmethods]
webmethods-01 ansible_host=10.0.1.10

[webmethods:vars]
opensearch_endpoint=https://opensearch.apim-dev.internal:9200
vault_addr=https://vault.apim-dev.internal:8200
```

### 2. Playbook

```yaml
- name: Setup webMethods API Gateway
  hosts: webmethods
  become: true
  roles:
    - webmethods
```

### 3. Exécution

```bash
ansible-playbook -i inventory/dev.ini playbooks/site.yml
```

## Post-installation

### Accès à l'interface d'administration

```bash
# Via ALB (après configuration)
https://apim-alb-dev-XXXXX.eu-west-1.elb.amazonaws.com:9072

# Credentials par défaut
User: Administrator
Password: (celui défini dans webmethods_admin_password)
```

### Health Check

```bash
curl http://localhost:9072/rest/apigateway/health
```

### Vérifier les logs

```bash
tail -f /opt/softwareag/IntegrationServer/instances/default/logs/server.log
```

### Créer un tenant (Team)

Via l'API REST :

```bash
curl -X POST http://localhost:9072/rest/apigateway/teams \
  -H "Content-Type: application/json" \
  -u Administrator:YourPassword \
  -d '{
    "name": "tenant-example",
    "description": "Example tenant"
  }'
```

## Backups

Les backups sont automatiquement schedulés quotidiennement à 2h du matin :
- Sauvegarde de la configuration
- Sauvegarde des packages
- Upload vers S3 : `s3://apim-backups-dev/webmethods/`

### Restauration manuelle

```bash
# Télécharger le backup
aws s3 cp s3://apim-backups-dev/webmethods/20251217_020000/ /tmp/restore/ --recursive

# Arrêter le service
systemctl stop webmethods

# Restaurer
tar xzf /tmp/restore/config.tar.gz -C /
tar xzf /tmp/restore/packages.tar.gz -C /

# Redémarrer
systemctl start webmethods
```

## Troubleshooting

### Service ne démarre pas

```bash
# Vérifier les logs
journalctl -u webmethods -n 100

# Vérifier la configuration
/opt/softwareag/profiles/IS_default/bin/startup.sh
```

### Mémoire insuffisante

Augmentez les valeurs dans `webmethods.env` :
```bash
JAVA_MIN_MEM=1024m
JAVA_MAX_MEM=4096m
```

Puis redémarrez :
```bash
systemctl restart webmethods
```

### License invalide

```bash
# Vérifier la license
cat /opt/softwareag/IntegrationServer/instances/default/config/licenseKey.xml

# Récupérer depuis Vault
vault kv get secret/webmethods/license
```

## Intégration avec Control Plane API

Ce Gateway sera automatiquement utilisé par le Control Plane API pour :
- Créer/gérer les APIs
- Gérer les tenants (Teams)
- Gérer les applications

Configuration du Control Plane :
```env
WEBMETHODS_URL=http://webmethods-instance-private-ip:9072
WEBMETHODS_USERNAME=Administrator
WEBMETHODS_PASSWORD=<from-vault>
```

## Architecture

```
┌─────────────────────────────────────────┐
│         Application Load Balancer       │
│              (Port 9072)                │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│      webMethods API Gateway             │
│      - Admin UI: 9072                   │
│      - Runtime: 5555                    │
│      - Multi-tenant (Teams)             │
└────────┬────────────────┬───────────────┘
         │                │
         ▼                ▼
┌────────────────┐  ┌──────────────┐
│   OpenSearch   │  │    Vault     │
│   (Logs/Audit) │  │  (Secrets)   │
└────────────────┘  └──────────────┘
```
