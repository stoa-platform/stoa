#!/usr/bin/env bash
# Local traffic seed — all auth modes (CAB-1997).
#
# Generates traffic covering every gateway auth path so Tempo traces
# include spans for: no-auth, Bearer JWT, API Key, mTLS, DPoP.
#
# Usage:
#   ./scripts/traffic/local-traffic-seed.sh              # run once
#   ./scripts/traffic/local-traffic-seed.sh --continuous  # every 30s until killed
#
# Prerequisites:
#   - Gateway on localhost:8081 (STOA_GATEWAY_URL)
#   - Keycloak on localhost:8080 (KC_TOKEN_URL)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ─── Load config (git-versioned defaults) ────────────────────────────
# Config file: scripts/traffic/seed.conf
# Env vars override config file values.

# Precedence: env vars > seed.conf > defaults
# Save any env overrides before sourcing config file
_env_no_auth="${SEED_NO_AUTH:-}"
_env_bearer="${SEED_BEARER_JWT:-}"
_env_apikey="${SEED_API_KEY:-}"
_env_mtls="${SEED_MTLS:-}"
_env_dpop="${SEED_DPOP:-}"
_env_proxy="${SEED_PROXY:-}"
_env_calls="${SEED_CALLS_PER_MODE:-}"
_env_interval="${SEED_INTERVAL:-}"

# Defaults
SEED_NO_AUTH=true; SEED_BEARER_JWT=true; SEED_API_KEY=true
SEED_MTLS=true; SEED_DPOP=true; SEED_PROXY=true
SEED_CALLS_PER_MODE=3; SEED_INTERVAL=30

# Config file overrides defaults
if [ -f "$SCRIPT_DIR/seed.conf" ]; then
  # shellcheck source=seed.conf
  source "$SCRIPT_DIR/seed.conf"
fi

# Env vars override config file
[ -n "$_env_no_auth" ] && SEED_NO_AUTH="$_env_no_auth"
[ -n "$_env_bearer" ] && SEED_BEARER_JWT="$_env_bearer"
[ -n "$_env_apikey" ] && SEED_API_KEY="$_env_apikey"
[ -n "$_env_mtls" ] && SEED_MTLS="$_env_mtls"
[ -n "$_env_dpop" ] && SEED_DPOP="$_env_dpop"
[ -n "$_env_proxy" ] && SEED_PROXY="$_env_proxy"
[ -n "$_env_calls" ] && SEED_CALLS_PER_MODE="$_env_calls"
[ -n "$_env_interval" ] && SEED_INTERVAL="$_env_interval"

GATEWAY_URL="${STOA_GATEWAY_URL:-http://localhost:8081}"
ADMIN_TOKEN="${STOA_ADMIN_API_TOKEN:-stoa-local-admin-token}"
KC_URL="${KC_TOKEN_URL:-http://localhost:8080/realms/stoa/protocol/openid-connect/token}"
KC_CLIENT="${KC_CLIENT_ID:-stoa-mcp-gateway}"
KC_SECRET="${KC_CLIENT_SECRET:-mcp-dev-secret}"
KC_DPOP_CLIENT="${KC_DPOP_CLIENT_ID:-stoa-e2e-dpop}"
KC_DPOP_SECRET="${KC_DPOP_CLIENT_SECRET:-dpop-e2e-dev-secret}"
MTLS_CERT="${MTLS_CLIENT_CERT:-$SCRIPT_DIR/../demo/certs/client-001.pem}"
MTLS_KEY="${MTLS_CLIENT_KEY:-$SCRIPT_DIR/../demo/certs/client-001-key.pem}"
CALLS_PER_MODE="${SEED_CALLS_PER_MODE}"
INTERVAL="${SEED_INTERVAL}"

# Counters
OK=0; FAIL=0; SKIP=0

# ─── Helpers ─────────────────────────────────────────────────────────

