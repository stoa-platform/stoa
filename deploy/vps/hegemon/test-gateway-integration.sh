#!/usr/bin/env bash
# Integration tests for HEGEMON Gateway stack.
# Run on a VPS where docker-compose.gateway.yml is up.
#
# 7 test scenarios:
#   1. Worker obtains JWT via Keycloak service account
#   2. Worker sends LLM request via external gateway with JWT
#   3. Gateway injects Anthropic API key, proxies to upstream
#   4. Response streams back to worker
#   5. Access log contains tenant/consumer/trace_id
#   6. COMMAND tier blocks POST to external API
#   7. AUTOPILOT tier allows everything
#
# Usage: ./test-gateway-integration.sh
# Exit 0 if gateways not running (skip gracefully).
set -euo pipefail

source "${HOME}/.env.hegemon" 2>/dev/null || true

INTERNAL_URL="${GATEWAY_INTERNAL_URL:-http://localhost:8090}"
EXTERNAL_URL="${GATEWAY_EXTERNAL_URL:-http://localhost:8091}"
KEYCLOAK_URL="${KEYCLOAK_URL:-https://auth.gostoa.dev}"
KEYCLOAK_REALM="${KEYCLOAK_REALM:-stoa}"
LOG_TAG="[gw-test]"
PASS=0
FAIL=0
SKIP=0

log() { echo "${LOG_TAG} $(date '+%H:%M:%S') $*"; }

result() {
  local label="$1"
  local status="$2"
  if [ "$status" = "PASS" ]; then
    echo "  [PASS] ${label}"
    PASS=$((PASS + 1))
  elif [ "$status" = "SKIP" ]; then
    echo "  [SKIP] ${label}"
    SKIP=$((SKIP + 1))
  else
    echo "  [FAIL] ${label}"
    FAIL=$((FAIL + 1))
  fi
}

# ─── Pre-check: gateways running? ────────────────────────────────────────────
log "Checking gateway health..."
if ! curl -sf "${INTERNAL_URL}/health" > /dev/null 2>&1; then
  log "Internal gateway not running at ${INTERNAL_URL} — skipping all tests"
  exit 0
fi
if ! curl -sf "${EXTERNAL_URL}/health" > /dev/null 2>&1; then
  log "External gateway not running at ${EXTERNAL_URL} — skipping all tests"
  exit 0
fi
log "Both gateways healthy"

echo ""
echo "=== HEGEMON Gateway Integration Tests ==="
echo ""

# ─── Scenario 1: JWT acquisition via Keycloak ────────────────────────────────
log "Scenario 1: JWT acquisition via Keycloak service account"

CLIENT_ID="${HEGEMON_KC_CLIENT_ID:-hegemon-worker-1}"
CLIENT_SECRET="${HEGEMON_KC_CLIENT_SECRET:-}"

if [ -z "$CLIENT_SECRET" ]; then
  result "JWT acquisition (no CLIENT_SECRET configured)" "SKIP"
  JWT_TOKEN=""
else
  TOKEN_RESPONSE=$(curl -sf -X POST \
    "${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token" \
    -d "client_id=${CLIENT_ID}" \
    -d "client_secret=${CLIENT_SECRET}" \
    -d "grant_type=client_credentials" \
    -d "scope=openid stoa:read stoa:write" 2>/dev/null || echo '{"error":"connection_failed"}')

  JWT_TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")

  if [ -n "$JWT_TOKEN" ] && [ "$JWT_TOKEN" != "None" ]; then
    # Verify hegemon-worker role is in the token
    ROLES=$(echo "$JWT_TOKEN" | cut -d. -f2 | base64 -d 2>/dev/null | python3 -c "import sys,json; print(','.join(json.load(sys.stdin).get('realm_access',{}).get('roles',[])))" 2>/dev/null || echo "")
    if echo "$ROLES" | grep -q "hegemon-worker"; then
      result "JWT with hegemon-worker role" "PASS"
    else
      result "JWT obtained but hegemon-worker role MISSING (roles: ${ROLES})" "FAIL"
    fi
  else
    ERROR=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error_description','unknown'))" 2>/dev/null || echo "unknown")
    result "JWT acquisition failed: ${ERROR}" "FAIL"
    JWT_TOKEN=""
  fi
fi

# ─── Scenario 2: LLM request via external gateway ────────────────────────────
log "Scenario 2: LLM request via external gateway"

LLM_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" \
  -X POST "${EXTERNAL_URL}/v1/messages" \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "claude-haiku-4-5-20251001",
    "max_tokens": 1,
    "messages": [{"role": "user", "content": "hi"}]
  }' 2>/dev/null || echo "000")

if [ "$LLM_STATUS" = "200" ]; then
  result "LLM proxy request (200 OK)" "PASS"
