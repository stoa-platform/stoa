#!/usr/bin/env bash
# Local traffic seed for Call Flow dashboard (CAB-1976).
#
# Generates sustained traffic to the local gateway so Tempo metrics-generator
# produces traces_service_graph_* metrics for Prometheus. Without traffic,
# the Call Flow dashboard shows "No data".
#
# Usage:
#   ./scripts/traffic/local-traffic-seed.sh              # run once (20 calls)
#   ./scripts/traffic/local-traffic-seed.sh --continuous  # every 30s until killed
#
# Prerequisites:
#   - Gateway running on localhost:8081 with STOA_ADMIN_API_TOKEN set
#   - Echo route registered (auto-registered if missing)

set -euo pipefail

GATEWAY_URL="${STOA_GATEWAY_URL:-http://localhost:8081}"
ADMIN_TOKEN="${STOA_ADMIN_API_TOKEN:-stoa-local-admin-token}"
CALLS_PER_BATCH=10
INTERVAL=30

# ─── Ensure echo route exists ────────────────────────────────────────

ensure_echo_route() {
  local count
  count=$(curl -s -H "Authorization: Bearer $ADMIN_TOKEN" "$GATEWAY_URL/admin/apis" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
  if [ "$count" = "0" ]; then
    echo "[seed] Registering echo route..."
    curl -s -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
      -H "Content-Type: application/json" \
      "$GATEWAY_URL/admin/apis" \
      -d '{
        "id": "echo-seed",
        "name": "Echo Seed",
        "tenant_id": "default",
        "path_prefix": "/echo",
        "backend_url": "http://host.docker.internal:8888",
        "methods": ["GET","POST"],
        "spec_hash": "seed",
        "activated": true,
        "trusted_backend": true
      }' > /dev/null 2>&1
    echo "[seed] Echo route registered"
  fi
}

# ─── Generate traffic batch ──────────────────────────────────────────

generate_batch() {
  local ok=0 fail=0
  for _ in $(seq 1 "$CALLS_PER_BATCH"); do
    # Proxy route (dynamic_proxy → pool_metrics)
    status=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY_URL/echo")
    [ "$status" = "200" ] && ok=$((ok+1)) || fail=$((fail+1))

    # MCP tool call (ToolSpan → Tempo traces)
    status=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
      -H "Content-Type: application/json" \
      "$GATEWAY_URL/mcp/tools/call" \
      -d '{"name":"stoa_platform_health","arguments":{}}')
    [ "$status" = "200" ] && ok=$((ok+1)) || fail=$((fail+1))
  done
  echo "[seed] $(date +%H:%M:%S) batch: ${ok} ok, ${fail} fail"
}

# ─── Main ────────────────────────────────────────────────────────────

ensure_echo_route
generate_batch

if [ "${1:-}" = "--continuous" ]; then
  echo "[seed] Continuous mode — Ctrl+C to stop"
  while true; do
    sleep "$INTERVAL"
    generate_batch
  done
fi
