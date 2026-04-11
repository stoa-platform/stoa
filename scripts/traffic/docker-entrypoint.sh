#!/usr/bin/env bash
# Traffic seeder entrypoint for docker-compose (CAB-1997).
#
# 1. Wait for gateway to be healthy
# 2. Bootstrap API routes via admin API
# 3. Run realistic-seeder in a loop
set -euo pipefail

# Install dependencies
apt-get update -qq && apt-get install -y -qq curl > /dev/null 2>&1
pip install -q requests 2>/dev/null

GATEWAY_URL="${GATEWAY_URL:-http://stoa-gateway:8080}"
ADMIN_TOKEN="${ADMIN_TOKEN:-local-dev-key}"
KC_URL="${KC_TOKEN_URL:-http://keycloak:8080/realms/stoa/protocol/openid-connect/token}"
ECHO_BACKEND="${ECHO_BACKEND:-http://echo-backend:8888}"

echo "[seeder] Waiting for gateway at $GATEWAY_URL..."
until curl -sf "$GATEWAY_URL/health" > /dev/null 2>&1; do
  sleep 2
done
echo "[seeder] Gateway healthy"

# --- Bootstrap routes ---
echo "[seeder] Registering API routes..."

SEED_TENANT="${SEED_TENANT:-demo}"

register_route() {
  local id="$1" name="$2" path="$3" backend="$4" methods="${5:-[]}"
  local full_prefix="/apis/${SEED_TENANT}/${name}${path}"
  curl -sf -X POST "$GATEWAY_URL/admin/apis" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"id\":\"$id\",\"name\":\"$name\",\"tenant_id\":\"${SEED_TENANT}\",\"path_prefix\":\"$full_prefix\",\"backend_url\":\"$backend\",\"methods\":$methods,\"spec_hash\":\"seed-local\",\"activated\":true}" \
    > /dev/null 2>&1 && echo "  + $name -> $full_prefix" || echo "  ! $name FAILED (may exist)"
}

# Tier 1: No auth
register_route "seed-echo"      "echo-fallback"    "/"              "$ECHO_BACKEND"
register_route "seed-exchange"   "exchange-rate"    "/v4"            "$ECHO_BACKEND"

# Tier 2: API Key (via echo — no real external APIs in local)
register_route "seed-weather"    "openweathermap"   "/weather"       "$ECHO_BACKEND"               '["GET"]'
register_route "seed-news"       "newsapi"          "/top-headlines" "$ECHO_BACKEND"               '["GET"]'

# Tier 3: OAuth2
register_route "seed-oauth2"     "echo-oauth2"      "/oauth2"        "$ECHO_BACKEND"               '["GET","POST"]'

# Tier 4: FAPI
register_route "seed-accounts"   "fapi-accounts"    "/api/v1/accounts"  "$ECHO_BACKEND/api/v1/accounts"  '["GET"]'
register_route "seed-transfers"  "fapi-transfers"    "/api/v1/transfers" "$ECHO_BACKEND/api/v1/transfers" '["GET","POST"]'

# Register same routes on connect gateway (if available)
CONNECT_GW="${CONNECT_URL:-}"
if [ -n "$CONNECT_GW" ]; then
  echo "[seeder] Registering routes on connect gateway at $CONNECT_GW..."
  for attempt in 1 2 3 4 5; do
    curl -sf "$CONNECT_GW/health" > /dev/null 2>&1 && break
    echo "  waiting for connect gateway... ($attempt)"
    sleep 3
  done
  # Reuse register_route but target connect gateway
  register_connect() {
    local id="$1" name="$2" path="$3" backend="$4" methods="${5:-[]}"
    local full_prefix="/apis/${SEED_TENANT}/${name}${path}"
    curl -sf -X POST "$CONNECT_GW/admin/apis" \
      -H "Authorization: Bearer $ADMIN_TOKEN" \
      -H "Content-Type: application/json" \
      -d "{\"id\":\"$id\",\"name\":\"$name\",\"tenant_id\":\"${SEED_TENANT}\",\"path_prefix\":\"$full_prefix\",\"backend_url\":\"$backend\",\"methods\":$methods,\"spec_hash\":\"seed-local\",\"activated\":true}" \
      > /dev/null 2>&1 && echo "  + [connect] $name -> $full_prefix" || echo "  ! [connect] $name FAILED (may exist)"
  }
  register_connect "connect-eurostat"  "eurostat"     "/nama_10_gdp"       "$ECHO_BACKEND"
  register_connect "connect-accounts"  "echo-bearer"  "/api/v1/accounts"   "$ECHO_BACKEND/api/v1/accounts"  '["GET"]'
fi

echo "[seeder] Routes registered"

# --- Run seeder in loop ---
echo "[seeder] Starting traffic seeder (loop mode, ${DURATION:-300}s per cycle)"
# Create proper Python package structure for imports
mkdir -p /app/scripts/traffic
ln -sf /app/scripts/traffic/auth_helpers.py /app/scripts/traffic/auth_helpers.py 2>/dev/null || true
ln -sf /app/scripts/traffic/scenarios.py /app/scripts/traffic/scenarios.py 2>/dev/null || true
touch /app/scripts/__init__.py /app/scripts/traffic/__init__.py 2>/dev/null || true

SEEDER_MODE="${SEEDER_MODE:-edge-only}"
while true; do
  python3 /app/realistic-seeder.py --mode "$SEEDER_MODE" 2>&1 || true
  echo "[seeder] Cycle complete, restarting in 5s..."
  sleep 5
done
