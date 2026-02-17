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
echo "[1/5] Creating ConfigMap 'security-scripts'..."
kubectl create configmap security-scripts \
  --from-file="$SCRIPT_DIR/../../scripts/security/tls-cert-check.sh" \
  --from-file="$SCRIPT_DIR/../../scripts/security/kubescape-report.sh" \
  -n "$NAMESPACE" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "  OK"

# Step 2: Apply RBAC (kubescape needs read-only cluster access)
echo "[2/5] Applying RBAC..."
kubectl apply -f "$SCRIPT_DIR/rbac.yaml"
echo "  OK"

# Step 3: Apply TLS cert monitor CronJob
echo "[3/5] Applying TLS cert monitor CronJob..."
kubectl apply -f "$SCRIPT_DIR/tls-cert-monitor-cronjob.yaml"
echo "  OK"

# Step 4: Apply kubescape CronJob
echo "[4/5] Applying kubescape CronJob..."
kubectl apply -f "$SCRIPT_DIR/kubescape-cronjob.yaml"
echo "  OK"

# Step 5: Smoke test — run TLS check immediately
echo "[5/5] Smoke test — creating one-off TLS cert check job..."
kubectl create job --from=cronjob/tls-cert-monitor tls-smoke-"$(date +%s)" \
  -n "$NAMESPACE" 2>/dev/null && echo "  Job created" || echo "  Job creation skipped (may already exist)"

echo ""
echo "=== Status ==="
kubectl get cronjob -n "$NAMESPACE" -l component=security
echo ""
echo "Deploy complete. Check logs with:"
echo "  kubectl logs -n $NAMESPACE -l app=tls-cert-monitor --tail=50"
echo "  kubectl logs -n $NAMESPACE -l app=kubescape-benchmark --tail=50"
