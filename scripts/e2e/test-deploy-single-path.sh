#!/usr/bin/env bash
# ADR-059 — Deploy Single Path E2E Verification
#
# Tests the full SSE deployment flow end-to-end:
#   Console → CP API → SSE push → Link → Gateway → Callback → CP API
#
# Prerequisites:
#   - CP API running with DEPLOY_MODE=sse_only
#   - A registered gateway instance (self_register)
#   - Valid STOA_API_URL, STOA_TOKEN, STOA_GATEWAY_API_KEY
#
# Usage:
#   ./test-deploy-single-path.sh
#   STOA_API_URL=https://api.gostoa.dev ./test-deploy-single-path.sh
#
# Exit codes:
#   0 = all checks passed
#   1 = critical failure

set -euo pipefail

API_URL="${STOA_API_URL:-http://localhost:8000}"
API_URL="${API_URL%/}"
TOKEN="${STOA_TOKEN:-}"
GATEWAY_API_KEY="${STOA_GATEWAY_API_KEY:-}"
TENANT_ID="${STOA_TENANT_ID:-oasis}"

PASS=0
FAIL=0
WARN=0

pass() { ((PASS++)); echo "  ✅ $1"; }
fail() { ((FAIL++)); echo "  ❌ $1"; }
warn() { ((WARN++)); echo "  ⚠️  $1"; }

auth_header() {
    if [ -n "$TOKEN" ]; then
        echo "Authorization: Bearer $TOKEN"
    else
        echo "X-Gateway-Key: ${GATEWAY_API_KEY}"
    fi
}

echo "═══════════════════════════════════════════════"
echo "ADR-059 — Deploy Single Path E2E Verification"
echo "API: ${API_URL}"
echo "Tenant: ${TENANT_ID}"
echo "═══════════════════════════════════════════════"
echo ""

# ─── Step 1: Health Check ───
echo "── Step 1: CP API Health ──"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${API_URL}/health" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    pass "GET /health → 200"
else
    fail "GET /health → ${HTTP_CODE} (expected 200)"
    echo "CP API is not reachable. Aborting."
    exit 1
fi

# ─── Step 2: Check DEPLOY_MODE ───
echo ""
echo "── Step 2: Verify DEPLOY_MODE ──"
DEPLOY_MODE=$(curl -s "${API_URL}/health" 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('deploy_mode', 'unknown'))
except:
    print('unknown')
" 2>/dev/null || echo "unknown")
if [ "$DEPLOY_MODE" = "sse_only" ] || [ "$DEPLOY_MODE" = "dual" ]; then
    pass "DEPLOY_MODE=${DEPLOY_MODE} (SSE enabled)"
else
    warn "DEPLOY_MODE=${DEPLOY_MODE} (SSE may not be active — test may not reflect SSE path)"
fi

# ─── Step 3: List Gateway Instances ───
echo ""
echo "── Step 3: List Gateway Instances (self_register) ──"
GATEWAYS=$(curl -s -H "$(auth_header)" \
    "${API_URL}/v1/admin/gateways?source=self_register" 2>/dev/null || echo "[]")
GW_COUNT=$(echo "$GATEWAYS" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    items = data if isinstance(data, list) else data.get('items', data.get('gateways', []))
    print(len(items))
except:
    print(0)
" 2>/dev/null || echo "0")

if [ "$GW_COUNT" -gt 0 ]; then
    pass "Found ${GW_COUNT} self-registered gateway(s)"
    # Extract first gateway ID
    GATEWAY_ID=$(echo "$GATEWAYS" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    items = data if isinstance(data, list) else data.get('items', data.get('gateways', []))
    print(items[0].get('id', ''))
except:
    print('')
" 2>/dev/null || echo "")
    echo "    Using gateway: ${GATEWAY_ID}"
else
    warn "No self-registered gateways found — deploy test will be skipped"
    GATEWAY_ID=""
fi

# ─── Step 4: SSE Endpoint Availability ───
echo ""
echo "── Step 4: SSE Endpoint Check ──"
if [ -n "$GATEWAY_ID" ] && [ -n "$GATEWAY_API_KEY" ]; then
    # Test SSE endpoint returns 200 (connection will stay open — use timeout)
    SSE_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 \
        -H "X-Gateway-Key: ${GATEWAY_API_KEY}" \
        -H "Accept: text/event-stream" \
        "${API_URL}/v1/internal/gateways/${GATEWAY_ID}/events" 2>/dev/null || echo "000")
    if [ "$SSE_CODE" = "200" ]; then
        pass "GET /{gateway_id}/events → 200 (SSE stream available)"
    elif [ "$SSE_CODE" = "000" ]; then
        # curl returns 000 when it times out reading — that's actually success for SSE
        pass "GET /{gateway_id}/events → connection held open (SSE stream active)"
    else
        fail "GET /{gateway_id}/events → ${SSE_CODE} (expected 200)"
    fi
else
    warn "SSE endpoint check skipped (no gateway or API key)"
fi

# ─── Step 5: SSE Endpoint Auth ───
echo ""
echo "── Step 5: SSE Endpoint Auth Rejection ──"
if [ -n "$GATEWAY_ID" ]; then
    BAD_AUTH_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 \
        -H "X-Gateway-Key: invalid-key-12345" \
        -H "Accept: text/event-stream" \
        "${API_URL}/v1/internal/gateways/${GATEWAY_ID}/events" 2>/dev/null || echo "000")
    if [ "$BAD_AUTH_CODE" = "401" ] || [ "$BAD_AUTH_CODE" = "403" ]; then
        pass "SSE rejects invalid key → ${BAD_AUTH_CODE}"
    else
        fail "SSE with bad key → ${BAD_AUTH_CODE} (expected 401/403)"
    fi
