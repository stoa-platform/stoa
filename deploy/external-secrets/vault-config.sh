#!/bin/bash
# Configure Vault for External Secrets Operator
# Run this from a machine with Vault CLI access and kubectl access
#
# Prerequisites:
#   - VAULT_ADDR=https://hcv.gostoa.dev
#   - VAULT_TOKEN set (admin token)
#   - kubectl configured for OVH prod cluster
#
# This is Phase 2 (CAB-1798) — only run after Vault is operational (Phase 0)
# and secrets are migrated (Phase 1)

set -e

VAULT_ADDR="${VAULT_ADDR:-https://hcv.gostoa.dev}"
NAMESPACE="stoa-system"

echo "Configuring Vault for External Secrets Operator..."
echo "Vault: ${VAULT_ADDR}"
echo ""

# Create policy for external-secrets (read stoa/k8s/* and stoa/shared/*)
vault policy write k8s-eso - <<EOF
# Read K8s secrets
path "stoa/data/k8s/*" {
  capabilities = ["read"]
}

path "stoa/metadata/k8s/*" {
  capabilities = ["list", "read"]
}

# Read shared secrets (Keycloak, etc.)
path "stoa/data/shared/*" {
  capabilities = ["read"]
}

path "stoa/metadata/shared/*" {
  capabilities = ["list", "read"]
}
EOF

echo "Policy 'k8s-eso' created"

# Enable Kubernetes auth if not already enabled
vault auth enable kubernetes 2>/dev/null || echo "Kubernetes auth already enabled"

# Configure Kubernetes auth with OVH cluster details
K8S_HOST=$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}')
K8S_CA_CERT=$(kubectl get configmap -n kube-system kube-root-ca.crt -o jsonpath='{.data.ca\.crt}' 2>/dev/null || \
  kubectl config view --raw --minify -o jsonpath='{.clusters[0].cluster.certificate-authority-data}' | base64 -d)

vault write auth/kubernetes/config \
  kubernetes_host="$K8S_HOST" \
  kubernetes_ca_cert="$K8S_CA_CERT" \
  disable_local_ca_jwt=true

echo "Kubernetes auth configured for $K8S_HOST"

# Create role for external-secrets service account
vault write auth/kubernetes/role/external-secrets \
  bound_service_account_names=external-secrets-sa \
  bound_service_account_namespaces=$NAMESPACE \
  policies=k8s-eso \
  ttl=1h

echo "Role 'external-secrets' created"

echo ""
echo "Vault configuration complete!"
echo ""
echo "Next steps:"
echo "1. Apply SecretStore and ExternalSecrets:"
echo "   kubectl apply -f secret-store.yaml"
echo "   kubectl apply -f external-secret-database.yaml"
echo "   kubectl apply -f external-secret-minio.yaml"
echo ""
echo "2. Verify:"
echo "   kubectl get secretstores -n stoa-system"
echo "   kubectl get externalsecrets -n stoa-system"
