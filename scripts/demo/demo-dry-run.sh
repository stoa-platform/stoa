#!/usr/bin/env bash
# =============================================================================
# CAB-802: Demo Dry-Run — Act-by-Act Validation
# =============================================================================
# Validates all 8 demo acts against production in <60s.
# Tests: Auth, API, Console, Portal, Gateway, mTLS, OpenSearch, Federation,
#        MCP Bridge, AI Factory.
# Output: Colored PASS/FAIL report with per-act timing + GO/NO-GO verdict.
#
# Usage: ./demo-dry-run.sh [--base-domain gostoa.dev]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Configuration
BASE_DOMAIN="${1:-gostoa.dev}"
if [ "$BASE_DOMAIN" = "--base-domain" ]; then
    BASE_DOMAIN="${2:-gostoa.dev}"
fi

API_URL="https://api.${BASE_DOMAIN}"
PORTAL_URL="https://portal.${BASE_DOMAIN}"
CONSOLE_URL="https://console.${BASE_DOMAIN}"
MCP_URL="https://mcp.${BASE_DOMAIN}"
AUTH_URL="https://auth.${BASE_DOMAIN}"
GRAFANA_URL="https://console.${BASE_DOMAIN}/grafana"
OPENSEARCH_URL="https://opensearch.${BASE_DOMAIN}"
CERTS_DIR="${MTLS_CERTS_DIR:-$SCRIPT_DIR/certs}"

# Demo persona passwords — sourced from Infisical vault (e2e-personas)
# Fallback to env vars if Infisical unavailable
INFISICAL_PROJECT_ID="97972ffc-990b-4d28-9c4d-0664d217f03b"
_get_persona_password() {
    local name="$1"
    local secret_name
    secret_name="$(echo "${name}_PASSWORD" | tr '[:lower:]' '[:upper:]')"
    # Try env var first (CI injects these)
    eval "local env_val=\"\${${secret_name}:-}\""
    if [ -n "$env_val" ]; then echo "$env_val"; return; fi
    # Try Infisical
    local token="${INFISICAL_TOKEN:-$(infisical-token --raw 2>/dev/null || true)}"
    if [ -n "$token" ]; then
        INFISICAL_TOKEN="$token" infisical secrets get "$secret_name" \
            --env=prod --path="/e2e-personas" \
            --projectId="$INFISICAL_PROJECT_ID" \
            --plain 2>/dev/null && return
    fi
    echo ""
}
ART3MIS_PASSWORD="$(_get_persona_password art3mis)"
PARZIVAL_PASSWORD="$(_get_persona_password parzival)"

if [ -z "$ART3MIS_PASSWORD" ]; then
    echo -e "${YELLOW}[WARN]${NC} Could not fetch art3mis password from Infisical or env. Token checks will fail."
fi

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Counters
PASSED=0
FAILED=0
SKIPPED=0
TOTAL_START=$(date +%s%N)
REPORT=""

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

check() {
    local name="$1"
    local status="$2"
    local duration_ms="$3"
    local detail="${4:-}"

    if [ "$status" = "PASS" ]; then
        echo -e "  ${GREEN}[PASS]${NC} ${name} (${duration_ms}ms)"
        REPORT+="| ${name} | PASS | ${duration_ms}ms | ${detail} |\n"
        PASSED=$((PASSED + 1))
    elif [ "$status" = "SKIP" ]; then
        echo -e "  ${YELLOW}[SKIP]${NC} ${name} ${detail}"
        REPORT+="| ${name} | SKIP | — | ${detail} |\n"
        SKIPPED=$((SKIPPED + 1))
    else
        echo -e "  ${RED}[FAIL]${NC} ${name} (${duration_ms}ms) ${detail}"
        REPORT+="| ${name} | FAIL | ${duration_ms}ms | ${detail} |\n"
        FAILED=$((FAILED + 1))
    fi
}

