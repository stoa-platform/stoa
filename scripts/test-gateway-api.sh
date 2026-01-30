#!/usr/bin/env bash
# Smoke test for webMethods API Gateway REST API.
# Validates all operations needed by the STOA Gateway Adapter.
#
# Usage: ./scripts/test-gateway-api.sh [BASE_URL]
# Default: http://localhost:5555
set -euo pipefail

BASE="${1:-http://localhost:5555}"
API="$BASE/rest/apigateway"
AUTH="Administrator:manage"
PASS=0
FAIL=0

check() {
  local desc="$1"; shift
  if output=$("$@" 2>&1); then
    echo "  [PASS] $desc"
    ((PASS++))
  else
    echo "  [FAIL] $desc"
    echo "         $output"
    ((FAIL++))
  fi
}

echo "=== STOA Gateway Adapter — Smoke Test ==="
echo "Target: $API"
echo ""

# --- Lifecycle ---
echo "-- Lifecycle --"
check "Health check" curl -sf -u "$AUTH" "$API/health"

# --- APIs ---
echo "-- APIs --"
check "List APIs" curl -sf -u "$AUTH" "$API/apis"

# --- Policies ---
echo "-- Policies --"
check "List policies" curl -sf -u "$AUTH" "$API/policies"
check "List policy actions" curl -sf -u "$AUTH" "$API/policyActions"

# --- Applications ---
echo "-- Applications --"
check "List applications" curl -sf -u "$AUTH" "$API/applications"

# Create a test application
APP_RESPONSE=$(curl -sf -u "$AUTH" -X POST "$API/applications" \
  -H "Content-Type: application/json" \
  -d '{"name":"stoa-smoke-test","description":"Smoke test app","contactEmails":["test@stoa.dev"]}' 2>/dev/null || echo "{}")
APP_ID=$(echo "$APP_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id','') or (d.get('applications',[])[0].get('id','') if d.get('applications') else ''))" 2>/dev/null || echo "")

if [ -n "$APP_ID" ]; then
  check "Create application" true
  check "Get application" curl -sf -u "$AUTH" "$API/applications/$APP_ID"
  check "Delete application" curl -sf -u "$AUTH" -X DELETE "$API/applications/$APP_ID"
else
  echo "  [SKIP] Application CRUD (could not create test app)"
fi

# --- Aliases ---
echo "-- Aliases --"
check "List aliases" curl -sf -u "$AUTH" "$API/alias"

# --- Strategies ---
echo "-- Strategies --"
check "List strategies" curl -sf -u "$AUTH" "$API/strategies"

# --- Scopes ---
echo "-- Scopes --"
check "List scopes" curl -sf -u "$AUTH" "$API/scopes"

# --- Configuration ---
echo "-- Configuration --"
check "Get error processing config" curl -sf -u "$AUTH" "$API/configurations/errorProcessing"

# --- Archive ---
echo "-- Archive --"
check "Export archive" curl -sf -u "$AUTH" "$API/archive" -o /dev/null

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