call() {
  local label="$1"; shift
  local status
  status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$@" 2>/dev/null) || status="000"
  if [ "$status" = "200" ] || [ "$status" = "204" ]; then
    OK=$((OK+1))
  else
    FAIL=$((FAIL+1))
    echo "[seed]   FAIL $label → $status"
  fi
}

# ─── OAuth2 token (client_credentials) ───────────────────────────────

_cached_token=""
_cached_token_exp=0
_cached_dpop_token=""
_cached_dpop_token_exp=0

get_token() {
  local client_id="${1:-$KC_CLIENT}"
  local client_secret="${2:-$KC_SECRET}"
  local now
  now=$(date +%s)

  # Use per-client cache
  if [ "$client_id" = "$KC_CLIENT" ] && [ -n "$_cached_token" ] && [ "$now" -lt "$_cached_token_exp" ]; then
    echo "$_cached_token"; return
  fi
  if [ "$client_id" = "$KC_DPOP_CLIENT" ] && [ -n "$_cached_dpop_token" ] && [ "$now" -lt "$_cached_dpop_token_exp" ]; then
    echo "$_cached_dpop_token"; return
  fi

  local resp token
  resp=$(curl -s --max-time 5 -X POST "$KC_URL" \
    -d "grant_type=client_credentials" \
    -d "client_id=$client_id" \
    -d "client_secret=$client_secret" \
    -d "scope=stoa:read" 2>/dev/null) || { echo ""; return; }
  token=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null) || { echo ""; return; }

  if [ -n "$token" ]; then
    if [ "$client_id" = "$KC_DPOP_CLIENT" ]; then
      _cached_dpop_token="$token"; _cached_dpop_token_exp=$((now + 240))
    else
      _cached_token="$token"; _cached_token_exp=$((now + 240))
    fi
  fi
  echo "$token"
}

# ─── DPoP proof (RFC 9449) ───────────────────────────────────────────

generate_dpop_proof() {
  local http_method="$1"
  local http_url="$2"
  python3 - "$http_method" "$http_url" <<'PYEOF'
import json, time, uuid, sys, base64
try:
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.backends import default_backend
    private_key = rsa.generate_private_key(65537, 2048, default_backend())
    pub = private_key.public_key().public_numbers()
    def b64url(n, length):
        return base64.urlsafe_b64encode(n.to_bytes(length, 'big')).rstrip(b'=').decode()
    headers = {
        'typ': 'dpop+jwt', 'alg': 'RS256',
        'jwk': {'kty': 'RSA', 'n': b64url(pub.n, 256), 'e': b64url(pub.e, 3)},
    }
    payload = {
        'jti': str(uuid.uuid4()), 'htm': sys.argv[1],
        'htu': sys.argv[2], 'iat': int(time.time()),
    }
    print(jwt.encode(payload, private_key, algorithm='RS256', headers=headers))
except ImportError:
    sys.exit(1)
except Exception as e:
    print(str(e), file=sys.stderr); sys.exit(1)
PYEOF
}

# MCP tool call body
MCP_BODY='{"name":"stoa_platform_health","arguments":{}}'
PROXY_OK=false

# ─── Ensure echo route exists (requires admin API) ──────────────────

ensure_echo_route() {
  # Check if admin API is available
  local status
  status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 \
    -H "Authorization: Bearer $ADMIN_TOKEN" "$GATEWAY_URL/admin/apis" 2>/dev/null) || status="000"
  if [ "$status" != "200" ]; then
    echo "[seed] Admin API unavailable ($status) — proxy routes disabled"
    return
  fi

  # Check if echo route already exists
  local has_echo
  has_echo=$(curl -s -H "Authorization: Bearer $ADMIN_TOKEN" "$GATEWAY_URL/admin/apis" 2>/dev/null \
    | python3 -c "import sys,json; apis=json.load(sys.stdin); print(any(a.get('id')=='echo-seed' or a.get('path_prefix')=='/echo' for a in apis))" 2>/dev/null || echo "False")
  if [ "$has_echo" != "True" ]; then
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
  PROXY_OK=true
}

