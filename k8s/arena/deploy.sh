#!/usr/bin/env bash
# Gateway Arena — Idempotent deploy to OVH K8s
# Usage: KUBECONFIG=~/.kube/config-stoa-ovh ./k8s/arena/deploy.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TOTAL=10

echo "=== Gateway Arena Deploy (4 K8s gateways: STOA prod + STOA minimal + Kong + AgentGateway) ==="

# 1. Echo backend (nginx returning static JSON — same as VPS echo)
echo "[1/$TOTAL] Applying echo backend..."
kubectl apply -f "$SCRIPT_DIR/echo-backend.yaml"
kubectl rollout status deploy/echo-backend -n stoa-system --timeout=60s

# 2. Register echo route on K8s STOA gateway (production instance)
echo "[2/$TOTAL] Registering echo route on K8s STOA gateway..."
ADMIN_TOKEN=$(kubectl get deploy stoa-gateway -n stoa-system -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="STOA_ADMIN_API_TOKEN")].value}')
if [ -n "$ADMIN_TOKEN" ]; then
  kubectl exec -n stoa-system deploy/stoa-gateway -- \
    curl -sf -X POST http://localhost:8080/admin/apis \
      -H "Authorization: Bearer $ADMIN_TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"id":"arena-echo","name":"arena-echo","tenant_id":"arena","path_prefix":"/echo","backend_url":"http://echo-backend.stoa-system.svc:8888","methods":[],"spec_hash":"arena-echo","activated":true}' \
    || echo "  (route may already exist — continuing)"
  echo ""
else
  echo "  WARNING: Could not read STOA_ADMIN_API_TOKEN from deployment. Register echo route manually."
fi

# 3. STOA Gateway — Minimal mode (all features disabled, pure Rust proxy)
echo "[3/$TOTAL] Applying STOA Gateway Minimal..."
kubectl apply -f "$SCRIPT_DIR/stoa-minimal.yaml"
kubectl rollout status deploy/stoa-gateway-minimal -n stoa-system --timeout=120s
echo "  Registering echo route on STOA Minimal..."
MINIMAL_TOKEN=$(kubectl get secret stoa-gateway-secrets -n stoa-system -o jsonpath='{.data.STOA_ADMIN_API_TOKEN}' 2>/dev/null | base64 -d 2>/dev/null || echo "")
if [ -n "$MINIMAL_TOKEN" ]; then
  kubectl exec -n stoa-system deploy/stoa-gateway-minimal -- \
    curl -sf -X POST http://localhost:8080/admin/apis \
      -H "Authorization: Bearer $MINIMAL_TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"id":"arena-echo","name":"arena-echo","tenant_id":"arena","path_prefix":"/echo","backend_url":"http://echo-backend.stoa-system.svc:8888","methods":[],"spec_hash":"arena-echo","activated":true}' \
    || echo "  (route may already exist — continuing)"
  echo ""
else
  echo "  WARNING: Could not read admin token for STOA Minimal. Register echo route manually."
fi

# 4. Kong DB-less (declarative config with echo route pre-configured)
echo "[4/$TOTAL] Applying Kong Arena (DB-less)..."
kubectl apply -f "$SCRIPT_DIR/kong.yaml"
kubectl rollout status deploy/kong-arena -n stoa-system --timeout=120s
echo "  Verifying Kong echo route..."
kubectl exec -n stoa-system deploy/kong-arena -- \
  curl -sf -o /dev/null -w "  Kong proxy echo: HTTP %{http_code}\n" http://localhost:8000/echo/get \
  || echo "  WARNING: Kong echo route not ready yet"

# 5. agentgateway (Linux Foundation / Solo.io — MCP-native, alpha)
echo "[5/$TOTAL] Applying agentgateway Arena..."
kubectl apply -f "$SCRIPT_DIR/agentgateway.yaml"
kubectl rollout status deploy/agentgateway-arena -n stoa-system --timeout=120s
echo "  Verifying agentgateway health..."
kubectl exec -n stoa-system deploy/agentgateway-arena -- \
  curl -sf -o /dev/null -w "  agentgateway health: HTTP %{http_code}\n" http://localhost:3000/health \
  || echo "  WARNING: agentgateway health not ready yet"

