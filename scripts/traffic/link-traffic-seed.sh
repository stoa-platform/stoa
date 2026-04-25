#!/usr/bin/env bash
# Link traffic seed — multi-tenant, Kong proxy (k3d) + webMethods (Docker).
#
# Registers stoa-link instances in the CP, sends heartbeats, then generates
# multi-tenant authz traffic through standalone link/authz endpoints.
#
# Usage:
#   ./scripts/traffic/link-traffic-seed.sh
#   ./scripts/traffic/link-traffic-seed.sh --continuous

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/seed-common.sh"

# ─── Config ──────────────────────────────────────────────────────────
LINK_KONG_AUTHZ_URL="${LINK_KONG_AUTHZ_URL:-${LINK_KONG_URL:-http://localhost:9082}}"
LINK_WM_URL="${LINK_WM_URL:-http://localhost:8086}"
LINK_CALLS_PER_COMBO="${LINK_CALLS_PER_COMBO:-2}"
SEED_INTERVAL="${SEED_INTERVAL:-30}"

CP_INTERNAL_URL="${CP_INTERNAL_URL:-http://localhost:8000}"
LINK_GATEWAY_KEY="${STOA_GATEWAY_API_KEY:-local-dev-key}"
CP_BASE="${CP_INTERNAL_URL}/v1/internal/gateways"

TENANTS=("acme-corp" "globex-inc" "initech")

# ─── Link instances: name|gateway_type|tenant|authz_url|target_gw_url ─
LINKS=(
  "link-kong-local|stoa_sidecar|acme-corp|$LINK_KONG_AUTHZ_URL|http://localhost:9080"
  "link-wm-local|stoa_sidecar|globex-inc|$LINK_WM_URL|http://localhost:5555"
)

# Gateway IDs (bash 3.2 compat)
_LINK_IDS=""
_set_link_id() { _LINK_IDS="${_LINK_IDS}${1}=${2} "; }
_get_link_id() { echo "$_LINK_IDS" | grep -oE "${1}=[^ ]+" | cut -d= -f2; }

# ─── Step 1: Register stoa-link instances in CP ─────────────────────
register_links() {
  echo "[link] Registering stoa-link instances in CP..."

  for entry in "${LINKS[@]}"; do
    local name gw_type tenant authz_url target_url
    IFS='|' read -r name gw_type tenant authz_url target_url <<< "$entry"

    local body="{\"hostname\":\"${name}.local\",\"mode\":\"sidecar\",\"gateway_type\":\"${gw_type}\",\"version\":\"0.5.0-seed\",\"environment\":\"dev\",\"name\":\"${name}\",\"admin_url\":\"${authz_url}\",\"public_url\":\"${authz_url}\",\"target_gateway_url\":\"${target_url}\",\"tenant_id\":\"${tenant}\",\"capabilities\":[\"ext_authz\",\"rate_limiting\",\"metering\"]}"

    local tmpfile; tmpfile=$(mktemp)
    local status
    status=$(curl -s -w "%{http_code}" --max-time 10 -o "$tmpfile" \
      -X POST "$CP_BASE/register" \
      -H "Content-Type: application/json" \
      -H "X-Gateway-Key: $LINK_GATEWAY_KEY" \
      -d "$body" 2>/dev/null) || status="000"

    if [ "$status" = "201" ] || [ "$status" = "200" ] || [ "$status" = "409" ]; then
      SEED_OK=$((SEED_OK+1))
      local gw_id
      gw_id=$(python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" < "$tmpfile" 2>/dev/null || echo "")
      if [ -n "$gw_id" ]; then
        _set_link_id "$name" "$gw_id"
        echo "[link]   $name → registered (id=$gw_id, mode=sidecar, tenant=$tenant)"
      fi
    else
      SEED_FAIL=$((SEED_FAIL+1))
      local err; err=$(cat "$tmpfile" 2>/dev/null || echo "")
      echo -e "  ${_RED}FAIL${_NC} register/$name → $status $err"
    fi
    rm -f "$tmpfile"
  done
  echo ""
}

# ─── Step 2: Heartbeat stoa-link instances ───────────────────────────
heartbeat_links() {
  for entry in "${LINKS[@]}"; do
    local name; name=$(echo "$entry" | cut -d'|' -f1)
    local gw_id; gw_id=$(_get_link_id "$name")
    [ -z "$gw_id" ] && continue

    call "heartbeat/$name" \
      -X POST "$CP_BASE/$gw_id/heartbeat" \
      -H "Content-Type: application/json" \
      -H "X-Gateway-Key: $LINK_GATEWAY_KEY" \
      -d '{"status":"healthy","uptime_seconds":3600,"version":"0.5.0-seed","metrics":{"authz_requests":0}}'
  done
}

# ─── Tenant role/scopes mapping ─────────────────────────────────────
get_scopes() {
  case "$1" in
    acme-corp)   echo '"stoa:read","stoa:write","stoa:admin"' ;;
    globex-inc)  echo '"stoa:read","stoa:write"' ;;
    initech)     echo '"stoa:read"' ;;
  esac
}
get_roles() {
  case "$1" in
    acme-corp)   echo '"tenant-admin"' ;;
    globex-inc)  echo '"devops"' ;;
    initech)     echo '"viewer"' ;;
  esac
}

