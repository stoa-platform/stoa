#!/bin/bash
# CAB-1305: Deploy security CronJobs to K8s
# Idempotent — safe to run multiple times
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
NAMESPACE="stoa-system"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config-stoa-ovh}"
export KUBECONFIG

echo "=== STOA Security Jobs — Deploy ==="
echo "Kubeconfig: $KUBECONFIG"
echo "Namespace:  $NAMESPACE"
echo ""

# Step 1: Create ConfigMap from scripts
echo "[1/4] Creating ConfigMap 'security-scripts'..."
kubectl create configmap security-scripts \
  --from-file="$SCRIPT_DIR/../../scripts/security/tls-cert-check.sh" \
  -n "$NAMESPACE" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "  OK"

# Step 2: Apply TLS cert monitor CronJob
echo "[2/4] Applying TLS cert monitor CronJob..."
kubectl apply -f "$SCRIPT_DIR/tls-cert-monitor-cronjob.yaml"
echo "  OK"

# Step 3: Apply RBAC (for kubescape, added in PR 3)
if [ -f "$SCRIPT_DIR/rbac.yaml" ]; then
  echo "[3/4] Applying RBAC..."
  kubectl apply -f "$SCRIPT_DIR/rbac.yaml"
  echo "  OK"
else
  echo "[3/4] Skipping RBAC (rbac.yaml not found — added in PR 3)"
fi

# Step 4: Apply kubescape CronJob (added in PR 3)
if [ -f "$SCRIPT_DIR/kubescape-cronjob.yaml" ]; then
  echo "[4/4] Applying kubescape CronJob..."
  kubectl apply -f "$SCRIPT_DIR/kubescape-cronjob.yaml"
  echo "  OK"
else
  echo "[4/4] Skipping kubescape CronJob (added in PR 3)"
fi

echo ""
echo "=== Smoke Test ==="
echo "Creating one-off TLS cert check job..."
kubectl create job --from=cronjob/tls-cert-monitor tls-smoke-test-"$(date +%s)" \
  -n "$NAMESPACE" 2>/dev/null && echo "  Job created" || echo "  Job creation skipped (may already exist)"

echo ""
echo "=== Status ==="
kubectl get cronjob -n "$NAMESPACE" -l component=security 2>/dev/null || echo "No security CronJobs found yet"
echo ""
echo "Deploy complete. Check logs with:"
echo "  kubectl logs -n $NAMESPACE -l app=tls-cert-monitor --tail=50"
