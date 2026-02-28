#!/usr/bin/env bash
# Gateway Arena Enterprise — Standalone deploy for Layer 1 benchmark
# Usage: KUBECONFIG=~/.kube/config-stoa-ovh ./k8s/arena/deploy-enterprise.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OPENSEARCH_URL="${OPENSEARCH_URL:-http://opensearch.stoa-system.svc:9200}"
TOTAL=8

echo "=== Gateway Arena Enterprise Deploy (Layer 1: AI Readiness) ==="

# 1. Bootstrap OpenSearch index template
echo "[1/$TOTAL] Applying OpenSearch index template (stoa-bench-*)..."
kubectl exec -n stoa-system deploy/opensearch -- \
  curl -s -XPUT "${OPENSEARCH_URL}/_index_template/stoa-bench" \
  -H "Content-Type: application/json" \
  -d "$(cat "$SCRIPT_DIR/opensearch-index-template.json")" 2>/dev/null \
  || echo "  (OpenSearch not reachable in-cluster, apply template manually)"

# 2. Apply ISM lifecycle policy
echo "[2/$TOTAL] Applying ISM lifecycle policy (stoa-bench-lifecycle)..."
kubectl exec -n stoa-system deploy/opensearch -- \
  curl -s -XPUT "${OPENSEARCH_URL}/_plugins/_ism/policies/stoa-bench-lifecycle" \
  -H "Content-Type: application/json" \
  -d "$(cat "$SCRIPT_DIR/opensearch-ism-policy.json")" 2>/dev/null \
  || echo "  (OpenSearch ISM not reachable, apply policy manually)"

# 3. Update ConfigMap with all arena scripts (baseline + enterprise)
echo "[3/$TOTAL] Updating ConfigMap with enterprise scripts..."
kubectl create configmap gateway-arena-scripts \
  --from-file="$REPO_ROOT/scripts/traffic/arena/benchmark.js" \
  --from-file="$REPO_ROOT/scripts/traffic/arena/run-arena.sh" \
  --from-file="$REPO_ROOT/scripts/traffic/arena/run-arena.py" \
  --from-file="$REPO_ROOT/scripts/traffic/arena/benchmark-enterprise.js" \
  --from-file="$REPO_ROOT/scripts/traffic/arena/run-arena-enterprise.sh" \
  --from-file="$REPO_ROOT/scripts/traffic/arena/run-arena-enterprise.py" \
  -n stoa-system \
  --dry-run=client -o yaml | kubectl apply -f -

# 4. Apply LLM mock backend (dim 9)
echo "[4/$TOTAL] Applying LLM mock backend..."
if [ -f "$SCRIPT_DIR/llm-mock-backend.yaml" ]; then
  kubectl apply -f "$SCRIPT_DIR/llm-mock-backend.yaml"
else
  echo "  (llm-mock-backend.yaml not found, skipping)"
fi

# 5. Import OpenSearch Dashboards saved objects
echo "[5/$TOTAL] Importing OpenSearch Dashboards visualizations..."
OSD_FILE="$REPO_ROOT/docker/observability/opensearch-dashboards/saved-objects/stoa-bench-dashboards.ndjson"
if [ -f "$OSD_FILE" ]; then
  kubectl exec -n stoa-system deploy/opensearch-dashboards -- \
    curl -s -XPOST "http://localhost:5601/api/saved_objects/_import?overwrite=true" \
    -H "osd-xsrf: true" \
    --form file=@- < "$OSD_FILE" 2>/dev/null \
    || echo "  (OpenSearch Dashboards not reachable, import manually via UI: Stack Management > Saved Objects > Import)"
else
  echo "  (saved objects file not found, skipping)"
fi

# 6. Apply enterprise CronJob
echo "[6/$TOTAL] Applying enterprise CronJob..."
kubectl apply -f "$SCRIPT_DIR/cronjob-enterprise.yaml"

# 7. Verify CronJob created
echo "[7/$TOTAL] Verifying CronJob..."
kubectl get cronjob gateway-arena-enterprise -n stoa-system

# 8. Smoke test — trigger manual run
JOB_NAME="arena-ent-smoke-$(date +%s)"
echo "[8/$TOTAL] Triggering smoke test: $JOB_NAME"
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
  echo "  2. Import Grafana dashboard: docker/observability/grafana/dashboards/gateway-arena-historical.json"
  echo "  3. OpenSearch Dashboards: stoa-bench-dashboards.ndjson (auto-imported in step 5)"
  echo "  4. Cleanup: kubectl delete job $JOB_NAME -n stoa-system"
else
  echo "Job did not complete in 15m. Check logs:"
  echo "  kubectl logs -n stoa-system job/$JOB_NAME"
fi