# ─── Mode 1: No Auth ────────────────────────────────────────────────

seed_no_auth() {
  [ "$SEED_NO_AUTH" != true ] && return
  echo "[seed] Mode: no-auth"
  for _ in $(seq 1 "$CALLS_PER_MODE"); do
    call "health/no-auth" "$GATEWAY_URL/health"
    call "mcp-list/no-auth" -X POST -H "Content-Type: application/json" \
      "$GATEWAY_URL/mcp/tools/list" -d '{}'
    call "mcp-call/no-auth" -X POST -H "Content-Type: application/json" \
      "$GATEWAY_URL/mcp/tools/call" -d "$MCP_BODY"
    call "mcp-caps/no-auth" "$GATEWAY_URL/mcp/capabilities"
    if [ "$SEED_PROXY" = true ] && [ "$PROXY_OK" = true ]; then
      call "proxy/no-auth" "$GATEWAY_URL/echo"
    fi
  done
}

# ─── Mode 2: Bearer JWT ─────────────────────────────────────────────

seed_bearer() {
  [ "$SEED_BEARER_JWT" != true ] && return
  echo "[seed] Mode: bearer-jwt"
  local token
  token=$(get_token)
  if [ -z "$token" ]; then
    echo "[seed]   SKIP bearer — KC unreachable"
    SKIP=$((SKIP + CALLS_PER_MODE * 3))
    return
  fi
  for _ in $(seq 1 "$CALLS_PER_MODE"); do
    call "mcp-list/bearer" -X POST -H "Content-Type: application/json" \
      -H "Authorization: Bearer $token" \
      "$GATEWAY_URL/mcp/tools/list" -d '{}'
    call "mcp-call/bearer" -X POST -H "Content-Type: application/json" \
      -H "Authorization: Bearer $token" \
      "$GATEWAY_URL/mcp/tools/call" -d "$MCP_BODY"
    call "mcp-caps/bearer" -H "Authorization: Bearer $token" \
      "$GATEWAY_URL/mcp/capabilities"
    if [ "$SEED_PROXY" = true ] && [ "$PROXY_OK" = true ]; then
      call "proxy/bearer" -H "Authorization: Bearer $token" "$GATEWAY_URL/echo"
    fi
  done
}

# ─── Mode 3: API Key ────────────────────────────────────────────────

seed_api_key() {
  [ "$SEED_API_KEY" != true ] && return
  echo "[seed] Mode: api-key"
  local api_key="${STOA_API_KEY:-local-dev-key}"
  for _ in $(seq 1 "$CALLS_PER_MODE"); do
    call "mcp-call/api-key-header" -X POST -H "Content-Type: application/json" \
      -H "X-API-Key: $api_key" \
      "$GATEWAY_URL/mcp/tools/call" -d "$MCP_BODY"
    call "mcp-list/api-key-query" -X POST -H "Content-Type: application/json" \
      "$GATEWAY_URL/mcp/tools/list?api_key=$api_key" -d '{}'
    if [ "$SEED_PROXY" = true ] && [ "$PROXY_OK" = true ]; then
      call "proxy/api-key" -H "X-API-Key: $api_key" "$GATEWAY_URL/echo"
    fi
  done
}

# ─── Mode 4: mTLS ───────────────────────────────────────────────────

seed_mtls() {
  [ "$SEED_MTLS" != true ] && return
  echo "[seed] Mode: mtls"
  if [ ! -f "$MTLS_CERT" ] || [ ! -f "$MTLS_KEY" ]; then
    echo "[seed]   SKIP mTLS — certs not found"
    SKIP=$((SKIP + CALLS_PER_MODE * 2))
    return
  fi
  for _ in $(seq 1 "$CALLS_PER_MODE"); do
    call "mcp-call/mtls" -X POST -H "Content-Type: application/json" \
      --cert "$MTLS_CERT" --key "$MTLS_KEY" -k \
      "$GATEWAY_URL/mcp/tools/call" -d "$MCP_BODY"
    call "mcp-list/mtls" -X POST -H "Content-Type: application/json" \
      --cert "$MTLS_CERT" --key "$MTLS_KEY" -k \
      "$GATEWAY_URL/mcp/tools/list" -d '{}'
    if [ "$SEED_PROXY" = true ] && [ "$PROXY_OK" = true ]; then
      call "proxy/mtls" --cert "$MTLS_CERT" --key "$MTLS_KEY" -k "$GATEWAY_URL/echo"
    fi
  done
}

