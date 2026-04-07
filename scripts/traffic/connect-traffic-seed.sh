#!/usr/bin/env bash
# Connect agent traffic seed — Kong (k3d) + webMethods (Docker).
# 2 instances × 5 operations (register, heartbeat, routes, ack, discovery).
#
# Usage:
#   ./scripts/traffic/connect-traffic-seed.sh
#   ./scripts/traffic/connect-traffic-seed.sh --continuous

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/seed-common.sh"

CP_INTERNAL_URL="${CP_INTERNAL_URL:-http://localhost:8000}"
CONNECT_GATEWAY_KEY="${STOA_GATEWAY_API_KEY:-local-dev-key}"
SEED_INTERVAL="${SEED_INTERVAL:-30}"
CP_BASE="${CP_INTERNAL_URL}/v1/internal/gateways"

# name|type|tenant|admin_url|public_url
INSTANCES=(
  "connect-kong-local|kong|acme-corp|http://localhost:9081|http://localhost:9080"
  "connect-wm-local|webmethods|globex-inc|http://localhost:5555|http://localhost:5555"
)

# Gateway IDs stored as name=id pairs (bash 3.2 compat, no associative arrays)
_GW_IDS=""
_set_gw_id() { _GW_IDS="${_GW_IDS}${1}=${2} "; }
_get_gw_id() { echo "$_GW_IDS" | grep -oE "${1}=[^ ]+" | cut -d= -f2; }

