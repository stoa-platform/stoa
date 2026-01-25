# UAC Templates - STOA Platform

Ce répertoire contient les templates Universal API Contract (UAC) pour le onboarding des tenants STOA.

## Architecture

Conformément à l'**ADR-022**, STOA utilise une architecture **flat** : un fichier UAC complet par tenant, bootstrappé depuis ces templates.

```
stoa-catalog/
├── _templates/
│   ├── README.md           # Ce fichier
│   ├── starter.yaml        # Template POC/Startups
│   └── enterprise.yaml     # Template Grands Comptes
└── tenants/
    ├── acme-corp/
    │   └── uac.yaml        # UAC instancié depuis enterprise.yaml
    ├── startup-xyz/
    │   └── uac.yaml        # UAC instancié depuis starter.yaml
    └── ...
```

## Templates disponibles

| Template | Cible | Use Cases |
|----------|-------|-----------|
| `starter.yaml` | POC, Startups, PME | Développement, tests, petite production |
| `enterprise.yaml` | CAC40, Grands Comptes | Production critique, conformité, SLA élevé |

## Comparaison des tiers

| Fonctionnalité | Starter | Enterprise |
|----------------|---------|------------|
| **Rate Limits (H)** | 500 req/h | 50,000 req/h |
| **Rate Limits (VH)** | 50 req/h | 5,000 req/h |
| **Rate Limits (VVH)** | Désactivé | 1,000 req/h |
| **Quota journalier** | 10K req | 1M req |
| **APIs max** | 5 | Illimité |
| **Rétention logs** | 7 jours | 90 jours |
| **Rétention métriques** | 30 jours | 365 jours |
| **Sampling tracing** | 10% | 100% |
| **SLA disponibilité** | 99% | 99.95% |
| **Support** | Email, 48h | 24/7, 4h (P1: 1h) |
| **mTLS** | Non | Oui |
| **Domaines custom** | Non | Oui |
| **Analytics avancées** | Non | Oui |
| **Vault integration** | Non | Oui |
| **Conformité (SOX, PCI)** | Non | Oui |

## Création d'un nouveau tenant

### 1. Copier le template approprié

```bash
# Pour un tenant Starter
TENANT_NAME="my-startup"
mkdir -p stoa-catalog/tenants/${TENANT_NAME}
cp stoa-catalog/_templates/starter.yaml stoa-catalog/tenants/${TENANT_NAME}/uac.yaml

# Pour un tenant Enterprise
TENANT_NAME="acme-corp"
mkdir -p stoa-catalog/tenants/${TENANT_NAME}
cp stoa-catalog/_templates/enterprise.yaml stoa-catalog/tenants/${TENANT_NAME}/uac.yaml
```

### 2. Remplacer les placeholders

```bash
# Variables obligatoires
TENANT_NAME="acme-corp"
TENANT_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
ADMIN_EMAIL="admin@acme-corp.com"
DATE=$(date +%Y-%m-%d)
KEYCLOAK_REALM="${TENANT_NAME}"

# Remplacer dans le fichier
sed -i '' "s/{{TENANT_NAME}}/${TENANT_NAME}/g" stoa-catalog/tenants/${TENANT_NAME}/uac.yaml
sed -i '' "s/{{TENANT_ID}}/${TENANT_ID}/g" stoa-catalog/tenants/${TENANT_NAME}/uac.yaml
sed -i '' "s/{{ADMIN_EMAIL}}/${ADMIN_EMAIL}/g" stoa-catalog/tenants/${TENANT_NAME}/uac.yaml
sed -i '' "s/{{DATE}}/${DATE}/g" stoa-catalog/tenants/${TENANT_NAME}/uac.yaml
sed -i '' "s/{{KEYCLOAK_REALM}}/${KEYCLOAK_REALM}/g" stoa-catalog/tenants/${TENANT_NAME}/uac.yaml
```

### 3. Configurer les placeholders optionnels (Enterprise)