# ─── Mode 5: DPoP (RFC 9449) ────────────────────────────────────────

seed_dpop() {
  [ "$SEED_DPOP" != true ] && return
  echo "[seed] Mode: dpop"
  if ! python3 -c "import jwt" 2>/dev/null; then
    echo "[seed]   SKIP DPoP — pip install PyJWT cryptography"
    SKIP=$((SKIP + CALLS_PER_MODE * 2))
    return
  fi

  local token
  token=$(get_token "$KC_DPOP_CLIENT" "$KC_DPOP_SECRET")
  if [ -z "$token" ]; then
    # Fallback to default client
    token=$(get_token)
  fi
  if [ -z "$token" ]; then
    echo "[seed]   SKIP DPoP — no token"
    SKIP=$((SKIP + CALLS_PER_MODE * 2))
    return
  fi

  for _ in $(seq 1 "$CALLS_PER_MODE"); do
    # DPoP baseline: proof + bound token
    local proof
    proof=$(generate_dpop_proof "POST" "$GATEWAY_URL/mcp/tools/call")
    if [ -n "$proof" ]; then
      call "mcp-call/dpop" -X POST -H "Content-Type: application/json" \
        -H "Authorization: DPoP $token" \
        -H "DPoP: $proof" \
        "$GATEWAY_URL/mcp/tools/call" -d "$MCP_BODY"
    else
      FAIL=$((FAIL+1))
      echo "[seed]   FAIL mcp-call/dpop — proof generation failed"
    fi

    # FAPI Advanced: DPoP + mTLS
    proof=$(generate_dpop_proof "POST" "$GATEWAY_URL/mcp/tools/list")
    if [ -n "$proof" ] && [ -f "$MTLS_CERT" ]; then
      call "mcp-list/dpop+mtls" -X POST -H "Content-Type: application/json" \
        -H "Authorization: DPoP $token" \
        -H "DPoP: $proof" \
        --cert "$MTLS_CERT" --key "$MTLS_KEY" -k \
        "$GATEWAY_URL/mcp/tools/list" -d '{}'
    elif [ -n "$proof" ]; then
      call "mcp-list/dpop" -X POST -H "Content-Type: application/json" \
        -H "Authorization: DPoP $token" \
        -H "DPoP: $proof" \
        "$GATEWAY_URL/mcp/tools/list" -d '{}'
    else
      FAIL=$((FAIL+1))
      echo "[seed]   FAIL mcp-list/dpop — proof generation failed"
    fi
  done
}

# ─── Main ────────────────────────────────────────────────────────────

run_batch() {
  OK=0; FAIL=0; SKIP=0

  seed_no_auth
  seed_bearer
  seed_api_key
  seed_mtls
  seed_dpop

  local total=$((OK + FAIL + SKIP))
  echo "[seed] $(date +%H:%M:%S) — ${OK} ok, ${FAIL} fail, ${SKIP} skip (${total} total)"
}

# Print active config
echo "[seed] Config: no-auth=$SEED_NO_AUTH bearer=$SEED_BEARER_JWT api-key=$SEED_API_KEY mtls=$SEED_MTLS dpop=$SEED_DPOP proxy=$SEED_PROXY calls=$CALLS_PER_MODE"

if [ "$SEED_PROXY" = true ]; then
  ensure_echo_route
fi
run_batch

if [ "${1:-}" = "--continuous" ]; then
  echo "[seed] Continuous mode — Ctrl+C to stop"
  while true; do
    sleep "$INTERVAL"
    run_batch
  done
fi