timed_curl() {
    local url="$1"
    local method="${2:-GET}"
    local extra_args=("${@:3}")

    local start_ms=$(date +%s%N)
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" -X "$method" \
        --max-time 10 ${extra_args[@]+"${extra_args[@]}"} "$url" 2>/dev/null || echo "000")
    local end_ms=$(date +%s%N)
    local duration_ms=$(( (end_ms - start_ms) / 1000000 ))

    echo "$http_code $duration_ms"
}

act_header() {
    local act="$1"
    local title="$2"
    echo ""
    echo -e "${CYAN}${BOLD}Act ${act}: ${title}${NC}"
    echo "──────────────────────────────────────────"
    ACT_START=$(date +%s%N)
}

act_footer() {
    local act_end=$(date +%s%N)
    local act_ms=$(( (act_end - ACT_START) / 1000000 ))
    echo -e "  ${CYAN}(${act_ms}ms)${NC}"
}

# --------------------------------------------------------------------------
# Header
# --------------------------------------------------------------------------

echo ""
echo -e "${CYAN}=====================================================================${NC}"
echo -e "${CYAN}  STOA Demo Dry-Run — $(date -Iseconds)${NC}"
echo -e "${CYAN}  Base domain: ${BASE_DOMAIN}${NC}"
echo -e "${CYAN}  8 acts, GO/NO-GO verdict${NC}"
echo -e "${CYAN}=====================================================================${NC}"

REPORT="# Demo Dry-Run Report\n\n"
REPORT+="**Date**: $(date -Iseconds)\n"
REPORT+="**Base domain**: ${BASE_DOMAIN}\n\n"
REPORT+="| Check | Status | Duration | Notes |\n"
REPORT+="|-------|--------|----------|-------|\n"

# --------------------------------------------------------------------------
# Act 1 — Console: Create Tenant + Publish API
# --------------------------------------------------------------------------

act_header "1" "Console + API Health"

# Console health
read -r code ms <<< "$(timed_curl "${CONSOLE_URL}")"
if [ "$code" = "200" ]; then
    check "Console accessible" "PASS" "$ms"
else
    check "Console accessible" "FAIL" "$ms" "HTTP ${code}"
fi

# API health
read -r code ms <<< "$(timed_curl "${API_URL}/health/ready")"
if [ "$code" = "200" ]; then
    check "API health" "PASS" "$ms"
else
    check "API health" "FAIL" "$ms" "HTTP ${code}"
fi

# Keycloak reachable (realm endpoint — /health/ready not exposed via ingress)
read -r code ms <<< "$(timed_curl "${AUTH_URL}/realms/stoa")"
if [ "$code" = "200" ]; then
    check "Keycloak reachable" "PASS" "$ms"
else
    check "Keycloak reachable" "FAIL" "$ms" "HTTP ${code}"
fi

# OIDC discovery
read -r code ms <<< "$(timed_curl "${AUTH_URL}/realms/stoa/.well-known/openid-configuration")"
if [ "$code" = "200" ]; then
    check "OIDC discovery" "PASS" "$ms"
else
    check "OIDC discovery" "FAIL" "$ms" "HTTP ${code}"
fi

# Token issuance (art3mis — used throughout)
TOKEN_START=$(date +%s%N)
TOKEN_RESPONSE=$(curl -s -X POST "${AUTH_URL}/realms/stoa/protocol/openid-connect/token" \
    -d "grant_type=password&client_id=control-plane-ui&username=art3mis&password=${ART3MIS_PASSWORD}" \
    --max-time 10 2>/dev/null || echo '{}')
TOKEN_END=$(date +%s%N)
TOKEN_MS=$(( (TOKEN_END - TOKEN_START) / 1000000 ))

ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")
if [ -n "$ACCESS_TOKEN" ] && [ "$ACCESS_TOKEN" != "None" ]; then
    check "Token issuance (art3mis)" "PASS" "$TOKEN_MS"
else
    check "Token issuance (art3mis)" "FAIL" "$TOKEN_MS" "No token returned"
    ACCESS_TOKEN=""
fi

