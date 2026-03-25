#!/usr/bin/env bash
# Bootstrap gateway routes for the traffic seeder (CAB-1869).
#
# Registers all edge-mcp API routes in stoa-gateway's in-memory RouteRegistry
# via the admin API (POST /admin/apis). Routes are volatile — they reset on
# gateway restart, so this script should run after every gateway deploy.
#
# Usage:
#   # From kubectl context with access to stoa-system namespace
#   KUBECONFIG=~/.kube/config-stoa-ovh ./scripts/traffic/bootstrap-routes.sh
#
#   # With explicit admin token (skip auto-detection from deployment)
#   ADMIN_TOKEN=secret ./scripts/traffic/bootstrap-routes.sh
#
#   # Dry run — print curl commands without executing
#   DRY_RUN=1 ./scripts/traffic/bootstrap-routes.sh
set -euo pipefail

NAMESPACE="${NAMESPACE:-stoa-system}"
GATEWAY_POD_LABEL="${GATEWAY_POD_LABEL:-app=stoa-gateway}"
ADMIN_PORT="${ADMIN_PORT:-8080}"

# --- Resolve admin token ---
if [ -z "${ADMIN_TOKEN:-}" ]; then
  echo "Detecting STOA_ADMIN_API_TOKEN from gateway deployment..."
  ADMIN_TOKEN=$(kubectl get deploy stoa-gateway -n "$NAMESPACE" \
    -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="STOA_ADMIN_API_TOKEN")].value}' 2>/dev/null || true)
  if [ -z "$ADMIN_TOKEN" ]; then
    echo "ERROR: Could not read STOA_ADMIN_API_TOKEN from deployment."
    echo "Set ADMIN_TOKEN env var or configure the gateway deployment."
    exit 1
  fi
  echo "  Token detected (${#ADMIN_TOKEN} chars)"
fi

# --- Route definitions ---
# Format: id|name|tenant_id|path_prefix|backend_url|methods_json|spec_hash
#
# Path matching: gateway uses longest-prefix match. The seeder sends
# requests to {base_url}{url_path}, so path_prefix must match url_path
# from scenarios.py and backend_url must reconstruct the correct upstream.
#
# Formula: target = backend_url + path.strip_prefix(path_prefix) + query_string

ROUTES=(
  # --- Tier 1: No Auth ---
  # echo-fallback: url_path="/" → catch-all fallback
  'd1a1b1c1-0006-4000-a000-000000000006|echo-fallback|demo|/|http://echo-backend.stoa-system.svc:8888|[]|seed-074'

  # exchange-rate: url_path="/v4/latest/EUR"
  # path_prefix=/v4 → remaining=/latest/EUR → backend: .../v4/latest/EUR ✓
  'd1a1b1c1-0001-4000-a000-000000000001|exchange-rate|demo|/v4|https://api.exchangerate-api.com/v4|["GET"]|seed-074'

  # --- Tier 2: API Key ---
  # openweathermap: url_path="/weather" + query params
  'd1a1b1c1-0003-4000-a000-000000000003|openweathermap|demo|/weather|https://api.openweathermap.org/data/2.5/weather|["GET"]|seed-074'

  # newsapi: url_path="/top-headlines" + query params
  'd1a1b1c1-0004-4000-a000-000000000004|newsapi|demo|/top-headlines|https://newsapi.org/v2/top-headlines|["GET"]|seed-074'

  # --- Tier 3: OAuth2 ---
  # echo-oauth2: url_path="/" — same path as echo-fallback, same backend.
  # Longest-prefix match means "/" catches both. Separate route for traceability.
  # Using /oauth2-echo prefix + updating seeder url_path is the clean fix,
  # but for now the echo-fallback route at "/" covers this.
  'd1a1b1c1-0009-4000-a000-000000000009|echo-oauth2|demo|/oauth2|http://echo-backend.stoa-system.svc:8888|["GET","POST"]|seed-075'

  # --- Tier 4: FAPI Banking ---
  # fapi-accounts: url_path="/api/v1/accounts"
  # Uses echo-backend until fapi-echo VPS is network-reachable from K8s
  'd1a1b1c1-0011-4000-a000-000000000011|fapi-accounts|demo|/api/v1/accounts|http://echo-backend.stoa-system.svc:8888/api/v1/accounts|["GET"]|seed-075'

  # fapi-transfers: url_path="/api/v1/transfers"
  'd1a1b1c1-0012-4000-a000-000000000012|fapi-transfers|demo|/api/v1/transfers|http://echo-backend.stoa-system.svc:8888/api/v1/transfers|["GET","POST"]|seed-075'
)

# --- Register routes ---
OK=0
FAIL=0
TOTAL=${#ROUTES[@]}

echo ""
echo "=== Registering $TOTAL routes on stoa-gateway ==="
echo ""

for entry in "${ROUTES[@]}"; do
  IFS='|' read -r id name tenant_id path_prefix backend_url methods spec_hash <<< "$entry"

  payload=$(cat <<ENDJSON
{"id":"$id","name":"$name","tenant_id":"$tenant_id","path_prefix":"$path_prefix","backend_url":"$backend_url","methods":$methods,"spec_hash":"$spec_hash","activated":true}
ENDJSON
)

  if [ "${DRY_RUN:-0}" = "1" ]; then
    echo "[DRY-RUN] $name → $path_prefix → $backend_url"
    OK=$((OK + 1))
    continue
  fi

  # Use kubectl exec to call the admin API from inside the cluster
  if kubectl exec -n "$NAMESPACE" deploy/stoa-gateway -- \
    curl -sf -X POST "http://localhost:$ADMIN_PORT/admin/apis" \
      -H "Authorization: Bearer $ADMIN_TOKEN" \
      -H "Content-Type: application/json" \
      -d "$payload" > /dev/null 2>&1; then
    echo "  ✓ $name → $path_prefix → $backend_url"
    OK=$((OK + 1))
  else
    echo "  ✗ $name FAILED (may already exist or backend unreachable)"
    FAIL=$((FAIL + 1))
  fi
done

echo ""
echo "=== Done: $OK/$TOTAL routes registered ($FAIL failed) ==="

# --- Verify ---
if [ "${DRY_RUN:-0}" != "1" ]; then
  echo ""
  echo "Verifying route count..."
  ROUTE_COUNT=$(kubectl exec -n "$NAMESPACE" deploy/stoa-gateway -- \
    curl -sf "http://localhost:$ADMIN_PORT/admin/apis" \
      -H "Authorization: Bearer $ADMIN_TOKEN" 2>/dev/null \
    | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "?")
  echo "  Gateway has $ROUTE_COUNT active routes"
fi