Pour les tenants Enterprise, configurer également :

```bash
# Intégrations
sed -i '' "s|{{ENTERPRISE_IDP_URL}}|https://idp.customer.com|g" uac.yaml
sed -i '' "s|{{MTLS_CA_BUNDLE}}|/path/to/ca-bundle.pem|g" uac.yaml
sed -i '' "s|{{SPLUNK_HEC_URL}}|https://splunk.customer.com:8088|g" uac.yaml
sed -i '' "s|{{SPLUNK_TOKEN}}|xxx|g" uac.yaml

# Alerting
sed -i '' "s|{{SLACK_WEBHOOK}}|https://hooks.slack.com/xxx|g" uac.yaml
sed -i '' "s|{{PAGERDUTY_KEY}}|xxx|g" uac.yaml

# Account management
sed -i '' "s|{{ACCOUNT_MANAGER}}|john.doe@gostoa.dev|g" uac.yaml
sed -i '' "s|{{CONTRACT_ID}}|ENT-2024-001|g" uac.yaml
```

### 4. Valider le YAML

```bash
# Validation syntaxe
yamllint stoa-catalog/tenants/${TENANT_NAME}/uac.yaml

# Validation schéma (si disponible)
kubectl apply --dry-run=client -f stoa-catalog/tenants/${TENANT_NAME}/uac.yaml
```

### 5. Appliquer au cluster

```bash
# Créer le namespace tenant
kubectl create namespace tenant-${TENANT_NAME}

# Appliquer le UAC
kubectl apply -f stoa-catalog/tenants/${TENANT_NAME}/uac.yaml -n tenant-${TENANT_NAME}

# Vérifier
kubectl get uac ${TENANT_NAME} -n tenant-${TENANT_NAME} -o yaml
```

## Checklist post-création

### Starter Tier

- [ ] Placeholders obligatoires remplacés (`TENANT_NAME`, `TENANT_ID`, `ADMIN_EMAIL`, `DATE`, `KEYCLOAK_REALM`)
- [ ] Validation YAML passée
- [ ] Keycloak realm créé
- [ ] Namespace Kubernetes créé
- [ ] UAC appliqué au cluster
- [ ] Email de bienvenue envoyé

### Enterprise Tier

Tout ce qui précède, plus :

- [ ] Contrat signé et `CONTRACT_ID` renseigné
- [ ] Technical Account Manager assigné
- [ ] Intégrations configurées (IdP, SIEM, etc.)
- [ ] Placeholders optionnels configurés ou sections supprimées
- [ ] Private connectivity configurée (si requise)
- [ ] Conformité validée (GDPR, SOX, PCI selon besoins)
- [ ] DR/BC plan documenté
- [ ] Kickoff meeting planifié
- [ ] Runbook créé pour l'équipe support

## Personnalisation des templates

### Sections optionnelles

Les sections marquées `# OPTIONAL:` peuvent être supprimées si non nécessaires :

```yaml
# OPTIONAL: IP allowlisting (empty = allow all)
ip_allowlist: []
```

### Ajout de scopes custom

```yaml
authorization:
  custom_scopes:
    - "{{TENANT_NAME}}:inventory:read"
    - "{{TENANT_NAME}}:inventory:write"
    - "{{TENANT_NAME}}:orders:admin"
```

### Override par classification

```yaml
classifications:
  VH:
    rate_limit: 200  # Override du défaut 50
```

## Mise à jour des templates

Lors de la mise à jour des templates :

1. **Ne jamais modifier directement** les UAC instanciés des tenants existants
2. Documenter les changements dans le CHANGELOG
3. Communiquer les nouvelles fonctionnalités aux tenants concernés
4. Pour les breaking changes, créer un plan de migration

## Support

- **Documentation** : https://docs.gostoa.dev/uac
- **Issues** : https://gitlab.gostoa.dev/stoa/platform/-/issues
- **Slack** : #stoa-platform
