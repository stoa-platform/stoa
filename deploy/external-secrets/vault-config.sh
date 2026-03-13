#!/bin/bash
# Configure Vault Kubernetes auth for External Secrets Operator
# Uses curl (no vault CLI dependency)
#
# Prerequisites:
#   - VAULT_ADDR=https://hcvault.gostoa.dev
#   - VAULT_TOKEN set (admin token)
#   - kubectl configured for OVH prod cluster (KUBECONFIG)
#
# Phase 2 (CAB-1798) — run after Vault is operational + secrets migrated

set -euo pipefail

VAULT_ADDR="${VAULT_ADDR:-https://hcvault.gostoa.dev}"
NAMESPACE="stoa-system"

echo "=== Configuring Vault for ESO ==="
echo "Vault: ${VAULT_ADDR}"
echo ""

# Step 1: Create k8s-eso policy (read k8s/*, shared/*, dev/*)
echo "[1/4] Creating k8s-eso policy..."
curl -sf -X PUT "${VAULT_ADDR}/v1/sys/policies/acl/k8s-eso" \
  -H "X-Vault-Token: ${VAULT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "policy": "path \"stoa/data/k8s/*\" { capabilities = [\"read\"] }\npath \"stoa/metadata/k8s/*\" { capabilities = [\"list\", \"read\"] }\npath \"stoa/data/shared/*\" { capabilities = [\"read\"] }\npath \"stoa/metadata/shared/*\" { capabilities = [\"list\", \"read\"] }\npath \"stoa/data/dev/*\" { capabilities = [\"read\"] }\npath \"stoa/metadata/dev/*\" { capabilities = [\"list\", \"read\"] }"
  }' && echo "  OK"

# Step 2: Enable Kubernetes auth (idempotent)
echo "[2/4] Enabling Kubernetes auth..."
curl -sf -X POST "${VAULT_ADDR}/v1/sys/auth/kubernetes" \
  -H "X-Vault-Token: ${VAULT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"type": "kubernetes"}' 2>/dev/null && echo "  Enabled" || echo "  Already enabled"

# Step 3: Configure K8s auth with cluster details
echo "[3/4] Configuring K8s auth..."
K8S_HOST=$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}')
K8S_CA_CERT=$(kubectl config view --raw --minify -o jsonpath='{.clusters[0].cluster.certificate-authority-data}' | base64 -d)

curl -sf -X POST "${VAULT_ADDR}/v1/auth/kubernetes/config" \
  -H "X-Vault-Token: ${VAULT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$(python3 -c "
import json
config = {
    'kubernetes_host': '${K8S_HOST}',
    'kubernetes_ca_cert': '''${K8S_CA_CERT}''',
    'disable_local_ca_jwt': True
}
print(json.dumps(config))
")" && echo "  Configured for ${K8S_HOST}"

# Step 4: Create role for external-secrets service account
echo "[4/4] Creating external-secrets role..."
curl -sf -X POST "${VAULT_ADDR}/v1/auth/kubernetes/role/external-secrets" \
  -H "X-Vault-Token: ${VAULT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{
    \"bound_service_account_names\": [\"external-secrets-sa\"],
    \"bound_service_account_namespaces\": [\"${NAMESPACE}\"],
    \"policies\": [\"k8s-eso\"],
    \"ttl\": \"1h\"
  }" && echo "  OK"

echo ""
echo "=== Vault ESO Configuration Complete ==="
echo ""
echo "Next steps:"
echo "  1. Apply SecretStore:     kubectl apply -f secret-store.yaml"
echo "  2. Apply ExternalSecrets: kubectl apply -f external-secret-*.yaml"
echo ""
echo "Verify:"
echo "  kubectl get secretstores -n stoa-system"
echo "  kubectl get externalsecrets -n stoa-system"
