#!/usr/bin/env bash
# Gateway Arena — Idempotent deploy to OVH K8s
# Usage: KUBECONFIG=~/.kube/config-stoa-ovh ./k8s/arena/deploy.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Gateway Arena Deploy ==="

# 1. Echo backend (nginx returning static JSON — same as VPS echo)
echo "[1/7] Applying echo backend..."
kubectl apply -f "$SCRIPT_DIR/echo-backend.yaml"
kubectl rollout status deploy/echo-backend -n stoa-system --timeout=60s

# 2. Register echo route on K8s gateway
echo "[2/7] Registering echo route on K8s STOA gateway..."
ADMIN_TOKEN=$(kubectl get deploy stoa-gateway -n stoa-system -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="STOA_ADMIN_API_TOKEN")].value}')
if [ -n "$ADMIN_TOKEN" ]; then
  # Register via any gateway pod
  kubectl exec -n stoa-system deploy/stoa-gateway -- \
    curl -sf -X POST http://localhost:8080/admin/apis \
      -H "Authorization: Bearer $ADMIN_TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"id":"arena-echo","name":"arena-echo","path_prefix":"/echo","backend_url":"http://echo-backend.stoa-system.svc:8888","methods":[],"activated":true}' \
    || echo "  (route may already exist — continuing)"
  echo ""
else
  echo "  WARNING: Could not read STOA_ADMIN_API_TOKEN from deployment. Register echo route manually."
fi

# 3. Pushgateway (Deployment + Service)
echo "[3/7] Applying Pushgateway..."
kubectl apply -f "$SCRIPT_DIR/pushgateway.yaml"

# 4. ConfigMap from arena script
echo "[4/7] Creating ConfigMap from gateway-arena.py..."
kubectl create configmap gateway-arena-script \
  --from-file="$REPO_ROOT/scripts/traffic/gateway-arena.py" \
  -n stoa-system \
  --dry-run=client -o yaml | kubectl apply -f -

# 5. ServiceMonitor for Prometheus auto-discovery
echo "[5/7] Applying ServiceMonitor..."
kubectl apply -f "$SCRIPT_DIR/pushgateway-servicemonitor.yaml"

# 6. CronJob
echo "[6/7] Applying CronJob..."
kubectl apply -f "$SCRIPT_DIR/cronjob-prod.yaml"

# 7. Smoke test — trigger one-off run
JOB_NAME="arena-smoke-$(date +%s)"
echo "[7/7] Triggering smoke test job: $JOB_NAME"
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