seed_register() {
  local name="$1" gw_type="$2" tenant="$3" admin_url="$4" public_url="$5"
  echo "[connect]   register ($name, type=$gw_type)"
  local body
  body=$(cat <<EOF
{"hostname":"${name}.seed.local","mode":"connect","gateway_type":"$gw_type","version":"0.5.0-seed","environment":"dev","name":"$name","admin_url":"$admin_url","public_url":"$public_url","ui_url":"$admin_url","tenant_id":"$tenant","capabilities":["mcp","route_sync","discovery"]}
EOF
)
  local tmpfile; tmpfile=$(mktemp)
  local status
  status=$(curl -s -w "%{http_code}" --max-time 10 -o "$tmpfile" \
    -X POST "$CP_BASE/register" \
    -H "Content-Type: application/json" \
    -H "X-Gateway-Key: $CONNECT_GATEWAY_KEY" \
    -d "$body" 2>/dev/null) || status="000"

  if [ "$status" = "201" ] || [ "$status" = "200" ] || [ "$status" = "409" ]; then
    SEED_OK=$((SEED_OK+1))
    local gw_id
    gw_id=$(python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" < "$tmpfile" 2>/dev/null || echo "")
    if [ -n "$gw_id" ]; then
      _set_gw_id "$name" "$gw_id"
      echo "[connect]     → gateway_id=$gw_id"
    fi
  else
    SEED_FAIL=$((SEED_FAIL+1))
    echo -e "  ${_RED}FAIL${_NC} register/$name → $status"
  fi
  rm -f "$tmpfile"
}

seed_heartbeat() {
  local name="$1"; local gw_id="$(_get_gw_id "$name")"
  [ -z "$gw_id" ] && { echo "[connect]   heartbeat ($name) — SKIP (no gw_id)"; SEED_SKIP=$((SEED_SKIP+1)); return; }
  echo "[connect]   heartbeat ($name)"
  call "heartbeat/$name" \
    -X POST "$CP_BASE/$gw_id/heartbeat" \
    -H "Content-Type: application/json" \
    -H "X-Gateway-Key: $CONNECT_GATEWAY_KEY" \
    -d '{"status":"healthy","uptime_seconds":3600,"version":"0.5.0-seed","metrics":{"routes_synced":5}}'
}

seed_fetch_routes() {
  local name="$1"
  echo "[connect]   fetch-routes ($name)"
  local tmpfile; tmpfile=$(mktemp)
  local status
  status=$(curl -s -w "%{http_code}" --max-time 10 -o "$tmpfile" \
    "$CP_BASE/routes?gateway_name=$name" \
    -H "X-Gateway-Key: $CONNECT_GATEWAY_KEY" 2>/dev/null) || status="000"
  if [[ "$status" =~ ^2[0-9][0-9]$ ]]; then
    SEED_OK=$((SEED_OK+1))
    local count; count=$(python3 -c "import sys,json; print(len(json.load(sys.stdin)))" < "$tmpfile" 2>/dev/null || echo "?")
    echo "[connect]     → $count routes"
  else
    SEED_FAIL=$((SEED_FAIL+1))
    echo -e "  ${_RED}FAIL${_NC} fetch-routes/$name → $status"
  fi
  rm -f "$tmpfile"
}

seed_route_ack() {
  local name="$1"; local gw_id="$(_get_gw_id "$name")"
  [ -z "$gw_id" ] && { echo "[connect]   route-ack ($name) — SKIP"; SEED_SKIP=$((SEED_SKIP+1)); return; }
  echo "[connect]   route-ack ($name)"
  call "route-ack/$name" \
    -X POST "$CP_BASE/$gw_id/route-sync-ack" \
    -H "Content-Type: application/json" \
    -H "X-Gateway-Key: $CONNECT_GATEWAY_KEY" \
    -d '{"results":[{"deployment_id":"seed-deploy-001","status":"applied","generation":1,"steps":[{"step":"agent_received","status":"success","error":""},{"step":"api_synced","status":"success","error":""}]}]}'
}

seed_discovery() {
  local name="$1" gw_type="$2"; local gw_id="$(_get_gw_id "$name")"
  [ -z "$gw_id" ] && { echo "[connect]   discovery ($name) — SKIP"; SEED_SKIP=$((SEED_SKIP+1)); return; }
  echo "[connect]   discovery ($name, type=$gw_type)"
  call "discovery/$name" \
    -X POST "$CP_BASE/$gw_id/discovery" \
    -H "Content-Type: application/json" \
    -H "X-Gateway-Key: $CONNECT_GATEWAY_KEY" \
    -d "{\"apis\":[{\"id\":\"seed-${gw_type}-finance\",\"name\":\"Finance (${gw_type})\",\"version\":\"1.0\",\"category\":\"finance\",\"path\":\"/api/v1/accounts\",\"methods\":[\"GET\",\"POST\"],\"status\":\"published\"},{\"id\":\"seed-${gw_type}-crm\",\"name\":\"CRM (${gw_type})\",\"version\":\"1.0\",\"category\":\"crm\",\"path\":\"/api/v1/contacts\",\"methods\":[\"GET\",\"PUT\"],\"status\":\"published\"}]}"
}

seed_instance() {
  local entry="$1"
  local name gw_type tenant admin_url public_url
  IFS='|' read -r name gw_type tenant admin_url public_url <<< "$entry"
  echo "[connect] Instance: $name (type=$gw_type, tenant=$tenant)"
  seed_register "$name" "$gw_type" "$tenant" "$admin_url" "$public_url"
  seed_heartbeat "$name"
  seed_fetch_routes "$name"
  seed_route_ack "$name"
  seed_discovery "$name" "$gw_type"
  echo ""
}

run_batch() {
  reset_counters; _GW_IDS=""
  local cp_status
  cp_status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "$CP_INTERNAL_URL/health" 2>/dev/null || echo "000")
  if [ "$cp_status" = "000" ]; then
    echo "[connect] CP API ($CP_INTERNAL_URL) — unreachable"
    SEED_FAIL=$((SEED_FAIL+1)); print_summary "connect"; return
  fi
  for entry in "${INSTANCES[@]}"; do seed_instance "$entry"; done
  print_summary "connect"
}

echo "[connect] Config: cp=$CP_INTERNAL_URL key=${CONNECT_GATEWAY_KEY:0:8}..."
echo "[connect] Instances: ${#INSTANCES[@]}"
echo ""
run_batch

if [ "${1:-}" = "--continuous" ]; then
  echo "[connect] Continuous mode — Ctrl+C to stop"
  while true; do sleep "$SEED_INTERVAL"; run_batch; done
fi
