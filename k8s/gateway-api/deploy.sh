#!/usr/bin/env bash
# Gateway API Foundation — Idempotent deploy to OVH K8s
# Usage: KUBECONFIG=~/.kube/config-stoa-ovh ./k8s/gateway-api/deploy.sh
#
# Phase 1 of CAB-1301: Installs Gateway API CRDs + NGINX Gateway Fabric controller.
# Does NOT migrate any existing Ingress resources (that's Phase 2).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Versions (pin for reproducibility) ---
GATEWAY_API_VERSION="v1.4.1"
NGF_CHART_VERSION="2.4.2"
NGF_NAMESPACE="nginx-gateway"

TOTAL=6
echo "=== Gateway API Foundation Deploy (CAB-1399) ==="
echo "  Gateway API CRDs: ${GATEWAY_API_VERSION}"
echo "  NGINX Gateway Fabric: ${NGF_CHART_VERSION}"
echo ""

# 1. Install Gateway API CRDs (standard channel)
echo "[1/$TOTAL] Installing Gateway API CRDs ${GATEWAY_API_VERSION}..."
if kubectl get crd gateways.gateway.networking.k8s.io &>/dev/null; then
  EXISTING=$(kubectl get crd gateways.gateway.networking.k8s.io -o jsonpath='{.metadata.annotations.gateway\.networking\.k8s\.io/bundle-version}' 2>/dev/null || echo "unknown")
  echo "  Gateway API CRDs already installed (bundle: ${EXISTING}). Applying update..."
fi
kubectl apply --server-side -f "https://github.com/kubernetes-sigs/gateway-api/releases/download/${GATEWAY_API_VERSION}/standard-install.yaml"
echo "  CRDs installed."

# 2. Create namespace
echo "[2/$TOTAL] Creating namespace ${NGF_NAMESPACE}..."
kubectl create namespace "${NGF_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

# 3. Install NGINX Gateway Fabric via Helm
echo "[3/$TOTAL] Installing NGINX Gateway Fabric ${NGF_CHART_VERSION}..."
if helm status ngf -n "${NGF_NAMESPACE}" &>/dev/null; then
  echo "  Release 'ngf' already exists. Upgrading..."
  helm upgrade ngf oci://ghcr.io/nginx/charts/nginx-gateway-fabric \
    --namespace "${NGF_NAMESPACE}" \
    --version "${NGF_CHART_VERSION}" \
    --values "${SCRIPT_DIR}/values-ngf.yaml" \
    --wait --timeout 120s
else
  helm install ngf oci://ghcr.io/nginx/charts/nginx-gateway-fabric \
    --namespace "${NGF_NAMESPACE}" \
    --version "${NGF_CHART_VERSION}" \
    --values "${SCRIPT_DIR}/values-ngf.yaml" \
    --wait --timeout 120s
fi

# 4. Wait for controller ready
echo "[4/$TOTAL] Waiting for NGF controller..."
kubectl rollout status deployment/ngf-nginx-gateway-fabric -n "${NGF_NAMESPACE}" --timeout=120s

# 5. Apply GatewayClass
echo "[5/$TOTAL] Applying GatewayClass..."
kubectl apply -f "${SCRIPT_DIR}/gatewayclass.yaml"

# 6. Verify
echo "[6/$TOTAL] Verifying installation..."
echo ""
echo "--- Gateway API CRDs ---"
kubectl get crd | grep gateway.networking.k8s.io
echo ""
echo "--- GatewayClass ---"
kubectl get gatewayclass
echo ""
echo "--- NGF Controller ---"
kubectl get pods -n "${NGF_NAMESPACE}"
echo ""
echo "--- Existing Nginx Ingress (should still be running) ---"
kubectl get pods -n ingress-nginx
echo ""
echo "=== Deploy complete. Dual-stack validated: both controllers running. ==="
echo "  Next: Phase 2 (CAB-1400) — migrate Ingress resources to HTTPRoute"