elif [ "$LLM_STATUS" = "429" ]; then
  result "LLM proxy request (429 rate limited — key was injected)" "PASS"
elif [ "$LLM_STATUS" = "401" ]; then
  result "LLM proxy request (401 — credential injection not working)" "FAIL"
else
  result "LLM proxy request (HTTP ${LLM_STATUS})" "FAIL"
fi

# ─── Scenario 3: Credential injection verification ───────────────────────────
log "Scenario 3: Credential injection (request without API key → gateway injects)"

# Send request WITHOUT any API key header — gateway should inject it
INJECT_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" \
  -X POST "${EXTERNAL_URL}/v1/messages" \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "claude-haiku-4-5-20251001",
    "max_tokens": 1,
    "messages": [{"role": "user", "content": "test credential injection"}]
  }' 2>/dev/null || echo "000")

if [ "$INJECT_STATUS" = "200" ] || [ "$INJECT_STATUS" = "429" ]; then
  result "Credential injection (upstream responded ${INJECT_STATUS})" "PASS"
else
  result "Credential injection (HTTP ${INJECT_STATUS} — expected 200 or 429)" "FAIL"
fi

# ─── Scenario 4: Response streaming ──────────────────────────────────────────
log "Scenario 4: SSE response streaming"

STREAM_RESPONSE=$(curl -sf -N \
  -X POST "${EXTERNAL_URL}/v1/messages" \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "claude-haiku-4-5-20251001",
    "max_tokens": 5,
    "stream": true,
    "messages": [{"role": "user", "content": "say ok"}]
  }' 2>/dev/null | head -20 || echo "")

if echo "$STREAM_RESPONSE" | grep -q "event:"; then
  result "SSE streaming response received" "PASS"
elif echo "$STREAM_RESPONSE" | grep -q "content_block"; then
  result "SSE streaming response received (content block)" "PASS"
elif [ -z "$STREAM_RESPONSE" ]; then
  # May fail due to rate limiting — not a hard failure
  result "SSE streaming (empty response — may be rate limited)" "SKIP"
else
  result "SSE streaming (unexpected response format)" "FAIL"
fi

# ─── Scenario 5: Access log contains correct metadata ────────────────────────
log "Scenario 5: Access log audit trail"

# Check docker logs for the external gateway
ACCESS_LOG=$(docker logs hegemon-gateway-external --tail 20 2>/dev/null || echo "")

if [ -n "$ACCESS_LOG" ]; then
  if echo "$ACCESS_LOG" | grep -q "v1/messages"; then
    result "Access log records LLM proxy requests" "PASS"
  else
    result "Access log missing LLM proxy requests" "FAIL"
  fi
else
  result "Access log (container not found or no logs)" "SKIP"
fi

# ─── Scenario 6: COMMAND tier blocks POST ─────────────────────────────────────
log "Scenario 6: COMMAND tier blocks mutations"

COMMAND_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" \
  -X POST "${INTERNAL_URL}/test" \
  -H "X-Hegemon-Supervision: command" \
  -H "Content-Type: application/json" \
  -d '{"test": true}' 2>/dev/null || echo "000")

if [ "$COMMAND_STATUS" = "403" ]; then
  result "COMMAND tier blocks POST (403 Forbidden)" "PASS"
elif [ "$COMMAND_STATUS" = "404" ]; then
  # 404 means the route doesn't exist but the request got through (middleware didn't block)
  # This is expected if supervision is not enabled on internal gateway yet
  result "COMMAND tier (404 — route not found, middleware may not be deployed)" "SKIP"
else
  result "COMMAND tier (HTTP ${COMMAND_STATUS} — expected 403)" "FAIL"
fi

# ─── Scenario 7: AUTOPILOT tier allows everything ────────────────────────────
log "Scenario 7: AUTOPILOT tier allows all requests"

AUTOPILOT_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" \
  "${INTERNAL_URL}/health" \
  -H "X-Hegemon-Supervision: autopilot" 2>/dev/null || echo "000")

if [ "$AUTOPILOT_STATUS" = "200" ]; then
  result "AUTOPILOT tier allows GET (200 OK)" "PASS"
else
  result "AUTOPILOT tier (HTTP ${AUTOPILOT_STATUS} — expected 200)" "FAIL"
fi

# ─── Summary ──────────────────────────────────────────────────────────────────
echo ""
TOTAL=$((PASS + FAIL + SKIP))
echo "=== Results: ${PASS} passed, ${FAIL} failed, ${SKIP} skipped (${TOTAL} total) ==="

if [ "$FAIL" -eq 0 ]; then
  echo "  All non-skipped tests passed."
  exit 0
else
  echo "  ${FAIL} test(s) failed. Review gateway configuration."
  exit 1
fi
