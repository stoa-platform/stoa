#!/bin/bash
# deploy-secrets.sh — Decrypt SOPS secrets and apply to K3s cluster
#
# Usage:
#   ./scripts/deploy-secrets.sh [environment]
#
# Prerequisites:
#   - sops installed (brew install sops)
#   - age key at ~/.config/sops/age/keys.txt (or SOPS_AGE_KEY env var)
#   - KUBECONFIG pointing to target cluster
#
# Environments: production (default)

set -euo pipefail

ENV="${1:-production}"
SECRETS_FILE="deploy/secrets/${ENV}.enc.yaml"
NAMESPACE="stoa-system"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config-stoa-prod}"

if [ ! -f "$SECRETS_FILE" ]; then
  echo "Error: Secrets file not found: $SECRETS_FILE"
  echo "Available files:"
  ls deploy/secrets/*.enc.yaml 2>/dev/null || echo "  (none)"
  exit 1
fi

echo "Decrypting secrets from $SECRETS_FILE..."
DECRYPTED=$(sops -d "$SECRETS_FILE")

echo "Applying secrets to namespace $NAMESPACE..."
echo "$DECRYPTED" | KUBECONFIG="$KUBECONFIG" kubectl apply -n "$NAMESPACE" -f -

echo "Secrets deployed successfully to $NAMESPACE"
echo ""
echo "Verify:"
echo "  kubectl get secrets -n $NAMESPACE"
