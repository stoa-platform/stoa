#!/usr/bin/env bash
# MCP OAuth 2.1 Flow Verification (RFC 9728 + RFC 8414)
#
# Tests the full OAuth discovery chain as an MCP client (Claude.ai) would execute it.
# Run after deployment to verify the flow end-to-end.
#
# Usage:
#   ./test-mcp-oauth-flow.sh                          # default: https://mcp.gostoa.dev
#   ./test-mcp-oauth-flow.sh https://mcp.staging.dev  # custom gateway URL
#   MCP_GATEWAY_URL=https://mcp.gostoa.dev ./test-mcp-oauth-flow.sh
#
# Exit codes:
#   0 = all checks passed
#   1 = critical failure (flow is broken)

set -euo pipefail

GATEWAY_URL="${1:-${MCP_GATEWAY_URL:-https://mcp.gostoa.dev}}"
GATEWAY_URL="${GATEWAY_URL%/}"  # trim trailing slash

PASS=0
FAIL=0
WARN=0

pass() { ((PASS++)); echo "  ✅ $1"; }
fail() { ((FAIL++)); echo "  ❌ $1"; }
warn() { ((WARN++)); echo "  ⚠️  $1"; }

echo "═══════════════════════════════════════════"
echo "MCP OAuth 2.1 Flow Verification"
echo "Gateway: ${GATEWAY_URL}"
echo "═══════════════════════════════════════════"
echo ""

# ─── Step 1: Health ───
echo "── Step 1: Health Check ──"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${GATEWAY_URL}/health" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
  pass "GET /health → 200"
else
  fail "GET /health → ${HTTP_CODE} (expected 200)"
fi

# ─── Step 2: MCP Discovery ───
echo ""
echo "── Step 2: MCP Discovery ──"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${GATEWAY_URL}/mcp" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
  pass "GET /mcp → 200 (discovery)"
else
  fail "GET /mcp → ${HTTP_CODE} (expected 200)"
fi

# ─── Step 3: OAuth Challenge on Protected Method ───
echo ""
echo "── Step 3: OAuth 2.1 Challenge (RFC 9728) ──"
RESP=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "${GATEWAY_URL}/mcp/sse" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}' 2>/dev/null || echo "HTTP_CODE:000")

HTTP_CODE=$(echo "$RESP" | grep "HTTP_CODE:" | sed 's/HTTP_CODE://')
if [ "$HTTP_CODE" = "401" ]; then
  pass "POST /mcp/sse tools/list → 401 (auth required)"
else
  fail "POST /mcp/sse tools/list → ${HTTP_CODE} (expected 401)"
fi

# Check WWW-Authenticate header
WWW_AUTH=$(curl -s -D - -o /dev/null -X POST "${GATEWAY_URL}/mcp/sse" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}' 2>/dev/null | grep -i "www-authenticate" || echo "")
if echo "$WWW_AUTH" | grep -qi "Bearer.*resource_metadata"; then
  pass "WWW-Authenticate: Bearer resource_metadata present"
else
  fail "WWW-Authenticate header missing or malformed: ${WWW_AUTH}"
fi

# ─── Step 4: Public Methods Work Without Auth ───
echo ""
echo "── Step 4: Public Methods (No Auth) ──"
INIT_RESP=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "${GATEWAY_URL}/mcp/sse" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"initialize","id":1,"params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"mcp-flow-test","version":"1.0"}}}' 2>/dev/null || echo "HTTP_CODE:000")

INIT_CODE=$(echo "$INIT_RESP" | grep "HTTP_CODE:" | sed 's/HTTP_CODE://')
if [ "$INIT_CODE" = "200" ]; then
  pass "POST /mcp/sse initialize → 200 (public method OK)"
else
  fail "POST /mcp/sse initialize → ${INIT_CODE} (expected 200)"
fi

# ─── Step 5: Protected Resource Metadata (RFC 9728) ───
echo ""
echo "── Step 5: Protected Resource Metadata ──"
PRM=$(curl -s "${GATEWAY_URL}/.well-known/oauth-protected-resource" 2>/dev/null || echo "{}")
PRM_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${GATEWAY_URL}/.well-known/oauth-protected-resource" 2>/dev/null || echo "000")

if [ "$PRM_CODE" = "200" ]; then
  pass "GET /.well-known/oauth-protected-resource → 200"
