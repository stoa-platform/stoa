#!/usr/bin/env bash
# Gateway API Foundation — Rollback / Uninstall
# Usage: KUBECONFIG=~/.kube/config-stoa-ovh ./k8s/gateway-api/rollback.sh
#
# Removes NGF and Gateway API CRDs. Does NOT touch existing Nginx Ingress.
set -euo pipefail

NGF_NAMESPACE="nginx-gateway"
GATEWAY_API_VERSION="v1.4.1"

echo "=== Gateway API Foundation Rollback ==="
echo ""
echo "This will:"
echo "  1. Uninstall NGINX Gateway Fabric Helm release"
echo "  2. Delete namespace ${NGF_NAMESPACE}"
echo "  3. Remove Gateway API CRDs"
echo ""
read -rp "Continue? [y/N] " confirm
if [[ "${confirm}" != "y" && "${confirm}" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi

# 1. Uninstall Helm release
echo "[1/3] Uninstalling NGF Helm release..."
if helm status ngf -n "${NGF_NAMESPACE}" &>/dev/null; then
  helm uninstall ngf -n "${NGF_NAMESPACE}" --wait
  echo "  Done."
else
  echo "  No release 'ngf' found. Skipping."
fi

# 2. Delete namespace
echo "[2/3] Deleting namespace ${NGF_NAMESPACE}..."
kubectl delete namespace "${NGF_NAMESPACE}" --ignore-not-found --wait=true

# 3. Remove Gateway API CRDs
echo "[3/3] Removing Gateway API CRDs..."
kubectl delete -f "https://github.com/kubernetes-sigs/gateway-api/releases/download/${GATEWAY_API_VERSION}/standard-install.yaml" --ignore-not-found
echo "  Done."

echo ""
echo "=== Rollback complete. Only Nginx Ingress Controller remains. ==="
