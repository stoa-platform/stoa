#!/usr/bin/env bash
# Shared helpers for all traffic seed scripts.
# Source this: source "$(dirname "${BASH_SOURCE[0]}")/seed-common.sh"

SEED_OK=0; SEED_FAIL=0; SEED_SKIP=0
_GREEN='\033[0;32m'; _RED='\033[0;31m'; _YELLOW='\033[1;33m'; _NC='\033[0m'

call() {
  local label="$1"; shift
  local status
  status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$@" 2>/dev/null) || status="000"
  if [[ "$status" =~ ^2[0-9][0-9]$ ]]; then
    SEED_OK=$((SEED_OK+1))
  else
    SEED_FAIL=$((SEED_FAIL+1))
    echo -e "  ${_RED}FAIL${_NC} $label → $status"
  fi
}

call_expect() {
  local label="$1"; shift
  local expected="$1"; shift
  local status
  status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$@" 2>/dev/null) || status="000"
  if [ "$status" = "$expected" ]; then
    SEED_OK=$((SEED_OK+1))
  else
    SEED_FAIL=$((SEED_FAIL+1))
    echo -e "  ${_RED}FAIL${_NC} $label → $status (expected $expected)"
  fi
}

_seed_cached_token=""; _seed_cached_token_exp=0
get_token() {
  local kc_url="${KC_TOKEN_URL:-http://localhost:8080/realms/stoa/protocol/openid-connect/token}"
  local client_id="${1:-${KC_CLIENT_ID:-stoa-mcp-gateway}}"
  local client_secret="${2:-${KC_CLIENT_SECRET:-mcp-dev-secret}}"
  local now; now=$(date +%s)
  if [ -n "$_seed_cached_token" ] && [ "$now" -lt "$_seed_cached_token_exp" ]; then
    echo "$_seed_cached_token"; return
  fi
  local resp token
  resp=$(curl -s --max-time 5 -X POST "$kc_url" \
    -d "grant_type=client_credentials" -d "client_id=$client_id" \
    -d "client_secret=$client_secret" -d "scope=stoa:read" 2>/dev/null) || { echo ""; return; }
  token=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null) || { echo ""; return; }
  if [ -n "$token" ]; then
    _seed_cached_token="$token"; _seed_cached_token_exp=$((now + 240))
  fi
  echo "$token"
}

reset_counters() { SEED_OK=0; SEED_FAIL=0; SEED_SKIP=0; }

print_summary() {
  local label="${1:-seed}"
  local total=$((SEED_OK + SEED_FAIL + SEED_SKIP))
  if [ "$SEED_FAIL" -gt 0 ]; then
    echo -e "[${label}] $(date +%H:%M:%S) — ${_GREEN}${SEED_OK} ok${_NC}, ${_RED}${SEED_FAIL} fail${_NC}, ${SEED_SKIP} skip (${total} total)"
  else
    echo -e "[${label}] $(date +%H:%M:%S) — ${_GREEN}${SEED_OK} ok${_NC}, ${SEED_FAIL} fail, ${SEED_SKIP} skip (${total} total)"
  fi
}

load_seed_conf() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
  [ -f "$script_dir/seed.conf" ] && source "$script_dir/seed.conf"
}
