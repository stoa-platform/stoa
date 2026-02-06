#!/bin/sh
# =============================================================================
# STOA Platform - Cross-Tenant Isolation Test (CAB-1114 Phase 3)
# =============================================================================
# Verifies that OpenSearch multi-tenant OIDC security works correctly:
#   - Tenant users can only see their own logs
#   - Cross-tenant access is denied
#   - Platform admins (cpi-admin) can see all logs
#
# Prerequisites:
#   - docker compose up -d (all services healthy)
#   - OpenSearch security enabled + OIDC configured
#
# Usage:
#   sh test/test-tenant-isolation.sh
# =============================================================================

set -e

OS_HOST="https://localhost:9200"
KC_HOST="http://localhost/auth"
KC_REALM="stoa"
CLIENT_ID="opensearch-dashboards"
CLIENT_SECRET="opensearch-dashboards-dev-secret"

PASS=0
FAIL=0

log()  { echo "[TEST] $1"; }
pass() { PASS=$((PASS + 1)); echo "[PASS] $1"; }
fail() { FAIL=$((FAIL + 1)); echo "[FAIL] $1"; }

# ---------------------------------------------------------------------------
# Helper: get JWT access token for a user
# ---------------------------------------------------------------------------
get_token() {
  local username="$1"
  local password="$2"
  curl -sf -X POST \
    "${KC_HOST}/realms/${KC_REALM}/protocol/openid-connect/token" \
    -d "grant_type=password" \
    -d "client_id=${CLIENT_ID}" \
    -d "client_secret=${CLIENT_SECRET}" \
    -d "username=${username}" \
    -d "password=${password}" \
    -d "scope=openid" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4
}

# ---------------------------------------------------------------------------
# Helper: query OpenSearch with a JWT token
# Returns: HTTP status code + doc count
# ---------------------------------------------------------------------------
query_index() {
  local token="$1"
  local index_pattern="$2"
  curl -sk -o /tmp/os_response -w "%{http_code}" \
    -H "Authorization: Bearer ${token}" \
    "${OS_HOST}/${index_pattern}/_count" 2>/dev/null
}

get_count() {
  grep -o '"count":[0-9]*' /tmp/os_response 2>/dev/null | cut -d: -f2 || echo "0"
}

echo ""
echo "============================================="
echo "CAB-1114 Phase 3 — Tenant Isolation Tests"
echo "============================================="
echo ""

# ---------------------------------------------------------------------------
# Test 1: parzival (oasis-gunters) can see oasis-gunters logs
# ---------------------------------------------------------------------------
log "Getting token for parzival (oasis-gunters, tenant-admin)..."
TOKEN_PARZIVAL=$(get_token "parzival" "copperkeystart")
if [ -z "$TOKEN_PARZIVAL" ]; then
  fail "Cannot get token for parzival (is Keycloak running?)"
else
  log "Token obtained for parzival"

  HTTP_CODE=$(query_index "$TOKEN_PARZIVAL" "stoa-logs-oasis-gunters-*")
  COUNT=$(get_count)
  if [ "$HTTP_CODE" = "200" ] && [ "$COUNT" -gt 0 ] 2>/dev/null; then
    pass "parzival CAN see oasis-gunters logs ($COUNT docs)"
  else
    fail "parzival CANNOT see oasis-gunters logs (HTTP $HTTP_CODE, count=$COUNT)"
  fi

  # Test 2: parzival CANNOT see ioi-sixers logs
  HTTP_CODE=$(query_index "$TOKEN_PARZIVAL" "stoa-logs-ioi-sixers-*")
  COUNT=$(get_count)
  if [ "$HTTP_CODE" = "403" ] || ([ "$HTTP_CODE" = "200" ] && [ "$COUNT" = "0" ]); then
    pass "parzival CANNOT see ioi-sixers logs (HTTP $HTTP_CODE, count=$COUNT)"
  else
    fail "parzival CAN see ioi-sixers logs (HTTP $HTTP_CODE, count=$COUNT) — ISOLATION BREACH!"
  fi
fi

# ---------------------------------------------------------------------------
# Test 3: sorrento (ioi-sixers) can see ioi-sixers logs
# ---------------------------------------------------------------------------
log "Getting token for sorrento (ioi-sixers, tenant-admin)..."
TOKEN_SORRENTO=$(get_token "sorrento" "ioi101")
if [ -z "$TOKEN_SORRENTO" ]; then
  fail "Cannot get token for sorrento (is Keycloak running?)"
else
  log "Token obtained for sorrento"

  HTTP_CODE=$(query_index "$TOKEN_SORRENTO" "stoa-logs-ioi-sixers-*")
  COUNT=$(get_count)
  if [ "$HTTP_CODE" = "200" ] && [ "$COUNT" -gt 0 ] 2>/dev/null; then
    pass "sorrento CAN see ioi-sixers logs ($COUNT docs)"
  else
    fail "sorrento CANNOT see ioi-sixers logs (HTTP $HTTP_CODE, count=$COUNT)"
  fi

  # Test 4: sorrento CANNOT see oasis-gunters logs
  HTTP_CODE=$(query_index "$TOKEN_SORRENTO" "stoa-logs-oasis-gunters-*")
  COUNT=$(get_count)
  if [ "$HTTP_CODE" = "403" ] || ([ "$HTTP_CODE" = "200" ] && [ "$COUNT" = "0" ]); then
    pass "sorrento CANNOT see oasis-gunters logs (HTTP $HTTP_CODE, count=$COUNT)"
  else
    fail "sorrento CAN see oasis-gunters logs (HTTP $HTTP_CODE, count=$COUNT) — ISOLATION BREACH!"
  fi
fi

# ---------------------------------------------------------------------------
# Test 5+6: halliday (cpi-admin) can see ALL logs
# ---------------------------------------------------------------------------
log "Getting token for halliday (gregarious-games, cpi-admin)..."
TOKEN_HALLIDAY=$(get_token "halliday" "readyplayerone")
if [ -z "$TOKEN_HALLIDAY" ]; then
  fail "Cannot get token for halliday (is Keycloak running?)"
else
  log "Token obtained for halliday"

  HTTP_CODE=$(query_index "$TOKEN_HALLIDAY" "stoa-logs-oasis-gunters-*")
  COUNT_OG=$(get_count)
  if [ "$HTTP_CODE" = "200" ] && [ "$COUNT_OG" -gt 0 ] 2>/dev/null; then
    pass "halliday CAN see oasis-gunters logs ($COUNT_OG docs)"
  else
    fail "halliday CANNOT see oasis-gunters logs (HTTP $HTTP_CODE)"
  fi

  HTTP_CODE=$(query_index "$TOKEN_HALLIDAY" "stoa-logs-ioi-sixers-*")
  COUNT_IOI=$(get_count)
  if [ "$HTTP_CODE" = "200" ] && [ "$COUNT_IOI" -gt 0 ] 2>/dev/null; then
    pass "halliday CAN see ioi-sixers logs ($COUNT_IOI docs)"
  else
    fail "halliday CANNOT see ioi-sixers logs (HTTP $HTTP_CODE)"
  fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "============================================="
echo "Results: ${PASS} passed, ${FAIL} failed"
echo "============================================="

if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "TENANT ISOLATION: FAILED"
  exit 1
else
  echo ""
  echo "TENANT ISOLATION: PASSED"
  exit 0
fi
