#!/usr/bin/env bash
# =============================================================================
# STOA Quick Start — Smoke Test (CAB-1955)
# =============================================================================
# Validates that docker compose quickstart services are healthy:
#   - PostgreSQL: keycloak database exists
#   - Keycloak: production mode, realm imported, healthcheck passes
#   - Control Plane API: healthcheck passes
#   - Console UI: healthcheck passes
#
# Usage:
#   ./scripts/demo/smoke-test-quickstart.sh
#
# Prerequisites:
#   docker compose up -d (from deploy/docker-compose/)
# =============================================================================

set -euo pipefail

COMPOSE_DIR="$(cd "$(dirname "$0")/../../deploy/docker-compose" && pwd)"
PASS=0
FAIL=0
TOTAL=0

# Colors (disable if not a terminal)
if [ -t 1 ]; then
  GREEN='\033[0;32m'
  RED='\033[0;31m'
  YELLOW='\033[1;33m'
  NC='\033[0m'
else
  GREEN='' RED='' YELLOW='' NC=''
fi

check() {
  local name="$1"
  local cmd="$2"
  TOTAL=$((TOTAL + 1))
  if eval "$cmd" > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} $name"
    PASS=$((PASS + 1))
  else
    echo -e "  ${RED}✗${NC} $name"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== STOA Quick Start Smoke Test ==="
echo ""

# ---- PostgreSQL ----
echo "PostgreSQL:"
check "Container running" \
  "docker compose -f '$COMPOSE_DIR/docker-compose.yml' ps postgres --format json | grep -q running"
check "keycloak database exists" \
  "docker exec stoa-postgres psql -U stoa -c '\\l' | grep -q keycloak"
check "stoa_platform database exists" \
  "docker exec stoa-postgres psql -U stoa -c '\\l' | grep -q stoa_platform"
echo ""

# ---- Keycloak ----
echo "Keycloak:"
check "Container running" \
  "docker compose -f '$COMPOSE_DIR/docker-compose.yml' ps keycloak --format json | grep -q running"
check "Health endpoint ready" \
  "curl -sf http://localhost:${PORT_KEYCLOAK:-8080}/health/ready | grep -q UP"
check "Production mode (no start-dev)" \
  "! grep -q 'start-dev' '$COMPOSE_DIR/docker-compose.yml'"
check "Realm stoa imported" \
  "curl -sf http://localhost:${PORT_KEYCLOAK:-8080}/realms/stoa/.well-known/openid-configuration | grep -q stoa"
echo ""

# ---- Control Plane API ----
echo "Control Plane API:"
check "Container running" \
  "docker compose -f '$COMPOSE_DIR/docker-compose.yml' ps control-plane-api --format json | grep -q running"
check "Health endpoint" \
  "curl -sf http://localhost:${PORT_API:-8000}/health | grep -q ok"
echo ""

# ---- Console UI ----
echo "Console UI:"
check "Container running" \
  "docker compose -f '$COMPOSE_DIR/docker-compose.yml' ps control-plane-ui --format json | grep -q running"
check "HTTP responds" \
  "curl -sf -o /dev/null http://localhost:${PORT_CONSOLE:-3000}"
echo ""

# ---- Summary ----
echo "=== Results: ${PASS}/${TOTAL} passed, ${FAIL} failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo -e "${RED}SMOKE TEST FAILED${NC}"
  exit 1
else
  echo -e "${GREEN}ALL CHECKS PASSED${NC}"
  exit 0
fi
