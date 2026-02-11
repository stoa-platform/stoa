#!/usr/bin/env bash
# Master E2E test orchestrator for STOA Gateway
#
# Builds the gateway, starts docker-compose, runs all test suites, tears down.
# Exit code = total number of failures across all suites.
#
# Usage:
#   cd stoa-gateway && ./tests/e2e/run-e2e.sh
#   SKIP_BUILD=1 ./tests/e2e/run-e2e.sh   # skip docker build (use existing image)
#   SKIP_TEARDOWN=1 ./tests/e2e/run-e2e.sh # keep containers running after tests
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose-test.yml"
PROJECT_NAME="stoa-gw-e2e"
GATEWAY_URL="${GATEWAY_URL:-http://localhost:18080}"
MAX_WAIT="${MAX_WAIT:-120}"
TOTAL_FAIL=0

export GATEWAY_URL

# --- Helpers ---

log() { echo ">>> $*"; }
wait_for_health() {
  local url="$1" name="$2" elapsed=0
  log "Waiting for $name ($url)..."
  while ! curl -sf "$url" > /dev/null 2>&1; do
    elapsed=$((elapsed + 2))
    if [ "$elapsed" -ge "$MAX_WAIT" ]; then
      log "TIMEOUT: $name not healthy after ${MAX_WAIT}s"
      docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" logs "$name" 2>/dev/null | tail -20
      return 1
    fi
    sleep 2
  done
  log "$name healthy (${elapsed}s)"
}

# --- Startup ---

log "Starting E2E test environment..."

if [ "${SKIP_BUILD:-}" != "1" ]; then
  log "Building gateway image..."
  docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" build gateway
fi

docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" up -d

# Wait for services
wait_for_health "http://localhost:18081/__admin/health" "wiremock"
wait_for_health "http://localhost:18082/get" "httpbin"
wait_for_health "$GATEWAY_URL/health" "gateway"

log "All services healthy. Running tests..."
echo ""

# --- Run test suites ---

run_suite() {
  local script="$1"
  if bash "$script"; then
    return 0
  else
    local failures=$?
    TOTAL_FAIL=$((TOTAL_FAIL + failures))
    return 0  # Don't abort on test failures
  fi
}

run_suite "$SCRIPT_DIR/test-health.sh"
echo ""
run_suite "$SCRIPT_DIR/test-auth.sh"
echo ""
run_suite "$SCRIPT_DIR/test-mcp.sh"
echo ""
run_suite "$SCRIPT_DIR/test-oauth.sh"

# --- Teardown ---

echo ""
echo "========================================="
if [ "$TOTAL_FAIL" -eq 0 ]; then
  echo "ALL E2E TESTS PASSED"
else
  echo "E2E TESTS: $TOTAL_FAIL FAILURES"
fi
echo "========================================="

if [ "${SKIP_TEARDOWN:-}" != "1" ]; then
  log "Tearing down..."
  docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" down -v --remove-orphans
fi

exit "$TOTAL_FAIL"