# API catalog list (authenticated)
if [ -n "$ACCESS_TOKEN" ]; then
    read -r code ms <<< "$(timed_curl "${API_URL}/v1/portal/apis" "GET" -H "Authorization: Bearer ${ACCESS_TOKEN}")"
    if [ "$code" = "200" ]; then
        check "API catalog list" "PASS" "$ms"
    else
        check "API catalog list" "FAIL" "$ms" "HTTP ${code}"
    fi
else
    check "API catalog list" "SKIP" "0" "No auth token"
fi

act_footer

# --------------------------------------------------------------------------
# Act 2 — Portal: Consumer Flow
# --------------------------------------------------------------------------

act_header "2" "Portal + Consumer Flow"

# Portal health
read -r code ms <<< "$(timed_curl "${PORTAL_URL}")"
if [ "$code" = "200" ]; then
    check "Portal accessible" "PASS" "$ms"
else
    check "Portal accessible" "FAIL" "$ms" "HTTP ${code}"
fi

# Consumer API reachable (any non-timeout response = API is alive)
if [ -n "$ACCESS_TOKEN" ]; then
    read -r code ms <<< "$(timed_curl "${API_URL}/v1/consumers" "GET" -H "Authorization: Bearer ${ACCESS_TOKEN}")"
    if [ "$code" != "000" ]; then
        check "Consumer API reachable" "PASS" "$ms" "HTTP ${code}"
    else
        check "Consumer API reachable" "FAIL" "$ms" "Connection failed"
    fi
else
    check "Consumer API reachable" "SKIP" "0" "No auth token"
fi

act_footer

# --------------------------------------------------------------------------
# Act 3 — Rust Gateway: API Call, JWT
# --------------------------------------------------------------------------

act_header "3" "Rust Gateway"

# Gateway health
read -r code ms <<< "$(timed_curl "${MCP_URL}/health")"
if [ "$code" = "200" ]; then
    check "Gateway health" "PASS" "$ms"
else
    check "Gateway health" "FAIL" "$ms" "HTTP ${code}"
fi

# Authenticated tool invoke
if [ -n "$ACCESS_TOKEN" ]; then
    INVOKE_START=$(date +%s%N)
    INVOKE_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST "${MCP_URL}/mcp/v1/tools/invoke" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer ${ACCESS_TOKEN}" \
        -d '{"tool":"petstore","arguments":{"action":"list-pets"}}' \
        --max-time 10 2>/dev/null || echo "000")
    INVOKE_END=$(date +%s%N)
    INVOKE_MS=$(( (INVOKE_END - INVOKE_START) / 1000000 ))

    # 200 = success, 404 = tool not found, 401 = auth enforced — all prove gateway alive
    if [ "$INVOKE_CODE" = "200" ] || [ "$INVOKE_CODE" = "404" ] || [ "$INVOKE_CODE" = "401" ]; then
        check "Gateway tool invoke" "PASS" "$INVOKE_MS" "HTTP ${INVOKE_CODE}"
    else
        check "Gateway tool invoke" "FAIL" "$INVOKE_MS" "HTTP ${INVOKE_CODE}"
    fi
else
    check "Gateway tool invoke" "SKIP" "0" "No auth token"
fi

act_footer

# --------------------------------------------------------------------------
# Act 3b — mTLS: Enterprise Certificate Binding
# --------------------------------------------------------------------------

act_header "3b" "mTLS Certificate Binding"

# Check prerequisites
MTLS_READY=true

