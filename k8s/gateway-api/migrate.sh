#!/usr/bin/env bash
# Ingress → HTTPRoute Migration — Phase 2 of CAB-1301
# Usage: KUBECONFIG=~/.kube/config-stoa-ovh ./k8s/gateway-api/migrate.sh
#
# Migrates 9 Ingress resources to Gateway API HTTPRoutes.
# Existing Ingress resources are NOT deleted (dual-stack during validation).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NGF_NAMESPACE="nginx-gateway"

TOTAL=7
echo "=== Ingress → HTTPRoute Migration (CAB-1400) ==="
echo ""

# 1. Copy TLS secrets to nginx-gateway namespace
echo "[1/$TOTAL] Copying TLS secrets to ${NGF_NAMESPACE}..."
declare -A SECRETS=(
  ["argocd-server-tls"]="argocd"
  ["control-plane-ui-tls"]="stoa-system"
  ["keycloak-tls"]="stoa-system"
  ["control-plane-api-tls"]="stoa-system"
  ["stoa-gateway-tls"]="stoa-system"
  ["stoa-portal-tls"]="stoa-system"
  ["pushgateway-tls"]="monitoring"
  ["opensearch-dashboards-tls"]="opensearch"
)

# Use grafana-tls for console.gostoa.dev is not needed — control-plane-ui-tls covers it
# (both Ingress resources for console.gostoa.dev share the same host, different paths)

for SECRET in "${!SECRETS[@]}"; do
  SRC_NS="${SECRETS[$SECRET]}"
  if kubectl get secret "$SECRET" -n "$NGF_NAMESPACE" &>/dev/null; then
    echo "  $SECRET already exists in $NGF_NAMESPACE. Skipping."
  else
    echo "  Copying $SECRET from $SRC_NS → $NGF_NAMESPACE..."
    kubectl get secret "$SECRET" -n "$SRC_NS" -o json | \
      python3 -c "
import json, sys
s = json.load(sys.stdin)
s['metadata'] = {'name': s['metadata']['name'], 'namespace': '$NGF_NAMESPACE'}
json.dump(s, sys.stdout)
" | kubectl apply -f -
  fi
done

# 2. Upgrade NGF service to LoadBalancer
echo ""
echo "[2/$TOTAL] Upgrading NGF service to LoadBalancer..."
helm upgrade ngf oci://ghcr.io/nginx/charts/nginx-gateway-fabric \
  --namespace "${NGF_NAMESPACE}" \
  --version 2.4.2 \
  --values "${SCRIPT_DIR}/values-ngf.yaml" \
  --set service.type=LoadBalancer \
  --wait --timeout 120s

# 3. Apply Gateway resource
echo ""
echo "[3/$TOTAL] Applying Gateway resource..."
kubectl apply -f "${SCRIPT_DIR}/gateway.yaml"

# 4. Apply HTTPRoutes
echo ""
echo "[4/$TOTAL] Applying HTTPRoutes..."
kubectl apply -f "${SCRIPT_DIR}/httproutes/"

# 5. Wait for Gateway to be programmed
echo ""
echo "[5/$TOTAL] Waiting for Gateway to be programmed..."
sleep 10
kubectl get gateway stoa -n "${NGF_NAMESPACE}"

# 6. Get new LoadBalancer IP
echo ""
echo "[6/$TOTAL] Checking LoadBalancer IP..."
for i in {1..30}; do
  NEW_IP=$(kubectl get svc ngf-nginx-gateway-fabric -n "${NGF_NAMESPACE}" -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)
  if [ -n "$NEW_IP" ]; then
    break
  fi
  echo "  Waiting for LB IP allocation... ($i/30)"
  sleep 10
done

if [ -z "$NEW_IP" ]; then
  echo "  WARNING: LoadBalancer IP not assigned after 5 minutes."
  echo "  Check: kubectl get svc ngf-nginx-gateway-fabric -n ${NGF_NAMESPACE}"
  exit 1
fi
echo "  New LoadBalancer IP: $NEW_IP"

# 7. Validate routes
echo ""
echo "[7/$TOTAL] Validating HTTPRoutes on new LB IP..."
echo ""
OLD_IP="5.196.236.53"
HOSTS=(
  "argocd.gostoa.dev"
  "console.gostoa.dev"
  "auth.gostoa.dev"
  "api.gostoa.dev"
  "mcp.gostoa.dev"
  "portal.gostoa.dev"
  "pushgateway.gostoa.dev"
  "opensearch.gostoa.dev"
)

PASS=0
FAIL=0
for HOST in "${HOSTS[@]}"; do
  HTTP_CODE=$(curl -sk -o /dev/null -w "%{http_code}" --resolve "${HOST}:443:${NEW_IP}" "https://${HOST}/" --max-time 10 2>/dev/null || echo "000")
  if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 500 ]; then
    echo "  ✅ ${HOST}: HTTP ${HTTP_CODE}"
    PASS=$((PASS + 1))
  else
    echo "  ❌ ${HOST}: HTTP ${HTTP_CODE}"
    FAIL=$((FAIL + 1))
  fi
done

echo ""
echo "=== Migration Summary ==="
echo "  Old LB (Nginx Ingress): ${OLD_IP}"
echo "  New LB (NGF):           ${NEW_IP}"
echo "  Routes:                 ${PASS} pass, ${FAIL} fail"
echo ""

if [ "$FAIL" -eq 0 ]; then
  echo "  All routes validated. Ready for DNS cutover."
  echo ""
  echo "  DNS Update (Cloudflare):"
  for HOST in "${HOSTS[@]}"; do
    SUBDOMAIN="${HOST%.gostoa.dev}"
    echo "    ${SUBDOMAIN}.gostoa.dev  A  ${NEW_IP}  (was ${OLD_IP})"
  done
  echo ""
  echo "  After DNS propagation, delete old Ingress resources:"
  echo "    kubectl delete ingress -A -l '!gateway.networking.k8s.io/route-name'"
else
  echo "  WARNING: ${FAIL} routes failed. Fix before DNS cutover."
  echo ""
  echo "  Debug:"
  echo "    kubectl get httproutes -A"
  echo "    kubectl describe gateway stoa -n ${NGF_NAMESPACE}"
fi