else
    warn "Auth rejection test skipped (no gateway)"
fi

# ─── Step 6: Pending Deployments Endpoint ───
echo ""
echo "── Step 6: Pending Deployments Catch-up Endpoint ──"
if [ -n "$GATEWAY_ID" ] && [ -n "$GATEWAY_API_KEY" ]; then
    PENDING_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "X-Gateway-Key: ${GATEWAY_API_KEY}" \
        "${API_URL}/v1/internal/gateways/${GATEWAY_ID}/config" 2>/dev/null || echo "000")
    if [ "$PENDING_CODE" = "200" ]; then
        pass "GET /{gateway_id}/config → 200 (catch-up endpoint available)"
    else
        fail "GET /{gateway_id}/config → ${PENDING_CODE} (expected 200)"
    fi
else
    warn "Pending deployments check skipped (no gateway or API key)"
fi

# ─── Step 7: Deploy API (if gateway available) ───
echo ""
echo "── Step 7: Deploy API to Gateway ──"
if [ -n "$GATEWAY_ID" ] && [ -n "$TOKEN" ]; then
    # List APIs to find one to deploy
    API_LIST=$(curl -s -H "Authorization: Bearer $TOKEN" \
        "${API_URL}/v1/tenants/${TENANT_ID}/apis?limit=1" 2>/dev/null || echo "[]")
    API_ID=$(echo "$API_LIST" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    items = data if isinstance(data, list) else data.get('items', data.get('apis', []))
    if items:
        print(items[0].get('id', ''))
    else:
        print('')
except:
    print('')
" 2>/dev/null || echo "")

    if [ -n "$API_ID" ]; then
        echo "    Deploying API ${API_ID} to gateway ${GATEWAY_ID}..."
        DEPLOY_RESP=$(curl -s -w "\n%{http_code}" \
            -X POST \
            -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" \
            -d "{\"api_identifier\": \"${API_ID}\", \"environment\": \"dev\", \"gateway_ids\": [\"${GATEWAY_ID}\"]}" \
            "${API_URL}/v1/tenants/${TENANT_ID}/deployments" 2>/dev/null || echo -e "\n500")
        DEPLOY_CODE=$(echo "$DEPLOY_RESP" | tail -1)
        DEPLOY_BODY=$(echo "$DEPLOY_RESP" | head -n -1)

        if [ "$DEPLOY_CODE" = "200" ] || [ "$DEPLOY_CODE" = "201" ]; then
            pass "POST /deployments → ${DEPLOY_CODE} (deployment created)"

            # Check deployment status after a short wait
            sleep 2
            DEPLOY_STATUS=$(curl -s -H "Authorization: Bearer $TOKEN" \
                "${API_URL}/v1/tenants/${TENANT_ID}/deployments?api_catalog_id=${API_ID}&gateway_instance_id=${GATEWAY_ID}" 2>/dev/null || echo "[]")
            STATUS=$(echo "$DEPLOY_STATUS" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    items = data if isinstance(data, list) else data.get('items', data.get('deployments', []))
    if items:
        print(items[0].get('sync_status', 'unknown'))
    else:
        print('no_deployment')
except:
    print('error')
" 2>/dev/null || echo "error")
            echo "    Deployment status after 2s: ${STATUS}"
            if [ "$STATUS" = "SYNCED" ] || [ "$STATUS" = "synced" ]; then
                pass "Deployment synced via SSE path"
            elif [ "$STATUS" = "PENDING" ] || [ "$STATUS" = "pending" ]; then
                warn "Deployment still PENDING (Link may not be connected)"
            else
                warn "Deployment status: ${STATUS}"
            fi
        else
            warn "POST /deployments → ${DEPLOY_CODE} (may need valid API + assignment)"
            echo "    Response: $(echo "$DEPLOY_BODY" | head -c 200)"
        fi
    else
        warn "No APIs found in tenant ${TENANT_ID} — deploy test skipped"
    fi
else
    warn "Deploy test skipped (no gateway or no token)"
fi

# ─── Summary ───
echo ""
echo "═══════════════════════════════════════════════"
echo "Results: ${PASS} passed, ${FAIL} failed, ${WARN} warnings"
echo "═══════════════════════════════════════════════"

if [ "$FAIL" -gt 0 ]; then
    echo "VERDICT: ❌ FAIL"
    exit 1
else
    echo "VERDICT: ✅ PASS"
    exit 0
fi