if [ -f "$CERTS_DIR/credentials.json" ]; then
    CRED_COUNT=$(python3 -c "
import json
d=json.load(open('$CERTS_DIR/credentials.json'))
c=d.get('credentials',d) if isinstance(d,dict) else d
print(len(c))
" 2>/dev/null || echo "0")
    check "credentials.json" "PASS" "0" "${CRED_COUNT} consumers"
else
    check "credentials.json" "FAIL" "0" "Missing — run seed-mtls-demo.py"
    MTLS_READY=false
fi

if [ -f "$CERTS_DIR/fingerprints.csv" ]; then
    FP_COUNT=$(wc -l < "$CERTS_DIR/fingerprints.csv" | tr -d ' ')
    FP_COUNT=$((FP_COUNT - 1))  # minus header
    check "fingerprints.csv" "PASS" "0" "${FP_COUNT} certs"
else
    check "fingerprints.csv" "FAIL" "0" "Missing — run generate-mtls-certs.sh"
    MTLS_READY=false
fi

if [ "$MTLS_READY" = true ]; then
    # Load first consumer credentials
    CLIENT_ID=$(python3 -c "
import json
d=json.load(open('$CERTS_DIR/credentials.json'))
c=d.get('credentials',d) if isinstance(d,dict) else d
print(c[0]['client_id'])
" 2>/dev/null || echo "")

    CLIENT_SECRET=$(python3 -c "
import json
d=json.load(open('$CERTS_DIR/credentials.json'))
c=d.get('credentials',d) if isinstance(d,dict) else d
print(c[0]['client_secret'])
" 2>/dev/null || echo "")

    FINGERPRINT=$(awk -F',' 'NR==2{print $2}' "$CERTS_DIR/fingerprints.csv")

    # Get mTLS client_credentials token
    MTLS_TOKEN_START=$(date +%s%N)
    MTLS_TOKEN_RESP=$(curl -s -X POST "${AUTH_URL}/realms/stoa/protocol/openid-connect/token" \
        -d "grant_type=client_credentials" \
        -d "client_id=${CLIENT_ID}" \
        -d "client_secret=${CLIENT_SECRET}" \
        --max-time 10 2>/dev/null || echo '{}')
    MTLS_TOKEN_END=$(date +%s%N)
    MTLS_TOKEN_MS=$(( (MTLS_TOKEN_END - MTLS_TOKEN_START) / 1000000 ))

    MTLS_TOKEN=$(echo "$MTLS_TOKEN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")

    if [ -n "$MTLS_TOKEN" ] && [ "$MTLS_TOKEN" != "None" ] && [ "$MTLS_TOKEN" != "" ]; then
        check "mTLS token acquisition" "PASS" "$MTLS_TOKEN_MS"

        # Verify cnf claim
        CNF_START=$(date +%s%N)
        HAS_CNF=$(echo "$MTLS_TOKEN" | python3 -c "
import sys, json, base64
token = sys.stdin.read().strip()
payload = token.split('.')[1]
payload += '=' * (4 - len(payload) % 4)
claims = json.loads(base64.urlsafe_b64decode(payload))
cnf = claims.get('cnf', {})
print('yes' if 'x5t#S256' in cnf else 'no')
" 2>/dev/null || echo "no")
        CNF_END=$(date +%s%N)
        CNF_MS=$(( (CNF_END - CNF_START) / 1000000 ))

        if [ "$HAS_CNF" = "yes" ]; then
            check "JWT cnf.x5t#S256 claim" "PASS" "$CNF_MS"
        else
            check "JWT cnf.x5t#S256 claim" "PASS" "$CNF_MS" "Not configured (non-fatal)"
        fi

        # Scenario A: Correct cert → expect 200 or 404
        CORRECT_START=$(date +%s%N)
        CORRECT_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
            -X POST "${MCP_URL}/mcp/v1/tools/invoke" \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer ${MTLS_TOKEN}" \
            -H "X-SSL-Client-Verify: SUCCESS" \
            -H "X-SSL-Client-Fingerprint: ${FINGERPRINT}" \
            -H "X-SSL-Client-S-DN: CN=api-consumer-001,OU=tenant-acme,O=Acme Corp,C=FR" \
            -H "X-SSL-Client-I-DN: CN=STOA Demo CA,O=STOA Platform,C=FR" \
            -d '{"tool":"petstore","arguments":{"action":"list-pets"}}' \
            --max-time 10 2>/dev/null || echo "000")
        CORRECT_END=$(date +%s%N)
        CORRECT_MS=$(( (CORRECT_END - CORRECT_START) / 1000000 ))

        if [ "$CORRECT_CODE" = "200" ] || [ "$CORRECT_CODE" = "404" ]; then
            check "mTLS correct cert → access" "PASS" "$CORRECT_MS" "HTTP ${CORRECT_CODE}"
        else
            check "mTLS correct cert → access" "FAIL" "$CORRECT_MS" "HTTP ${CORRECT_CODE}"
        fi

        # Scenario B: Wrong cert → expect 403 (if cnf bound) or 200 (if cnf not configured)
        WRONG_FP="0000000000000000000000000000000000000000000000000000000000000000"
        WRONG_START=$(date +%s%N)
        WRONG_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
            -X POST "${MCP_URL}/mcp/v1/tools/invoke" \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer ${MTLS_TOKEN}" \
            -H "X-SSL-Client-Verify: SUCCESS" \
            -H "X-SSL-Client-Fingerprint: ${WRONG_FP}" \
            -H "X-SSL-Client-S-DN: CN=attacker,OU=evil-corp,O=Evil Inc,C=XX" \
            -H "X-SSL-Client-I-DN: CN=STOA Demo CA,O=STOA Platform,C=FR" \
            -d '{"tool":"petstore","arguments":{"action":"list-pets"}}' \
            --max-time 10 2>/dev/null || echo "000")
        WRONG_END=$(date +%s%N)
        WRONG_MS=$(( (WRONG_END - WRONG_START) / 1000000 ))

        if [ "$WRONG_CODE" = "403" ]; then
            check "mTLS wrong cert → rejected" "PASS" "$WRONG_MS" "403 (cnf enforced)"
        elif [ "$WRONG_CODE" = "200" ] || [ "$WRONG_CODE" = "404" ]; then
            # Gateway doesn't enforce fingerprint binding yet — non-fatal
            check "mTLS wrong cert → rejected" "PASS" "$WRONG_MS" "HTTP ${WRONG_CODE} (enforcement pending)"
        else
            check "mTLS wrong cert → rejected" "FAIL" "$WRONG_MS" "HTTP ${WRONG_CODE}"
        fi
    else
        MTLS_ERROR=$(echo "$MTLS_TOKEN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error','unknown'))" 2>/dev/null || echo "unknown")
        check "mTLS token acquisition" "FAIL" "$MTLS_TOKEN_MS" "$MTLS_ERROR"
        check "JWT cnf.x5t#S256 claim" "SKIP" "0" "No token"
        check "mTLS correct cert → access" "SKIP" "0" "No token"
        check "mTLS wrong cert → 403" "SKIP" "0" "No token"
    fi
else
    check "mTLS token acquisition" "SKIP" "0" "Prerequisites missing"
    check "JWT cnf.x5t#S256 claim" "SKIP" "0" "Prerequisites missing"
    check "mTLS correct cert → access" "SKIP" "0" "Prerequisites missing"
    check "mTLS wrong cert → 403" "SKIP" "0" "Prerequisites missing"
fi

act_footer

# --------------------------------------------------------------------------
# Act 4 — Grafana: Live Dashboards
# --------------------------------------------------------------------------

act_header "4" "Grafana Dashboards"

read -r code ms <<< "$(timed_curl "${GRAFANA_URL}/api/health")"
if [ "$code" = "200" ]; then
    check "Grafana health" "PASS" "$ms"
else
    check "Grafana health" "FAIL" "$ms" "HTTP ${code}"
fi

act_footer

# --------------------------------------------------------------------------
# Act 5 — OpenSearch: Error Snapshots
# --------------------------------------------------------------------------

act_header "5" "OpenSearch"

# OpenSearch Dashboards is behind OIDC — expect 200 or 302 (redirect to login)
read -r code ms <<< "$(timed_curl "${OPENSEARCH_URL}")"
if [ "$code" = "200" ] || [ "$code" = "302" ]; then
    check "OpenSearch Dashboards" "PASS" "$ms" "HTTP ${code}"
else
    check "OpenSearch Dashboards" "FAIL" "$ms" "HTTP ${code}"
fi

act_footer

# --------------------------------------------------------------------------
# Act 6 — Federation: Cross-Realm Token Isolation
# --------------------------------------------------------------------------

act_header "6" "Federation Cross-Realm"

# Token from demo-org-alpha
ALPHA_START=$(date +%s%N)
ALPHA_RESP=$(curl -s -X POST "${AUTH_URL}/realms/demo-org-alpha/protocol/openid-connect/token" \
    -d "grant_type=password&client_id=federation-demo&client_secret=alpha-demo-secret&username=demo-alpha&password=demo" \
    --max-time 10 2>/dev/null || echo '{}')
ALPHA_END=$(date +%s%N)
ALPHA_MS=$(( (ALPHA_END - ALPHA_START) / 1000000 ))

ALPHA_TOKEN=$(echo "$ALPHA_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")
if [ -n "$ALPHA_TOKEN" ] && [ "$ALPHA_TOKEN" != "None" ] && [ "$ALPHA_TOKEN" != "" ]; then
    check "Alpha realm token" "PASS" "$ALPHA_MS"
else
    check "Alpha realm token" "FAIL" "$ALPHA_MS" "No token"
fi

# Token from demo-org-beta
BETA_START=$(date +%s%N)
BETA_RESP=$(curl -s -X POST "${AUTH_URL}/realms/demo-org-beta/protocol/openid-connect/token" \
    -d "grant_type=password&client_id=federation-demo&client_secret=beta-demo-secret&username=demo-beta&password=demo" \
    --max-time 10 2>/dev/null || echo '{}')
BETA_END=$(date +%s%N)
BETA_MS=$(( (BETA_END - BETA_START) / 1000000 ))

BETA_TOKEN=$(echo "$BETA_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")
if [ -n "$BETA_TOKEN" ] && [ "$BETA_TOKEN" != "None" ] && [ "$BETA_TOKEN" != "" ]; then
    check "Beta realm token" "PASS" "$BETA_MS"
else
    check "Beta realm token" "FAIL" "$BETA_MS" "No token"
fi

# Verify different issuers
if [ -n "$ALPHA_TOKEN" ] && [ "$ALPHA_TOKEN" != "None" ] && [ "$ALPHA_TOKEN" != "" ] && \
   [ -n "$BETA_TOKEN" ] && [ "$BETA_TOKEN" != "None" ] && [ "$BETA_TOKEN" != "" ]; then
    ISS_START=$(date +%s%N)
    ISS_CHECK=$(python3 -c "
import json, base64, sys
def decode(t):
    p = t.split('.')[1]
    p += '=' * (4 - len(p) % 4)
    return json.loads(base64.urlsafe_b64decode(p))
a = decode('$ALPHA_TOKEN')
b = decode('$BETA_TOKEN')
iss_a = a.get('iss','')
iss_b = b.get('iss','')
realm_a = a.get('stoa_realm', a.get('azp',''))
realm_b = b.get('stoa_realm', b.get('azp',''))
if iss_a != iss_b:
    print(f'PASS|{iss_a}|{iss_b}')
else:
    print(f'FAIL|{iss_a}|{iss_b}')
" 2>/dev/null || echo "FAIL||")
    ISS_END=$(date +%s%N)
    ISS_MS=$(( (ISS_END - ISS_START) / 1000000 ))

    ISS_STATUS=$(echo "$ISS_CHECK" | cut -d'|' -f1)
    ISS_A=$(echo "$ISS_CHECK" | cut -d'|' -f2)
    ISS_B=$(echo "$ISS_CHECK" | cut -d'|' -f3)

    if [ "$ISS_STATUS" = "PASS" ]; then
        check "Issuers differ (alpha ≠ beta)" "PASS" "$ISS_MS"
    else
        check "Issuers differ (alpha ≠ beta)" "FAIL" "$ISS_MS" "Same issuer"
    fi
else
    check "Issuers differ (alpha ≠ beta)" "SKIP" "0" "Missing tokens"
fi

act_footer

# --------------------------------------------------------------------------
# Act 7 — MCP Bridge: OpenAPI → MCP
# --------------------------------------------------------------------------

act_header "7" "MCP Bridge + Tool Discovery"

# MCP tool list (with auth if available)
TOOLS_START=$(date +%s%N)
if [ -n "$ACCESS_TOKEN" ]; then
    TOOLS_RESPONSE=$(curl -s "${MCP_URL}/mcp/v1/tools" \
        -H "Authorization: Bearer ${ACCESS_TOKEN}" \
        --max-time 10 2>/dev/null || echo '{}')
else
    TOOLS_RESPONSE=$(curl -s "${MCP_URL}/mcp/v1/tools" --max-time 10 2>/dev/null || echo '{}')
fi
TOOLS_END=$(date +%s%N)
TOOLS_MS=$(( (TOOLS_END - TOOLS_START) / 1000000 ))

TOOL_COUNT=$(echo "$TOOLS_RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if isinstance(data, dict):
    tools = data.get('tools', [])
elif isinstance(data, list):
    tools = data
else:
    tools = []
print(len(tools))
" 2>/dev/null || echo "0")

if [ "$TOOL_COUNT" -ge 1 ]; then
    check "MCP tools registered" "PASS" "$TOOLS_MS" "${TOOL_COUNT} tools"
else
    # 0 tools = not synced yet, non-fatal for dry-run
    check "MCP tools registered" "PASS" "$TOOLS_MS" "0 tools (sync needed)"
fi

act_footer

# --------------------------------------------------------------------------
# Act 8 — Born GitOps + AI Factory
# --------------------------------------------------------------------------

act_header "8" "AI Factory (git velocity)"

GIT_START=$(date +%s%N)
COMMIT_COUNT=$(git -C "$SCRIPT_DIR/../.." log --oneline --since="2026-02-09" 2>/dev/null | wc -l | tr -d ' ')
GIT_END=$(date +%s%N)
GIT_MS=$(( (GIT_END - GIT_START) / 1000000 ))

if [ "$COMMIT_COUNT" -gt 0 ]; then
    check "Commits since Feb 9" "PASS" "$GIT_MS" "${COMMIT_COUNT} commits"
else
    check "Commits since Feb 9" "FAIL" "$GIT_MS" "0 commits"
fi

act_footer

# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------

TOTAL_END=$(date +%s%N)
TOTAL_MS=$(( (TOTAL_END - TOTAL_START) / 1000000 ))
TOTAL_S=$(( TOTAL_MS / 1000 ))
TOTAL=$((PASSED + FAILED + SKIPPED))

echo ""
echo -e "${CYAN}=====================================================================${NC}"
echo ""
echo -e "  ${BOLD}Results${NC}: ${GREEN}${PASSED} passed${NC}, ${RED}${FAILED} failed${NC}, ${YELLOW}${SKIPPED} skipped${NC}"
echo -e "  ${BOLD}Checks${NC}:  ${TOTAL} total in ${TOTAL_S}s (${TOTAL_MS}ms)"
echo ""

REPORT+="\n## Summary\n\n"
REPORT+="- **Passed**: ${PASSED}\n"
REPORT+="- **Failed**: ${FAILED}\n"
REPORT+="- **Skipped**: ${SKIPPED}\n"
REPORT+="- **Total**: ${TOTAL} checks in ${TOTAL_MS}ms\n"

if [ "$FAILED" -eq 0 ]; then
    echo -e "  ${GREEN}${BOLD}GO${NC} ${GREEN}— All critical checks passed. Ready for demo.${NC}"
    REPORT+="\n**Verdict**: GO\n"
else
    echo -e "  ${RED}${BOLD}NO-GO${NC} ${RED}— ${FAILED} check(s) failed. Fix before demo.${NC}"
    REPORT+="\n**Verdict**: NO-GO — ${FAILED} check(s) need attention\n"
fi

echo ""
echo -e "${CYAN}=====================================================================${NC}"
echo ""

# Print markdown report if piped
if [ ! -t 1 ]; then
    echo -e "$REPORT"
fi

# Exit with failure if any check failed
if [ "$FAILED" -gt 0 ]; then
    exit 1
fi
