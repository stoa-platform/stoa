# Configuration

## BASE_DOMAIN

`BASE_DOMAIN` is the single source of truth for all service URLs.

All other URLs derive from it:

| Variable | Value |
|----------|-------|
| `BASE_DOMAIN` | `gostoa.dev` |
| Console | `https://console.${BASE_DOMAIN}` |
| Portal | `https://portal.${BASE_DOMAIN}` |
| API | `https://api.${BASE_DOMAIN}` |
| MCP Gateway | `https://mcp.${BASE_DOMAIN}` |
| Auth | `https://auth.${BASE_DOMAIN}` |

## Environment Variables by Component

### Control Plane API

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | — | PostgreSQL connection string |
| `KEYCLOAK_URL` | — | Keycloak base URL |
| `KEYCLOAK_REALM` | `stoa` | Keycloak realm name |
| `KEYCLOAK_CLIENT_ID` | `control-plane-ui` | OIDC client ID |
| `KEYCLOAK_CLIENT_SECRET` | — | OIDC client secret (from Vault) |
| `MINIO_ENDPOINT` | — | MinIO/S3 endpoint |
| `MINIO_ACCESS_KEY` | — | MinIO access key (from Vault) |
| `MINIO_SECRET_KEY` | — | MinIO secret key (from Vault) |
| `OPENSEARCH_URL` | — | OpenSearch endpoint |
| `GATEWAY_API_KEYS` | — | Comma-separated gateway API keys |
| `BASE_DOMAIN` | — | Base domain for URL generation |

### MCP Gateway

| Variable | Default | Description |
|----------|---------|-------------|
| `OPA_ENABLED` | `true` | Enable OPA policy engine |
| `OPA_EMBEDDED` | `true` | Use embedded OPA evaluator |
| `METERING_ENABLED` | `true` | Enable Kafka metering events |
| `K8S_WATCHER_ENABLED` | `false` | Enable CRD watcher for Tool resources |
| `CONTROL_PLANE_URL` | — | Control Plane API URL |
| `CONTROL_PLANE_API_KEY` | — | API key for CP auth (from Vault) |
| `JWT_SECRET` | — | JWT signing secret (from Vault) |
| `KAFKA_BOOTSTRAP_SERVERS` | — | Kafka brokers |

### Console UI / Portal (nginx)

| Variable | Default | Description |
|----------|---------|-------------|
| `API_BACKEND_URL` | — | Control Plane API backend for proxy_pass |
| `LOGS_BACKEND_URL` | — | OpenSearch backend for log proxy |
| `GRAFANA_BACKEND_URL` | — | Grafana backend for dashboard proxy |
| `DNS_RESOLVER` | `10.100.0.10` | Cluster DNS resolver for nginx |

### STOA Gateway (Rust)

| Variable | Default | Description |
|----------|---------|-------------|
| `LISTEN_ADDR` | `0.0.0.0:8443` | Listen address |
| `CONTROL_PLANE_URL` | — | Control Plane API URL |
| `JWT_SECRET` | — | JWT validation secret |
| `ADMIN_API_TOKEN` | — | Admin registration token |

## Environment Config Files

Per-environment configurations are in `deploy/config/`:

```
deploy/config/
├── dev.env
├── staging.env
└── prod.env
```

These are used for local development and CI references. In production, all configuration comes from Helm values + Vault secrets.

## Secrets Configuration

### With Vault + ESO (Recommended)

Secrets are stored in Vault and synced to Kubernetes via External Secrets Operator.

Vault paths:

| Path | Content |
|------|---------|
| `secret/apim/{env}/database` | PostgreSQL credentials |
| `secret/apim/{env}/minio` | MinIO/S3 credentials |
| `secret/apim/{env}/gateway-admin` | Gateway admin token |
| `secret/apim/{env}/keycloak-admin` | Keycloak admin credentials |
| `secret/stoa/data/gateway` | Gateway runtime secrets |

Where `{env}` = `dev`, `staging`, `prod`.

ESO syncs these to K8s Secret `stoa-gateway-secrets`:

```yaml
# charts/stoa-platform/values.yaml
externalSecret:
  enabled: true
  refreshInterval: 1h
  secretStoreRef: vault-backend
  vaultPath: stoa/data/gateway
```

### Without Vault (K8s Secrets only)

Create secrets manually:

```bash
kubectl create secret generic stoa-gateway-secrets \
  -n stoa-system \
  --from-literal=control_plane_api_key=<key> \
  --from-literal=jwt_secret=<secret> \
  --from-literal=keycloak_client_secret=<secret> \
  --from-literal=admin_api_token=<token>
```

### Referencing Secrets in Deployments

Use `envFrom` for the full secret, or `env.valueFrom` for individual keys:

```yaml
# Full secret
envFrom:
  - secretRef:
      name: stoa-gateway-secrets
      optional: true              # Prevents pod crash if secret missing

# Individual key
env:
  - name: DATABASE_URL
    valueFrom:
      secretKeyRef:
        name: stoa-db-credentials
        key: connection_string
```

## Helm Values Reference

The full values reference is in `charts/stoa-platform/values.yaml`. Key sections:

```yaml
global:
  baseDomain: ""
  registry: ""
  imagePullSecrets: []

controlPlaneApi:
  replicas: 1
  image: { repository: "", tag: "" }
  resources: { requests: { cpu: 200m, memory: 256Mi } }

mcpGateway:
  replicas: 1
  opa: { enabled: true, embedded: true }
  metering: { enabled: true }

controlPlaneUi:
  replicas: 1

portal:
  replicas: 1

stoaGateway:
  replicas: 1

externalSecret:
  enabled: false
  refreshInterval: 1h
  secretStoreRef: vault-backend
  vaultPath: stoa/data/gateway
```