else
  fail "GET /.well-known/oauth-protected-resource → ${PRM_CODE} (expected 200)"
fi

# Check authorization_servers points to gateway (not Keycloak)
AUTH_SERVER=$(echo "$PRM" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('authorization_servers',[''])[0])" 2>/dev/null || echo "")
if echo "$AUTH_SERVER" | grep -q "${GATEWAY_URL}"; then
  pass "authorization_servers → ${AUTH_SERVER} (points to gateway)"
elif echo "$AUTH_SERVER" | grep -qi "auth\.\|keycloak\|realms/"; then
  fail "authorization_servers → ${AUTH_SERVER} (points to Keycloak, should be gateway!)"
else
  warn "authorization_servers → ${AUTH_SERVER} (unexpected value)"
fi

# Check resource field
RESOURCE=$(echo "$PRM" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('resource',''))" 2>/dev/null || echo "")
if [ "$RESOURCE" = "$GATEWAY_URL" ]; then
  pass "resource → ${RESOURCE}"
else
  warn "resource → ${RESOURCE} (expected ${GATEWAY_URL})"
fi

# ─── Step 6: Authorization Server Metadata (RFC 8414) ───
echo ""
echo "── Step 6: Authorization Server Metadata ──"

# Discover from authorization_servers URL
if [ -n "$AUTH_SERVER" ]; then
  ASM_URL="${AUTH_SERVER%/}/.well-known/oauth-authorization-server"
  ASM=$(curl -s "${ASM_URL}" 2>/dev/null || echo "{}")
  ASM_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${ASM_URL}" 2>/dev/null || echo "000")

  if [ "$ASM_CODE" = "200" ]; then
    pass "GET ${ASM_URL} → 200"
  else
    fail "GET ${ASM_URL} → ${ASM_CODE} (expected 200)"
  fi

  # Check critical fields
  TOKEN_EP=$(echo "$ASM" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('token_endpoint',''))" 2>/dev/null || echo "")
  REG_EP=$(echo "$ASM" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('registration_endpoint',''))" 2>/dev/null || echo "")
  AUTH_EP=$(echo "$ASM" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('authorization_endpoint',''))" 2>/dev/null || echo "")
  AUTH_METHODS=$(echo "$ASM" | python3 -c "import sys,json; d=json.load(sys.stdin); print(','.join(d.get('token_endpoint_auth_methods_supported',[])))" 2>/dev/null || echo "")
  PKCE=$(echo "$ASM" | python3 -c "import sys,json; d=json.load(sys.stdin); print(','.join(d.get('code_challenge_methods_supported',[])))" 2>/dev/null || echo "")

  if echo "$TOKEN_EP" | grep -q "${GATEWAY_URL}"; then
    pass "token_endpoint → ${TOKEN_EP} (proxied through gateway)"
  elif [ -n "$TOKEN_EP" ]; then
    warn "token_endpoint → ${TOKEN_EP} (direct to Keycloak, should be gateway proxy)"
  else
    fail "token_endpoint missing"
  fi

  if echo "$REG_EP" | grep -q "${GATEWAY_URL}"; then
    pass "registration_endpoint → ${REG_EP} (proxied through gateway)"
  elif [ -n "$REG_EP" ]; then
    warn "registration_endpoint → ${REG_EP} (direct to Keycloak)"
  else
    fail "registration_endpoint missing"
  fi

  if [ -n "$AUTH_EP" ]; then
    pass "authorization_endpoint → ${AUTH_EP}"
  else
    fail "authorization_endpoint missing"
  fi

  # Critical: "none" must be in token_endpoint_auth_methods_supported for public clients
  if echo "$AUTH_METHODS" | grep -q "none"; then
    pass "token_endpoint_auth_methods includes 'none' (public client support)"
  else
    fail "token_endpoint_auth_methods: [${AUTH_METHODS}] — missing 'none' (public clients broken!)"
  fi

  if echo "$PKCE" | grep -q "S256"; then
    pass "code_challenge_methods includes S256 (PKCE support)"
  else
    fail "code_challenge_methods: [${PKCE}] — missing S256 (PKCE required for MCP)"
  fi
else
  fail "No authorization_servers found — cannot discover OAuth metadata"
fi

