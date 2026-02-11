#!/usr/bin/env bash
# E2E: MCP protocol endpoint tests
# Scenarios 7-12: discovery, capabilities, tools/list, tools/call, REST tools
set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://localhost:18080}"
PASS=0
FAIL=0

pass() { PASS=$((PASS + 1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL + 1)); echo "  FAIL: $1 — $2"; }

echo "=== MCP E2E Tests ==="

# Scenario 7: GET /mcp returns discovery JSON
status=$(curl -s -o /dev/null -w '%{http_code}' "$GATEWAY_URL/mcp")
body=$(curl -s "$GATEWAY_URL/mcp")
if [ "$status" = "200" ] && echo "$body" | grep -q '"server"'; then
  pass "GET /mcp → discovery JSON"
else
  fail "GET /mcp" "status=$status body=$body"
fi

# Scenario 8: GET /mcp/capabilities returns capabilities
status=$(curl -s -o /dev/null -w '%{http_code}' "$GATEWAY_URL/mcp/capabilities")
body=$(curl -s "$GATEWAY_URL/mcp/capabilities")
if [ "$status" = "200" ] && echo "$body" | grep -q '"capabilities"'; then
  pass "GET /mcp/capabilities → capabilities JSON"
else
  fail "GET /mcp/capabilities" "status=$status body=$body"
fi

# Scenario 9: POST /mcp/tools/list returns tools array
status=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H "Content-Type: application/json" -d '{}' "$GATEWAY_URL/mcp/tools/list")
body=$(curl -s -X POST -H "Content-Type: application/json" -d '{}' "$GATEWAY_URL/mcp/tools/list")
if [ "$status" = "200" ] && echo "$body" | grep -q '"tools"'; then
  pass "POST /mcp/tools/list → tools array"
else
  fail "POST /mcp/tools/list" "status=$status body=$body"
fi

# Scenario 10: POST /mcp/tools/call unknown tool returns error
status=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H "Content-Type: application/json" -d '{"name":"nonexistent","arguments":{}}' "$GATEWAY_URL/mcp/tools/call")
body=$(curl -s -X POST -H "Content-Type: application/json" -d '{"name":"nonexistent","arguments":{}}' "$GATEWAY_URL/mcp/tools/call")
if echo "$body" | grep -q '"isError"'; then
  pass "POST /mcp/tools/call (unknown) → error response"
else
  fail "POST /mcp/tools/call (unknown)" "status=$status body=$body"
fi

# Scenario 11: GET /mcp/v1/tools returns REST tool list
status=$(curl -s -o /dev/null -w '%{http_code}' "$GATEWAY_URL/mcp/v1/tools")
body=$(curl -s "$GATEWAY_URL/mcp/v1/tools")
if [ "$status" = "200" ]; then
  pass "GET /mcp/v1/tools → 200"
else
  fail "GET /mcp/v1/tools" "status=$status body=$body"
fi

# Scenario 12: POST /mcp/v1/tools/invoke unknown returns error
status=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H "Content-Type: application/json" -d '{"tool":"nonexistent","arguments":{}}' "$GATEWAY_URL/mcp/v1/tools/invoke")
if [ "$status" != "200" ] || curl -s -X POST -H "Content-Type: application/json" -d '{"tool":"nonexistent","arguments":{}}' "$GATEWAY_URL/mcp/v1/tools/invoke" | grep -q -i "error\|not.found"; then
  pass "POST /mcp/v1/tools/invoke (unknown) → error"
else
  fail "POST /mcp/v1/tools/invoke (unknown)" "status=$status"
fi

echo ""
echo "MCP: $PASS passed, $FAIL failed"
exit "$FAIL"
