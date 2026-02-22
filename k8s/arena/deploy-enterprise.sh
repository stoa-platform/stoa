#!/usr/bin/env bash
# Gateway Arena Enterprise — Standalone deploy for Layer 1 benchmark
# Usage: KUBECONFIG=~/.kube/config-stoa-ovh ./k8s/arena/deploy-enterprise.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TOTAL=4

echo "=== Gateway Arena Enterprise Deploy (Layer 1: AI Readiness) ==="

# 1. Update ConfigMap with all arena scripts (baseline + enterprise)
echo "[1/$TOTAL] Updating ConfigMap with enterprise scripts..."
kubectl create configmap gateway-arena-scripts \
  --from-file="$REPO_ROOT/scripts/traffic/arena/benchmark.js" \
  --from-file="$REPO_ROOT/scripts/traffic/arena/run-arena.sh" \
  --from-file="$REPO_ROOT/scripts/traffic/arena/run-arena.py" \
  --from-file="$REPO_ROOT/scripts/traffic/arena/benchmark-enterprise.js" \
  --from-file="$REPO_ROOT/scripts/traffic/arena/run-arena-enterprise.sh" \
  --from-file="$REPO_ROOT/scripts/traffic/arena/run-arena-enterprise.py" \
  -n stoa-system \
  --dry-run=client -o yaml | kubectl apply -f -

# 2. Apply enterprise CronJob
echo "[2/$TOTAL] Applying enterprise CronJob..."
kubectl apply -f "$SCRIPT_DIR/cronjob-enterprise.yaml"

# 3. Verify CronJob created
echo "[3/$TOTAL] Verifying CronJob..."
kubectl get cronjob gateway-arena-enterprise -n stoa-system

# 4. Smoke test — trigger manual run
JOB_NAME="arena-ent-smoke-$(date +%s)"
echo "[4/$TOTAL] Triggering smoke test: $JOB_NAME"
kubectl create job --from=cronjob/gateway-arena-enterprise "$JOB_NAME" -n stoa-system

echo ""
echo "Waiting for job to complete (timeout 15m)..."
if kubectl wait --for=condition=complete "job/$JOB_NAME" -n stoa-system --timeout=900s 2>/dev/null; then
  echo ""
  echo "=== Smoke Test Logs ==="
  kubectl logs -n stoa-system "job/$JOB_NAME" --tail=30
  echo ""
  echo "=== Verification ==="
  echo "CronJobs:"
  kubectl get cronjob -n stoa-system -l 'app in (gateway-arena,gateway-arena-enterprise)'
  echo ""
  echo "Deploy complete. Next steps:"
  echo "  1. Check Pushgateway: kubectl exec -n monitoring deploy/pushgateway -- wget -qO- localhost:9091/metrics | grep enterprise"
  echo "  2. Import Grafana dashboard: docker/observability/grafana/dashboards/gateway-arena-enterprise.json"
  echo "  3. Cleanup: kubectl delete job $JOB_NAME -n stoa-system"
else
  echo "Job did not complete in 15m. Check logs:"
  echo "  kubectl logs -n stoa-system job/$JOB_NAME"
fi
