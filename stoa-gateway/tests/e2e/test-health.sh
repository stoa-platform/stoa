#!/usr/bin/env bash
# E2E: Health endpoint tests
# Scenarios 1-3: /health, /ready, /admin/health
set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://localhost:18080}"
ADMIN_TOKEN="${ADMIN_TOKEN:-test-admin-token}"
PASS=0
FAIL=0

pass() { PASS=$((PASS + 1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL + 1)); echo "  FAIL: $1 — $2"; }

echo "=== Health E2E Tests ==="

# Scenario 1: GET /health returns 200 + "OK"
status=$(curl -s -o /dev/null -w '%{http_code}' "$GATEWAY_URL/health")
body=$(curl -s "$GATEWAY_URL/health")
if [ "$status" = "200" ] && [ "$body" = "OK" ]; then
  pass "GET /health → 200 OK"
else
  fail "GET /health" "status=$status body=$body"
fi

# Scenario 2: GET /ready returns 200 + "READY"
status=$(curl -s -o /dev/null -w '%{http_code}' "$GATEWAY_URL/ready")
body=$(curl -s "$GATEWAY_URL/ready")
if [ "$status" = "200" ] && [ "$body" = "READY" ]; then
  pass "GET /ready → 200 READY"
else
  fail "GET /ready" "status=$status body=$body"
fi

# Scenario 3: GET /admin/health with bearer returns 200 + JSON
status=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $ADMIN_TOKEN" "$GATEWAY_URL/admin/health")
body=$(curl -s -H "Authorization: Bearer $ADMIN_TOKEN" "$GATEWAY_URL/admin/health")
if [ "$status" = "200" ] && echo "$body" | grep -q '"status"'; then
  pass "GET /admin/health (bearer) → 200 JSON"
else
  fail "GET /admin/health (bearer)" "status=$status body=$body"
fi

echo ""
echo "Health: $PASS passed, $FAIL failed"
exit "$FAIL"