# ─── Step 7: Dynamic Client Registration ───
echo ""
echo "── Step 7: Dynamic Client Registration (DCR) ──"
if [ -n "$REG_EP" ]; then
  DCR_RESP=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "${REG_EP}" \
    -H "Content-Type: application/json" \
    -d '{
      "client_name": "mcp-flow-test-'$(date +%s)'",
      "redirect_uris": ["http://localhost:19876/callback"],
      "token_endpoint_auth_method": "none",
      "grant_types": ["authorization_code"],
      "response_types": ["code"]
    }' 2>/dev/null || echo "HTTP_CODE:000")

  DCR_CODE=$(echo "$DCR_RESP" | grep "HTTP_CODE:" | sed 's/HTTP_CODE://')
  DCR_BODY=$(echo "$DCR_RESP" | grep -v "HTTP_CODE:")

  if [ "$DCR_CODE" = "201" ] || [ "$DCR_CODE" = "200" ]; then
    CLIENT_ID=$(echo "$DCR_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('client_id',''))" 2>/dev/null || echo "")
    if [ -n "$CLIENT_ID" ]; then
      pass "DCR → ${DCR_CODE} (client_id: ${CLIENT_ID})"
    else
      warn "DCR → ${DCR_CODE} but no client_id in response"
    fi
  else
    DCR_ERR=$(echo "$DCR_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('error_description', d.get('error','unknown')))" 2>/dev/null || echo "$DCR_BODY")
    fail "DCR → ${DCR_CODE}: ${DCR_ERR}"
  fi
else
  warn "Skipping DCR — no registration_endpoint found"
fi

# ─── Step 8: Authorization URL Construction ───
echo ""
echo "── Step 8: Authorization URL ──"
if [ -n "$AUTH_EP" ] && [ -n "$CLIENT_ID" ]; then
  AUTH_URL="${AUTH_EP}?response_type=code&client_id=${CLIENT_ID}&redirect_uri=http%3A%2F%2Flocalhost%3A19876%2Fcallback&scope=openid+stoa%3Aread&code_challenge=test&code_challenge_method=S256&state=test123"
  AUTH_URL_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$AUTH_URL" 2>/dev/null || echo "000")

  # Keycloak should return 200 (login page) or 302 (redirect to login)
  if [ "$AUTH_URL_CODE" = "200" ] || [ "$AUTH_URL_CODE" = "302" ]; then
    pass "Authorization URL → ${AUTH_URL_CODE} (Keycloak login page reachable)"
  else
    fail "Authorization URL → ${AUTH_URL_CODE} (Keycloak login page NOT reachable)"
  fi
else
  warn "Skipping auth URL test — missing auth_endpoint or client_id"
fi

# ─── Step 9: Token Endpoint Proxy ───
echo ""
echo "── Step 9: Token Endpoint Proxy ──"
if [ -n "$TOKEN_EP" ]; then
  # Send invalid token request — expect 400/401 (not 502/503 which would mean proxy broken)
  TOK_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${TOKEN_EP}" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "grant_type=authorization_code&code=fake&redirect_uri=http://localhost:19876/callback&client_id=fake" 2>/dev/null || echo "000")

  if [ "$TOK_CODE" = "400" ] || [ "$TOK_CODE" = "401" ]; then
    pass "Token endpoint proxy → ${TOK_CODE} (proxy works, rejected fake code correctly)"
  elif [ "$TOK_CODE" = "502" ] || [ "$TOK_CODE" = "503" ]; then
    fail "Token endpoint proxy → ${TOK_CODE} (proxy broken, can't reach Keycloak)"
  else
    warn "Token endpoint proxy → ${TOK_CODE} (unexpected code)"
  fi
else
  warn "Skipping token endpoint test — no token_endpoint found"
fi

# ─── Summary ───
echo ""
echo "═══════════════════════════════════════════"
echo "Results: ${PASS} passed, ${FAIL} failed, ${WARN} warnings"
echo "═══════════════════════════════════════════"

if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "🔴 MCP OAuth flow has ${FAIL} critical failure(s)."
  echo "   Claude.ai and other MCP clients will NOT be able to connect."
  exit 1
else
  echo ""
  echo "🟢 MCP OAuth flow is functional."
  if [ "$WARN" -gt 0 ]; then
    echo "   ${WARN} warning(s) — review above for potential issues."
  fi
  exit 0
fi
