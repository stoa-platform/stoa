# External Secrets Operator Setup

Synchronizes secrets from HashiCorp Vault to Kubernetes.

## Installation

```bash
# Add Helm repo
helm repo add external-secrets https://charts.external-secrets.io
helm repo update

# Install ESO
helm install external-secrets external-secrets/external-secrets \
  -n external-secrets \
  --create-namespace \
  --set installCRDs=true
```

## Configuration

### 1. Create SecretStore

```bash
kubectl apply -f secret-store.yaml
```

### 2. Create ExternalSecrets

```bash
kubectl apply -f external-secret-database.yaml
kubectl apply -f external-secret-minio.yaml
```

## Vault Paths

| Path | Description |
|------|-------------|
| `secret/apim/dev/database` | PostgreSQL credentials |
| `secret/apim/dev/minio` | MinIO credentials |
| `secret/apim/dev/gateway-admin` | Gateway admin credentials |
| `secret/apim/dev/keycloak-admin` | Keycloak admin credentials |

## Verification

```bash
# Check SecretStore status
kubectl get secretstore -n stoa-system

# Check ExternalSecret sync status
kubectl get externalsecret -n stoa-system

# View synced secrets
kubectl get secrets -n stoa-system | grep -E "minio|postgres|database"
```

## Troubleshooting

```bash
# Check ESO logs
kubectl logs -n external-secrets -l app.kubernetes.io/name=external-secrets

# Check ExternalSecret events
kubectl describe externalsecret -n stoa-system
```