# 6. Pushgateway (Deployment + Service + Ingress)
echo "[6/$TOTAL] Applying Pushgateway..."
kubectl apply -f "$SCRIPT_DIR/pushgateway.yaml"
kubectl apply -f "$SCRIPT_DIR/pushgateway-ingress.yaml"

# 7. ConfigMap from k6 arena scripts
echo "[7/$TOTAL] Creating ConfigMap from k6 arena scripts (baseline + enterprise + verify)..."
kubectl create configmap gateway-arena-scripts \
  --from-file="$REPO_ROOT/scripts/traffic/arena/benchmark.js" \
  --from-file="$REPO_ROOT/scripts/traffic/arena/run-arena.sh" \
  --from-file="$REPO_ROOT/scripts/traffic/arena/run-arena.py" \
  --from-file="$REPO_ROOT/scripts/traffic/arena/benchmark-enterprise.js" \
  --from-file="$REPO_ROOT/scripts/traffic/arena/run-arena-enterprise.sh" \
  --from-file="$REPO_ROOT/scripts/traffic/arena/run-arena-enterprise.py" \
  --from-file="$REPO_ROOT/scripts/traffic/arena/run-arena-verify.sh" \
  -n stoa-system \
  --dry-run=client -o yaml | kubectl apply -f -
# Clean up old ConfigMap if it exists
kubectl delete configmap gateway-arena-script -n stoa-system --ignore-not-found

# 8. ServiceMonitor + CronJobs (baseline + enterprise + verify)
echo "[8/$TOTAL] Applying ServiceMonitor + CronJobs..."
kubectl apply -f "$SCRIPT_DIR/pushgateway-servicemonitor.yaml"
kubectl apply -f "$SCRIPT_DIR/cronjob-prod.yaml"
kubectl apply -f "$SCRIPT_DIR/cronjob-enterprise.yaml"
kubectl apply -f "$SCRIPT_DIR/cronjob-verify.yaml"

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
  kubectl get pods -n stoa-system -l 'app in (echo-backend,stoa-gateway-minimal,kong-arena,agentgateway-arena)'
  echo ""
  echo "Pushgateway pod:"
  kubectl get pods -n monitoring -l app=pushgateway
  echo ""
  echo "CronJob:"
  kubectl get cronjob -n stoa-system gateway-arena
  echo ""
  # 10. Enterprise smoke test
  echo "[10/$TOTAL] Triggering enterprise smoke test..."
  ENT_JOB_NAME="arena-ent-smoke-$(date +%s)"
  kubectl create job --from=cronjob/gateway-arena-enterprise "$ENT_JOB_NAME" -n stoa-system
  echo "  Enterprise job created: $ENT_JOB_NAME (runs in background)"
  echo ""
  echo "Deploy complete. Next steps:"
  echo "  1. Verify baseline scores: kubectl exec -n monitoring deploy/pushgateway -- wget -qO- localhost:9091/metrics | grep gateway_arena_score"
  echo "  2. Verify enterprise scores: kubectl exec -n monitoring deploy/pushgateway -- wget -qO- localhost:9091/metrics | grep enterprise"
  echo "  3. Deploy VPS sidecars: ./deploy/vps/bench/deploy.sh"
  echo "  4. Check Grafana dashboards for leaderboard"
  echo "  5. Clean up: kubectl delete job $JOB_NAME $ENT_JOB_NAME -n stoa-system"
  echo ""
  echo "NOTE: Gravitee removed from arena. To clean up old Gravitee pods:"
  echo "  kubectl delete deploy gravitee-arena-mongo gravitee-arena-mgmt gravitee-arena-gw -n stoa-system --ignore-not-found"
  echo "  kubectl delete job gravitee-arena-init -n stoa-system --ignore-not-found"
else
  echo "Job did not complete in 10m. Check logs:"
  echo "  kubectl logs -n stoa-system job/$JOB_NAME"
fi
