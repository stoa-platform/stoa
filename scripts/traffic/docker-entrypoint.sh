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

register_route() {
  local id="$1" name="$2" path="$3" backend="$4" methods="${5:-[]}"
  curl -sf -X POST "$GATEWAY_URL/admin/apis" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"id\":\"$id\",\"name\":\"$name\",\"tenant_id\":\"default\",\"path_prefix\":\"$path\",\"backend_url\":\"$backend\",\"methods\":$methods,\"spec_hash\":\"seed-local\",\"activated\":true}" \
    > /dev/null 2>&1 && echo "  + $name -> $path" || echo "  ! $name FAILED (may exist)"
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
