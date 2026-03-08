#!/usr/bin/env bash
# STOA Bench — Deploy L2 CUJ CronJob + Grafana dashboards to OVH K8s
# Usage: KUBECONFIG=~/.kube/config-stoa-ovh ./k8s/arena/deploy-bench.sh
#
# Prerequisites:
#   - Docker image ghcr.io/stoa-platform/stoa-bench:0.1.0 pushed
#   - arena-verify-config secret exists with oidc-client-secret
#   - Pushgateway running in monitoring namespace
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BENCH_DIR="$REPO_ROOT/stoa-bench"
TOTAL=5

echo "=== STOA Bench Deploy (L2 CUJs + L3 Stability) ==="
echo ""

# 1. Verify prerequisites
echo "[$((1))/$TOTAL] Checking prerequisites..."
if ! kubectl get secret arena-verify-config -n stoa-system -o name >/dev/null 2>&1; then
  echo "  ERROR: arena-verify-config secret not found."
  echo "  Create it: kubectl create secret generic arena-verify-config -n stoa-system \\"
  echo "    --from-literal=oidc-client-secret=<SECRET> \\"
  echo "    --from-literal=healthchecks-url=<URL>"
  exit 1
fi
echo "  arena-verify-config: OK"

if ! kubectl get pods -n monitoring -l app=pushgateway -o name 2>/dev/null | grep -q pod; then
  echo "  WARNING: Pushgateway not found in monitoring namespace. Metrics push will fail."
else
  echo "  Pushgateway: OK"
fi

# 2. Apply CronJob
echo "[$((2))/$TOTAL] Applying L2 CUJ CronJob..."
kubectl apply -f "$SCRIPT_DIR/cronjob-l2-cuj.yaml"
echo "  CronJob stoa-bench-l2: applied (schedule: */15 * * * *)"

# 3. Provision Grafana dashboards via ConfigMap
echo "[$((3))/$TOTAL] Creating Grafana dashboard ConfigMaps..."
for dash in l2-cuj-status l3-stability demo-readiness; do
  DASH_FILE="$BENCH_DIR/dashboards/${dash}.json"
  if [ -f "$DASH_FILE" ]; then
    kubectl create configmap "grafana-dash-stoa-bench-${dash}" \
      --from-file="${dash}.json=${DASH_FILE}" \
      -n monitoring \
      --dry-run=client -o yaml | kubectl apply -f -
    # Label for Grafana sidecar auto-discovery
    kubectl label configmap "grafana-dash-stoa-bench-${dash}" \
      -n monitoring \
      grafana_dashboard=1 \
      --overwrite
    echo "  ${dash}: OK"
  else
    echo "  WARNING: ${DASH_FILE} not found, skipping"
  fi
done

# 4. Smoke test — trigger one-off L2 run
echo "[$((4))/$TOTAL] Triggering smoke test..."
JOB_NAME="bench-l2-smoke-$(date +%s)"
kubectl create job --from=cronjob/stoa-bench-l2 "$JOB_NAME" -n stoa-system

echo ""
echo "  Waiting for job $JOB_NAME to complete (timeout 10m)..."
if kubectl wait --for=condition=complete "job/$JOB_NAME" -n stoa-system --timeout=600s 2>/dev/null; then
  echo ""
  echo "=== Smoke Test Logs (last 30 lines) ==="
  kubectl logs -n stoa-system "job/$JOB_NAME" --tail=30
  echo ""
else
  echo ""
  echo "  Job did not complete in 10m. Check:"
  echo "    kubectl logs -n stoa-system job/$JOB_NAME"
  echo "    kubectl describe job/$JOB_NAME -n stoa-system"
fi

# 5. Verify
echo "[$((5))/$TOTAL] Verification..."
echo ""
echo "CronJobs:"
kubectl get cronjob -n stoa-system stoa-bench-l2 2>/dev/null || echo "  NOT FOUND"
echo ""
echo "Grafana dashboards:"
kubectl get configmap -n monitoring -l grafana_dashboard=1 | grep stoa-bench || echo "  none found"
echo ""
echo "Pushgateway metrics (L2):"
kubectl exec -n monitoring deploy/pushgateway -- wget -qO- localhost:9091/metrics 2>/dev/null \
  | grep -E "^stoa_bench_(demo_ready|l2_passed|l3_demo_confidence)" \
  || echo "  no stoa_bench metrics yet"
echo ""
echo "Deploy complete. Cleanup: kubectl delete job $JOB_NAME -n stoa-system"
