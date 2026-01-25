#!/bin/bash
# Configure Vault for External Secrets Operator
# Run this from a machine with Vault access

set -e

VAULT_ADDR="${VAULT_ADDR:-http://127.0.0.1:8200}"
NAMESPACE="stoa-system"

echo "Configuring Vault for External Secrets Operator..."

# Create policy for external-secrets
vault policy write external-secrets - <<EOF
# Read secrets from apim path
path "secret/data/apim/*" {
  capabilities = ["read"]
}

path "secret/metadata/apim/*" {
  capabilities = ["list", "read"]
}
EOF

echo "Policy 'external-secrets' created"

# Enable Kubernetes auth if not already enabled
vault auth enable kubernetes 2>/dev/null || echo "Kubernetes auth already enabled"

# Configure Kubernetes auth
# Get the Kubernetes API server address
K8S_HOST=$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}')

# Get the CA cert from the service account
K8S_CA_CERT=$(kubectl get secret -n vault vault-token -o jsonpath='{.data.ca\.crt}' 2>/dev/null | base64 -d || \
  kubectl exec -n vault vault-0 -- cat /var/run/secrets/kubernetes.io/serviceaccount/ca.crt)

vault write auth/kubernetes/config \
  kubernetes_host="$K8S_HOST" \
  kubernetes_ca_cert="$K8S_CA_CERT" \
  disable_local_ca_jwt=true

echo "Kubernetes auth configured"

# Create role for external-secrets service account
vault write auth/kubernetes/role/external-secrets \
  bound_service_account_names=external-secrets-sa \
  bound_service_account_namespaces=$NAMESPACE \
  policies=external-secrets \
  ttl=1h

echo "Role 'external-secrets' created"

echo ""
echo "Vault configuration complete!"
echo ""
echo "Next steps:"
echo "1. Install External Secrets Operator:"
echo "   helm install external-secrets external-secrets/external-secrets -n external-secrets --create-namespace"
echo ""
echo "2. Apply SecretStore and ExternalSecrets:"
echo "   kubectl apply -f secret-store.yaml"
echo "   kubectl apply -f external-secret-database.yaml"
echo "   kubectl apply -f external-secret-minio.yaml"
