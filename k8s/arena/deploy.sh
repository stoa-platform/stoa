#!/usr/bin/env bash
# Gateway Arena — Idempotent deploy to OVH K8s
# Usage: KUBECONFIG=~/.kube/config-stoa-ovh ./k8s/arena/deploy.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TOTAL=9

echo "=== Gateway Arena Deploy (6 gateways: 3 K8s + 3 VPS) ==="

# 1. Echo backend (nginx returning static JSON — same as VPS echo)
echo "[1/$TOTAL] Applying echo backend..."
kubectl apply -f "$SCRIPT_DIR/echo-backend.yaml"
kubectl rollout status deploy/echo-backend -n stoa-system --timeout=60s

# 2. Register echo route on K8s STOA gateway
echo "[2/$TOTAL] Registering echo route on K8s STOA gateway..."
ADMIN_TOKEN=$(kubectl get deploy stoa-gateway -n stoa-system -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="STOA_ADMIN_API_TOKEN")].value}')
if [ -n "$ADMIN_TOKEN" ]; then
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

# 3. Kong DB-less (declarative config with echo route pre-configured)
echo "[3/$TOTAL] Applying Kong Arena (DB-less)..."
kubectl apply -f "$SCRIPT_DIR/kong.yaml"
kubectl rollout status deploy/kong-arena -n stoa-system --timeout=120s
echo "  Verifying Kong echo route..."
kubectl exec -n stoa-system deploy/kong-arena -- \
  curl -sf -o /dev/null -w "  Kong proxy echo: HTTP %{http_code}\n" http://localhost:8000/echo/get \
  || echo "  WARNING: Kong echo route not ready yet"

# 4. Gravitee APIM (MongoDB + Mgmt API + Gateway)
echo "[4/$TOTAL] Applying Gravitee Arena stack..."
kubectl apply -f "$SCRIPT_DIR/gravitee.yaml"
echo "  Waiting for MongoDB..."
kubectl rollout status deploy/gravitee-arena-mongo -n stoa-system --timeout=120s
echo "  Waiting for Management API..."
kubectl rollout status deploy/gravitee-arena-mgmt -n stoa-system --timeout=180s
echo "  Waiting for Gateway..."
kubectl rollout status deploy/gravitee-arena-gw -n stoa-system --timeout=180s

# 5. Gravitee echo route init job
echo "[5/$TOTAL] Running Gravitee echo route init job..."
# Delete previous job if it exists (jobs are immutable)
kubectl delete job gravitee-arena-init -n stoa-system --ignore-not-found
kubectl apply -f "$SCRIPT_DIR/gravitee.yaml"
echo "  Waiting for init job to complete..."
if kubectl wait --for=condition=complete job/gravitee-arena-init -n stoa-system --timeout=300s 2>/dev/null; then
  echo "  Gravitee echo route registered"
  kubectl logs -n stoa-system job/gravitee-arena-init --tail=10
else
  echo "  WARNING: Gravitee init job did not complete. Check logs:"
  echo "    kubectl logs -n stoa-system job/gravitee-arena-init"
fi

# 6. Pushgateway (Deployment + Service)
echo "[6/$TOTAL] Applying Pushgateway..."
kubectl apply -f "$SCRIPT_DIR/pushgateway.yaml"

# 7. ConfigMap from k6 arena scripts
echo "[7/$TOTAL] Creating ConfigMap from k6 arena scripts..."
kubectl create configmap gateway-arena-scripts \
  --from-file="$REPO_ROOT/scripts/traffic/arena/benchmark.js" \
  --from-file="$REPO_ROOT/scripts/traffic/arena/run-arena.sh" \
  -n stoa-system \
  --dry-run=client -o yaml | kubectl apply -f -
# Clean up old ConfigMap if it exists
kubectl delete configmap gateway-arena-script -n stoa-system --ignore-not-found

# 8. ServiceMonitor + CronJob
echo "[8/$TOTAL] Applying ServiceMonitor + CronJob..."
kubectl apply -f "$SCRIPT_DIR/pushgateway-servicemonitor.yaml"
kubectl apply -f "$SCRIPT_DIR/cronjob-prod.yaml"

# 9. Smoke test — trigger one-off run
JOB_NAME="arena-smoke-$(date +%s)"
echo "[9/$TOTAL] Triggering smoke test job: $JOB_NAME"
kubectl create job --from=cronjob/gateway-arena "$JOB_NAME" -n stoa-system

echo ""
echo "Waiting for job to complete (timeout 10m)..."
if kubectl wait --for=condition=complete "job/$JOB_NAME" -n stoa-system --timeout=600s 2>/dev/null; then
  echo ""
  echo "=== Smoke Test Logs ==="
  kubectl logs -n stoa-system "job/$JOB_NAME" --tail=50
  echo ""
  echo "=== Verification ==="
  echo "Arena pods:"
  kubectl get pods -n stoa-system -l 'app in (echo-backend,kong-arena,gravitee-arena-mongo,gravitee-arena-mgmt,gravitee-arena-gw)'
  echo ""
  echo "Pushgateway pod:"
  kubectl get pods -n monitoring -l app=pushgateway
  echo ""
  echo "CronJob:"
  kubectl get cronjob -n stoa-system gateway-arena
  echo ""
  echo "Deploy complete. Next steps:"
  echo "  1. Verify 6 gateway scores in Pushgateway: curl http://pushgateway.monitoring.svc:9091/metrics"
  echo "  2. Check Grafana dashboard for 6-gateway leaderboard"
  echo "  3. Clean up smoke job: kubectl delete job $JOB_NAME -n stoa-system"
else
  echo "Job did not complete in 10m. Check logs:"
  echo "  kubectl logs -n stoa-system job/$JOB_NAME"
fi
