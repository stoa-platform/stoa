#!/usr/bin/env bash
# E2E: OAuth discovery endpoint tests
# Scenarios 13-15: well-known endpoints (RFC 9728, 8414, OIDC)
set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://localhost:18080}"
PASS=0
FAIL=0

pass() { PASS=$((PASS + 1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL + 1)); echo "  FAIL: $1 — $2"; }

echo "=== OAuth E2E Tests ==="

# Scenario 13: GET /.well-known/oauth-protected-resource returns RFC 9728 JSON
status=$(curl -s -o /dev/null -w '%{http_code}' "$GATEWAY_URL/.well-known/oauth-protected-resource")
body=$(curl -s "$GATEWAY_URL/.well-known/oauth-protected-resource")
if [ "$status" = "200" ] && echo "$body" | grep -q '"resource"'; then
  pass "GET /.well-known/oauth-protected-resource → RFC 9728"
else
  fail "GET /.well-known/oauth-protected-resource" "status=$status body=$body"
fi

# Scenario 14: GET /.well-known/oauth-authorization-server returns RFC 8414 JSON
status=$(curl -s -o /dev/null -w '%{http_code}' "$GATEWAY_URL/.well-known/oauth-authorization-server")
body=$(curl -s "$GATEWAY_URL/.well-known/oauth-authorization-server")
if [ "$status" = "200" ] && echo "$body" | grep -q '"issuer"'; then
  pass "GET /.well-known/oauth-authorization-server → RFC 8414"
else
  fail "GET /.well-known/oauth-authorization-server" "status=$status body=$body"
fi

# Scenario 15: GET /.well-known/openid-configuration returns 503 (no Keycloak URL)
status=$(curl -s -o /dev/null -w '%{http_code}' "$GATEWAY_URL/.well-known/openid-configuration")
if [ "$status" = "503" ]; then
  pass "GET /.well-known/openid-configuration → 503 (no Keycloak)"
else
  fail "GET /.well-known/openid-configuration" "expected 503, got $status"
fi

echo ""
echo "OAuth: $PASS passed, $FAIL failed"
exit "$FAIL"
