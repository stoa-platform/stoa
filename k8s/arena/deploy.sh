#!/usr/bin/env bash
# Gateway Arena — Idempotent deploy to OVH K8s
# Usage: KUBECONFIG=~/.kube/config-stoa-ovh ./k8s/arena/deploy.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Gateway Arena Deploy ==="

# 1. Pushgateway (Deployment + Service)
echo "[1/5] Applying Pushgateway..."
kubectl apply -f "$SCRIPT_DIR/pushgateway.yaml"

# 2. ConfigMap from arena script
echo "[2/5] Creating ConfigMap from gateway-arena.py..."
kubectl create configmap gateway-arena-script \
  --from-file="$REPO_ROOT/scripts/traffic/gateway-arena.py" \
  -n stoa-system \
  --dry-run=client -o yaml | kubectl apply -f -

# 3. ServiceMonitor for Prometheus auto-discovery
echo "[3/5] Applying ServiceMonitor..."
kubectl apply -f "$SCRIPT_DIR/pushgateway-servicemonitor.yaml"

# 4. CronJob
echo "[4/5] Applying CronJob..."
kubectl apply -f "$SCRIPT_DIR/cronjob-prod.yaml"

# 5. Smoke test — trigger one-off run
JOB_NAME="arena-smoke-$(date +%s)"
echo "[5/5] Triggering smoke test job: $JOB_NAME"
kubectl create job --from=cronjob/gateway-arena "$JOB_NAME" -n stoa-system

echo ""
echo "Waiting for job to complete (timeout 5m)..."
if kubectl wait --for=condition=complete "job/$JOB_NAME" -n stoa-system --timeout=300s 2>/dev/null; then
  echo ""
  echo "=== Smoke Test Logs ==="
  kubectl logs -n stoa-system "job/$JOB_NAME" --tail=30
  echo ""
  echo "=== Verification ==="
  echo "Pushgateway pod:"
  kubectl get pods -n monitoring -l app=pushgateway
  echo ""
  echo "ServiceMonitor:"
  kubectl get servicemonitor -n monitoring pushgateway
  echo ""
  echo "CronJob:"
  kubectl get cronjob -n stoa-system gateway-arena
  echo ""
  echo "Deploy complete. Next steps:"
  echo "  1. Import Grafana dashboard: console.gostoa.dev/grafana -> Import -> paste docker/observability/grafana/dashboards/gateway-arena.json"
  echo "  2. Verify Prometheus targets include pushgateway"
  echo "  3. Clean up smoke job: kubectl delete job $JOB_NAME -n stoa-system"
else
  echo "Job did not complete in 5m. Check logs:"
  echo "  kubectl logs -n stoa-system job/$JOB_NAME"
fi
