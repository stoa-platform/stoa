#!/usr/bin/env bash
# Deploy traffic seeder infrastructure (CAB-1869).
#
# Steps:
#   1. Apply fapi-echo Service (headless → VPS worker-3)
#   2. Register gateway routes (edge-mcp)
#   3. Unsuspend the traffic-seeder CronJob
#
# Usage:
#   KUBECONFIG=~/.kube/config-stoa-ovh ./k8s/traffic/deploy-seeder.sh
#
# Prerequisites:
#   - echo-backend deployed (k8s/arena/echo-backend.yaml)
#   - fapi-echo running on worker-3 (see VPS inventory for IP)
#   - traffic-seeder-credentials Secret exists
#   - Migration 074 + 075 applied
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
NAMESPACE="${NAMESPACE:-stoa-system}"
TOTAL=5

echo "=== Traffic Seeder Deploy ==="

# 1. fapi-echo headless Service → VPS
echo "[1/$TOTAL] Applying fapi-echo Service (headless → worker-3)..."
kubectl apply -f "$SCRIPT_DIR/fapi-echo-service.yaml"
echo "  Verifying DNS resolution..."
kubectl run dns-check --rm -it --restart=Never --image=busybox:1.36 -n "$NAMESPACE" \
  -- nslookup fapi-echo.stoa-system.svc.cluster.local 2>/dev/null \
  | grep -q "Address" \
  && echo "  ✓ fapi-echo.stoa-system.svc resolved" \
  || echo "  ⚠ DNS check skipped (non-interactive)"

# 2. Register gateway routes
echo ""
echo "[2/$TOTAL] Registering gateway routes..."
bash "$REPO_ROOT/scripts/traffic/bootstrap-routes.sh"

# 3. Verify echo-backend is running
echo ""
echo "[3/$TOTAL] Verifying echo-backend..."
kubectl get deploy echo-backend -n "$NAMESPACE" -o wide 2>/dev/null \
  && echo "  ✓ echo-backend running" \
  || echo "  ⚠ echo-backend not found — run: kubectl apply -f k8s/arena/echo-backend.yaml"

# 4. Verify credentials Secret
echo ""
echo "[4/$TOTAL] Verifying traffic-seeder-credentials Secret..."
kubectl get secret traffic-seeder-credentials -n "$NAMESPACE" -o name 2>/dev/null \
  && echo "  ✓ Secret exists" \
  || echo "  ⚠ Secret missing — create it first"

# 5. Unsuspend CronJob
echo ""
echo "[5/$TOTAL] Unsuspending traffic-seeder CronJob..."
kubectl patch cronjob traffic-seeder -n "$NAMESPACE" \
  -p '{"spec":{"suspend":false}}' 2>/dev/null \
  && echo "  ✓ CronJob unsuspended — will run at next */10 minute mark" \
  || echo "  ⚠ CronJob not found — apply: kubectl apply -f k8s/traffic/cronjob-seeder.yaml"

echo ""
echo "=== Deploy complete ==="
echo ""
echo "Next steps:"
echo "  - Watch first run: kubectl logs -n $NAMESPACE -l app=traffic-seeder -f"
echo "  - Trigger immediately: kubectl create job seeder-test --from=cronjob/traffic-seeder -n $NAMESPACE"
echo "  - Check gateway routes: kubectl exec -n $NAMESPACE deploy/stoa-gateway -- curl -s http://localhost:8080/admin/health"
