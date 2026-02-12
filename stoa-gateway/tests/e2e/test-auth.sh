#!/usr/bin/env bash
# E2E: Auth endpoint tests
# Scenarios 4-6: admin auth with missing/invalid/valid tokens
set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://localhost:18080}"
ADMIN_TOKEN="${ADMIN_TOKEN:-test-admin-token}"
PASS=0
FAIL=0

pass() { PASS=$((PASS + 1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL + 1)); echo "  FAIL: $1 — $2"; }

echo "=== Auth E2E Tests ==="

# Scenario 4: Admin endpoint without token → 401
status=$(curl -s -o /dev/null -w '%{http_code}' "$GATEWAY_URL/admin/health")
if [ "$status" = "401" ]; then
  pass "GET /admin/health (no token) → 401"
else
  fail "GET /admin/health (no token)" "expected 401, got $status"
fi

# Scenario 5: Admin endpoint with valid token → 200
status=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $ADMIN_TOKEN" "$GATEWAY_URL/admin/health")
if [ "$status" = "200" ]; then
  pass "GET /admin/health (valid token) → 200"
else
  fail "GET /admin/health (valid token)" "expected 200, got $status"
fi

# Scenario 6: Admin endpoint with invalid token → 401
status=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer wrong-token" "$GATEWAY_URL/admin/health")
if [ "$status" = "401" ]; then
  pass "GET /admin/health (invalid token) → 401"
else
  fail "GET /admin/health (invalid token)" "expected 401, got $status"
fi

echo ""
echo "Auth: $PASS passed, $FAIL failed"
exit "$FAIL"
