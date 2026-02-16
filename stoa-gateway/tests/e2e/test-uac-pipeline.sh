#!/usr/bin/env bash
# E2E: UAC Contract Deployment Pipeline smoke test
# Tests the full contract lifecycle: create → verify → routes → tools → delete
#
# Usage:
#   GATEWAY_URL=http://localhost:8080 ./tests/e2e/test-uac-pipeline.sh
#   GATEWAY_URL=https://mcp.gostoa.dev ADMIN_TOKEN=xxx ./tests/e2e/test-uac-pipeline.sh
set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://localhost:18080}"
ADMIN_TOKEN="${ADMIN_TOKEN:-}"
CONTRACT_NAME="smoke-uac-$(date +%s)"
TENANT_ID="smoke-test"
CONTRACT_KEY="${TENANT_ID}:${CONTRACT_NAME}"
PASS=0
FAIL=0
TOTAL=0

# --- Helpers ---

pass() { PASS=$((PASS + 1)); TOTAL=$((TOTAL + 1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL + 1)); TOTAL=$((TOTAL + 1)); echo "  FAIL: $1 — $2"; }

auth_header() {
  if [ -n "$ADMIN_TOKEN" ]; then
    echo "-H" "Authorization: Bearer $ADMIN_TOKEN"
  fi
}

echo "=== UAC Contract Pipeline Smoke Test ==="
echo "  Gateway: $GATEWAY_URL"
echo "  Contract: $CONTRACT_NAME"
echo "  Key: $CONTRACT_KEY"
echo ""

# --- Scenario 1: Health check ---

status=$(curl -s -o /dev/null -w '%{http_code}' "$GATEWAY_URL/health")
if [ "$status" = "200" ]; then
  pass "Gateway health check"
else
  fail "Gateway health check" "status=$status"
  echo "Gateway not reachable. Aborting."
  exit 1
fi

# --- Scenario 2: Create UAC contract ---

CONTRACT_PAYLOAD=$(cat <<EOF
{
  "name": "$CONTRACT_NAME",
  "version": "1.0.0",
  "tenant_id": "$TENANT_ID",
  "display_name": "Smoke Test Contract",
  "description": "Created by UAC pipeline smoke test — safe to delete",
  "classification": "H",
  "endpoints": [
    {
      "path": "/smoke/health",
      "methods": ["GET"],
      "backend_url": "https://httpbin.org/get",
      "operation_id": "smoke_health"
    },
    {
      "path": "/smoke/echo",
      "methods": ["POST"],
      "backend_url": "https://httpbin.org/post",
      "operation_id": "smoke_echo",
      "input_schema": {"type": "object", "properties": {"msg": {"type": "string"}}}
    }
  ],
  "required_policies": ["audit_logging"],
  "status": "published"
}
EOF
)

status=$(curl -s -o /dev/null -w '%{http_code}' \
  -X POST \
  -H "Content-Type: application/json" \
  $(auth_header) \
  -d "$CONTRACT_PAYLOAD" \
  "$GATEWAY_URL/admin/contracts")
if [ "$status" = "200" ] || [ "$status" = "201" ]; then
  pass "POST /admin/contracts → $status"
else
  fail "POST /admin/contracts" "status=$status"
fi

# --- Scenario 3: List contracts and verify ours exists ---

body=$(curl -s $(auth_header) "$GATEWAY_URL/admin/contracts")
if echo "$body" | grep -q "$CONTRACT_NAME"; then
  pass "GET /admin/contracts contains $CONTRACT_NAME"
else
  fail "GET /admin/contracts" "contract not found in response"
fi

# --- Scenario 4: Verify REST routes were generated ---

status=$(curl -s -o /dev/null -w '%{http_code}' $(auth_header) "$GATEWAY_URL/admin/apis")
if [ "$status" = "200" ]; then
  pass "GET /admin/apis → 200 (route registry accessible)"
else
  fail "GET /admin/apis" "status=$status"
fi

# --- Scenario 5: Verify MCP tools were generated ---

status=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H "Content-Type: application/json" -d '{}' "$GATEWAY_URL/mcp/tools/list")
if [ "$status" = "200" ]; then
  pass "POST /mcp/tools/list → 200 (tool registry accessible)"
else
  fail "POST /mcp/tools/list" "status=$status"
fi

# --- Scenario 6: Get specific contract by key ---

status=$(curl -s -o /dev/null -w '%{http_code}' $(auth_header) "$GATEWAY_URL/admin/contracts/$CONTRACT_KEY")
if [ "$status" = "200" ]; then
  pass "GET /admin/contracts/$CONTRACT_KEY → 200"
else
  fail "GET /admin/contracts/$CONTRACT_KEY" "status=$status"
fi

# --- Scenario 7: Delete contract by key ---

status=$(curl -s -o /dev/null -w '%{http_code}' \
  -X DELETE \
  $(auth_header) \
  "$GATEWAY_URL/admin/contracts/$CONTRACT_KEY")
if [ "$status" = "200" ] || [ "$status" = "204" ]; then
  pass "DELETE /admin/contracts/$CONTRACT_KEY → $status"
else
  fail "DELETE /admin/contracts/$CONTRACT_KEY" "status=$status"
fi

# --- Scenario 8: Verify contract deleted ---

body=$(curl -s $(auth_header) "$GATEWAY_URL/admin/contracts")
if echo "$body" | grep -q "$CONTRACT_NAME"; then
  fail "Contract still exists after delete" "found in GET /admin/contracts"
else
  pass "Contract removed from GET /admin/contracts"
fi

# --- Scenario 9: Delete idempotent (404 = success) ---

status=$(curl -s -o /dev/null -w '%{http_code}' \
  -X DELETE \
  $(auth_header) \
  "$GATEWAY_URL/admin/contracts/$CONTRACT_KEY")
if [ "$status" = "200" ] || [ "$status" = "204" ] || [ "$status" = "404" ]; then
  pass "DELETE idempotent (re-delete) → $status"
else
  fail "DELETE idempotent" "unexpected status=$status"
fi

# --- Summary ---

echo ""
echo "=== Results: $PASS/$TOTAL passed, $FAIL failed ==="
exit "$FAIL"
