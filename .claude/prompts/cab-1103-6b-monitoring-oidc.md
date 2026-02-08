CAB-1103 Phase 6B: Monitoring OIDC — Grafana + Prometheus authentifies via Keycloak.

Branch: `feat/cab-1103-6b-monitoring-oidc` (creer depuis main)

## Contexte
Grafana et Prometheus sont accessibles sans auth ou avec auth basique. On veut les proteger via OIDC (Keycloak).
Keycloak admin: voir `.env` a la racine du repo pour les credentials (auth.gostoa.dev).

## Architecture
```
Grafana   ──OIDC──→  Keycloak (auth.gostoa.dev, realm: stoa)
Prometheus ──oauth2-proxy──→  Keycloak
AlertManager → Slack webhooks (routing par severite)
```

## Taches

### 1. Creer le client Keycloak `stoa-observability`
Via l'Admin REST API de Keycloak:
```bash
# 1. Obtenir un token admin
TOKEN=$(curl -s -X POST "https://auth.gostoa.dev/realms/master/protocol/openid-connect/token" \
  -d "grant_type=password&client_id=admin-cli&username=admin&password=demo" | jq -r '.access_token')

# 2. Creer le client
curl -s -X POST "https://auth.gostoa.dev/admin/realms/stoa/clients" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "clientId": "stoa-observability",
    "name": "STOA Observability",
    "enabled": true,
    "protocol": "openid-connect",
    "publicClient": false,
    "standardFlowEnabled": true,
    "directAccessGrantsEnabled": false,
    "redirectUris": [
      "https://grafana.gostoa.dev/login/generic_oauth",
      "https://grafana.gostoa.dev/*",
      "http://localhost:3001/login/generic_oauth"
    ],
    "webOrigins": ["https://grafana.gostoa.dev", "http://localhost:3001"]
  }'

# 3. Recuperer le client secret
CLIENT_ID=$(curl -s "https://auth.gostoa.dev/admin/realms/stoa/clients?clientId=stoa-observability" \
  -H "Authorization: Bearer $TOKEN" | jq -r '.[0].id')
curl -s "https://auth.gostoa.dev/admin/realms/stoa/clients/$CLIENT_ID/client-secret" \
  -H "Authorization: Bearer $TOKEN" | jq -r '.value'
```

### 2. Configurer Grafana OIDC
Fichier: `deploy/docker-compose/docker-compose.yml` (section grafana) ou `charts/stoa-platform/values.yaml`

Variables d'environnement Grafana:
```yaml
GF_AUTH_GENERIC_OAUTH_ENABLED: "true"
GF_AUTH_GENERIC_OAUTH_NAME: "STOA SSO"
GF_AUTH_GENERIC_OAUTH_CLIENT_ID: "stoa-observability"
GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET: "<secret from step 1>"
GF_AUTH_GENERIC_OAUTH_SCOPES: "openid profile email"
GF_AUTH_GENERIC_OAUTH_AUTH_URL: "https://auth.gostoa.dev/realms/stoa/protocol/openid-connect/auth"
GF_AUTH_GENERIC_OAUTH_TOKEN_URL: "https://auth.gostoa.dev/realms/stoa/protocol/openid-connect/token"
GF_AUTH_GENERIC_OAUTH_API_URL: "https://auth.gostoa.dev/realms/stoa/protocol/openid-connect/userinfo"
GF_AUTH_GENERIC_OAUTH_ROLE_ATTRIBUTE_PATH: "contains(roles[*], 'stoa:admin') && 'Admin' || 'Viewer'"
GF_AUTH_GENERIC_OAUTH_ALLOW_ASSIGN_GRAFANA_ADMIN: "true"
GF_SERVER_ROOT_URL: "https://grafana.gostoa.dev"
GF_SERVER_SERVE_FROM_SUB_PATH: "true"
GF_SECURITY_ALLOW_EMBEDDING: "true"
```

### 3. Configurer oauth2-proxy pour Prometheus
Fichier: `deploy/docker-compose/docker-compose.yml` ou creer `deploy/docker-compose/oauth2-proxy.yml`
- Image: `quay.io/oauth2-proxy/oauth2-proxy:v7.6.0`
- Provider: `keycloak-oidc`
- upstream: `http://prometheus:9090`
- Ajouter dans Helm values si applicable

### 4. AlertManager routing
Fichier: `deploy/docker-compose/alertmanager/alertmanager.yml` ou `charts/stoa-platform/templates/alertmanager-config.yaml`

```yaml
route:
  receiver: 'default'
  routes:
    - match:
        severity: critical
      receiver: 'slack-incidents'
    - match:
        severity: warning
      receiver: 'slack-alerts'

receivers:
  - name: 'default'
    slack_configs:
      - api_url: '${SLACK_WEBHOOK_URL}'
        channel: '#alerts'
  - name: 'slack-incidents'
    slack_configs:
      - api_url: '${SLACK_WEBHOOK_URL}'
        channel: '#incidents'
        title: 'CRITICAL: {{ .GroupLabels.alertname }}'
  - name: 'slack-alerts'
    slack_configs:
      - api_url: '${SLACK_WEBHOOK_URL}'
        channel: '#alerts'
```

### 5. Mettre a jour Helm values
- `charts/stoa-platform/values.yaml`: section grafana.oidc, prometheus.oauth2proxy, alertmanager
- S'assurer que les secrets sont references via K8s Secrets (pas en dur)

## DoD
- [ ] Client `stoa-observability` cree dans Keycloak realm stoa
- [ ] Grafana configuree pour OIDC (docker-compose + Helm values)
- [ ] oauth2-proxy configure pour Prometheus
- [ ] AlertManager routing: critical → #incidents, warning → #alerts
- [ ] Commit: `feat(monitoring): OIDC auth for Grafana/Prometheus + AlertManager routing (CAB-1103)`

## Contraintes
- Stocker le client secret dans `.env` local (gitignore) + K8s Secret reference dans Helm
- Ne PAS hardcoder de secrets dans les fichiers trackes
- Ne PAS push
- Credentials Keycloak admin: lire `.env` a la racine