# ─── API entries: category:path:method:expected (all 200 in minimal mode) ─
APIS=(
  "finance:/api/v1/accounts:GET:200:200:200"
  "finance:/api/v1/accounts:POST:200:200:200"
  "crm:/api/v1/contacts:GET:200:200:200"
  "crm:/api/v1/contacts:DELETE:200:200:200"
  "crm:/api/v1/contacts:PUT:200:200:200"
  "weather:/api/v1/forecasts:GET:200:200:200"
  "internal:/internal/metrics:GET:200:200:200"
  "admin:/admin/tenants:GET:200:200:200"
  "admin:/admin/tenants:POST:200:200:200"
  "admin:/admin/tenants:DELETE:200:200:200"
)

get_expected_code() {
  local api_entry="$1" tenant="$2"
  case "$tenant" in
    acme-corp)   echo "$api_entry" | cut -d: -f4 ;;
    globex-inc)  echo "$api_entry" | cut -d: -f5 ;;
    initech)     echo "$api_entry" | cut -d: -f6 ;;
    *)           echo "403" ;;
  esac
}

# ─── Step 3: Multi-tenant authz traffic ─────────────────────────────
seed_authz() {
  local gw_label="$1" base_url="$2"
  echo "[link] Gateway: $gw_label ($base_url) — /authz"

  for tenant in "${TENANTS[@]}"; do
    echo "[link]   Tenant: $tenant"
    local scopes roles
    scopes=$(get_scopes "$tenant")
    roles=$(get_roles "$tenant")

    for api_entry in "${APIS[@]}"; do
      local category path method expected
      category=$(echo "$api_entry" | cut -d: -f1)
      path=$(echo "$api_entry" | cut -d: -f2)
      method=$(echo "$api_entry" | cut -d: -f3)
      expected=$(get_expected_code "$api_entry" "$tenant")
      local label="${category}/${method}/${tenant}/${gw_label}"

      local body="{\"method\":\"$method\",\"path\":\"$path\",\"headers\":{},\"user\":{\"id\":\"${tenant}-user\",\"email\":\"${tenant}-user@stoa.dev\",\"roles\":[$roles],\"scopes\":[$scopes]},\"tenant_id\":\"$tenant\"}"

      for _ in $(seq 1 "$LINK_CALLS_PER_COMBO"); do
        call_expect "$label" "$expected" \
          -X POST -H "Content-Type: application/json" \
          -d "$body" "$base_url/authz"
      done
    done
  done

  # No-auth (no user block → 401)
  echo "[link]   No-auth ($gw_label) — expect 401"
  for path in "/api/v1/accounts" "/api/v1/contacts" "/admin/tenants"; do
    call_expect "no-auth:${path}/${gw_label}" "401" \
      -X POST -H "Content-Type: application/json" \
      -d "{\"method\":\"GET\",\"path\":\"$path\",\"headers\":{}}" \
      "$base_url/authz"
  done
}

# ─── Main ────────────────────────────────────────────────────────────
run_batch() {
  reset_counters; _LINK_IDS=""

  # Register + heartbeat (makes links visible as ONLINE in CP)
  local cp_status
  cp_status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "$CP_INTERNAL_URL/health" 2>/dev/null || echo "000")
  if [ "$cp_status" != "000" ]; then
    register_links
    heartbeat_links
  else
    echo "[link] CP API unreachable — skipping registration"
  fi

  # Authz traffic per gateway
  for entry in "${LINKS[@]}"; do
    local name authz_url gw_label
    name=$(echo "$entry" | cut -d'|' -f1)
    authz_url=$(echo "$entry" | cut -d'|' -f4)

    # Derive label from name
    case "$name" in
      *kong*) gw_label="kong-k3d" ;;
      *wm*)   gw_label="wm-docker" ;;
      *)      gw_label="$name" ;;
    esac

    local status
    status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "$authz_url/health" 2>/dev/null || echo "000")
    if [ "$status" = "000" ]; then
      echo "[link] $gw_label ($authz_url) — unreachable, skipping"
      continue
    fi
    seed_authz "$gw_label" "$authz_url"
  done

  print_summary "link"
}

echo "[link] Config: kong_authz=$LINK_KONG_AUTHZ_URL wm=$LINK_WM_URL calls=$LINK_CALLS_PER_COMBO cp=$CP_INTERNAL_URL"
echo "[link] Tenants: ${TENANTS[*]}"
echo "[link] Links: ${#LINKS[@]} (stoa-link instances, mode=sidecar)"
echo ""
run_batch

if [ "${1:-}" = "--continuous" ]; then
  echo "[link] Continuous mode — Ctrl+C to stop"
  while true; do sleep "$SEED_INTERVAL"; run_batch; done
fi
