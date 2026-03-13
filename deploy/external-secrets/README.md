# External Secrets Operator — Vault Integration

Synchronizes secrets from HashiCorp Vault (hcvault.gostoa.dev) to Kubernetes.

## Prerequisites

1. **Vault operational** (Phase 0 — CAB-1796)
2. **Secrets migrated** (Phase 1 — CAB-1797)
3. **ESO installed** on K8s cluster

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm repo update
helm install external-secrets external-secrets/external-secrets \
  -n external-secrets --create-namespace --set installCRDs=true
```

## Setup (Phase 2 — CAB-1798)

### 1. Configure Vault K8s auth

```bash
export VAULT_TOKEN="<admin-token>"
export VAULT_ADDR="https://hcvault.gostoa.dev"
export KUBECONFIG=~/.kube/config-stoa-ovh
./vault-config.sh
```

### 2. Apply SecretStore + ExternalSecrets

```bash
kubectl apply -f secret-store.yaml
kubectl apply -f external-secret-gateway.yaml
kubectl apply -f external-secret-opensearch.yaml
kubectl apply -f external-secret-database.yaml
```

## Vault Paths

| Vault Path | K8s Secret | Component | Keys |
|---|---|---|---|
| `k8s/gateway` | `stoa-gateway-secrets` | stoa-gateway | STOA_CONTROL_PLANE_API_KEY, STOA_KEYCLOAK_CLIENT_SECRET |
| `k8s/opensearch` | `stoa-opensearch-secret` | control-plane-api | 6 OpenSearch keys |
| `dev/env` | `postgresql-credentials` | control-plane-api | DEV_PG_* (5 keys) |

## Verification

```bash
kubectl get secretstore -n stoa-system
kubectl get externalsecret -n stoa-system
kubectl get secrets -n stoa-system | grep -E "gateway|opensearch|postgresql"
```

## Troubleshooting

```bash
# ESO logs
kubectl logs -n external-secrets -l app.kubernetes.io/name=external-secrets

# ExternalSecret events
kubectl describe externalsecret -n stoa-system

# Test Vault connectivity from cluster
kubectl run vault-test --rm -it --image=curlimages/curl -- \
  curl -sf https://hcvault.gostoa.dev/v1/sys/health
```
