#!/usr/bin/env bash
# =============================================================================
# STOA Quickstart Smoke Test (CAB-1955)
# =============================================================================
# Validates that docker compose up produces healthy services.
# Usage: ./scripts/demo/smoke-test-quickstart.sh
# =============================================================================
set -euo pipefail

COMPOSE_DIR="deploy/docker-compose"
TIMEOUT=180  # 3 minutes max for all services to be healthy

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[smoke]${NC} $*"; }
warn() { echo -e "${YELLOW}[smoke]${NC} $*"; }
fail() { echo -e "${RED}[smoke]${NC} $*"; exit 1; }

# ---------------------------------------------------------------------------
# Healthcheck helpers
# ---------------------------------------------------------------------------
wait_for_url() {
  local name="$1" url="$2" max_wait="${3:-60}"
  local elapsed=0
  while [ "$elapsed" -lt "$max_wait" ]; do
    if curl -sf --max-time 5 "$url" > /dev/null 2>&1; then
      log "$name: healthy (${elapsed}s)"
      return 0
    fi
    sleep 3
    elapsed=$((elapsed + 3))
  done
  fail "$name: not healthy after ${max_wait}s"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
log "Starting STOA Quickstart smoke test..."

# 1. Check docker compose is available
command -v docker >/dev/null 2>&1 || fail "docker not found"

# 2. Verify compose file exists
[ -f "$COMPOSE_DIR/docker-compose.yml" ] || fail "docker-compose.yml not found in $COMPOSE_DIR"

# 3. Check Keycloak health
log "Checking Keycloak (port 8080)..."
wait_for_url "Keycloak" "http://localhost:8080/health/ready" "$TIMEOUT"

# 4. Check API health
log "Checking Control Plane API (port 8000)..."
wait_for_url "API" "http://localhost:8000/health" 60

# 5. Check Console UI health
log "Checking Console UI (port 3000)..."
wait_for_url "Console" "http://localhost:3000" 30

# 6. Verify Keycloak realm is imported (stoa realm exists)
log "Checking Keycloak realm 'stoa' exists..."
KC_REALMS=$(curl -sf "http://localhost:8080/realms/stoa/.well-known/openid-configuration" 2>/dev/null || true)
if echo "$KC_REALMS" | grep -q '"issuer"'; then
  log "Realm 'stoa': imported"
else
  fail "Realm 'stoa' not found — realm import may have failed"
fi

# 7. Verify Keycloak uses PostgreSQL (not H2)
log "Checking Keycloak DB connection..."
KC_DB_ENV=$(docker exec stoa-keycloak printenv KC_DB 2>/dev/null || true)
if [ "$KC_DB_ENV" = "postgres" ]; then
  log "KC_DB=postgres: confirmed"
else
  warn "KC_DB env not set to postgres (got: '$KC_DB_ENV') — may still use H2"
fi

# 8. Verify no start-dev in running command
KC_CMD=$(docker inspect stoa-keycloak --format '{{.Config.Cmd}}' 2>/dev/null || true)
if echo "$KC_CMD" | grep -q 'start-dev'; then
  fail "Keycloak is running in dev mode (start-dev) — expected prod mode (start)"
else
  log "KC mode: production (start)"
fi

log "========================================="
log "All smoke tests passed!"
log "========================================="
