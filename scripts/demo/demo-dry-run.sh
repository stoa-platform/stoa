#!/usr/bin/env bash
# =============================================================================
# CAB-802: Demo Dry-Run Automation
# =============================================================================
# Automated pre-demo dry-run that validates each demo segment sequentially.
# Tests: Auth, API, Portal, Gateway, Console.
# Output: Markdown PASS/FAIL report with timing.
#
# Usage: ./demo-dry-run.sh [--base-domain gostoa.dev]
# =============================================================================

set -euo pipefail

# Configuration
BASE_DOMAIN="${1:-gostoa.dev}"
# Strip --base-domain flag if provided
if [ "$BASE_DOMAIN" = "--base-domain" ]; then
    BASE_DOMAIN="${2:-gostoa.dev}"
fi

API_URL="https://api.${BASE_DOMAIN}"
PORTAL_URL="https://portal.${BASE_DOMAIN}"
CONSOLE_URL="https://console.${BASE_DOMAIN}"
MCP_URL="https://mcp.${BASE_DOMAIN}"
AUTH_URL="https://auth.${BASE_DOMAIN}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Counters
PASSED=0
FAILED=0
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
        ((PASSED++))
    else
        echo -e "  ${RED}[FAIL]${NC} ${name} (${duration_ms}ms) ${detail}"
        REPORT+="| ${name} | FAIL | ${duration_ms}ms | ${detail} |\n"
        ((FAILED++))
    fi
}

# Timed curl: returns "status_code duration_ms"
timed_curl() {
    local url="$1"
    local method="${2:-GET}"
    local extra_args=("${@:3}")

    local start_ms=$(date +%s%N)
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" -X "$method" \
        --max-time 10 "${extra_args[@]}" "$url" 2>/dev/null || echo "000")
    local end_ms=$(date +%s%N)
    local duration_ms=$(( (end_ms - start_ms) / 1000000 ))

    echo "$http_code $duration_ms"
}

# --------------------------------------------------------------------------
# Header
# --------------------------------------------------------------------------

echo ""
echo -e "${CYAN}=====================================================================${NC}"
echo -e "${CYAN}  STOA Demo Dry-Run — $(date -Iseconds)${NC}"
echo -e "${CYAN}  Base domain: ${BASE_DOMAIN}${NC}"
echo -e "${CYAN}=====================================================================${NC}"
echo ""

REPORT="# Demo Dry-Run Report\n\n"
REPORT+="**Date**: $(date -Iseconds)\n"
REPORT+="**Base domain**: ${BASE_DOMAIN}\n\n"
REPORT+="| Check | Status | Duration | Notes |\n"
REPORT+="|-------|--------|----------|-------|\n"

# --------------------------------------------------------------------------
# Segment 1: Auth (Keycloak)
# --------------------------------------------------------------------------

echo -e "${CYAN}Segment 1: Auth (Keycloak)${NC}"
echo "──────────────────────────────────"

# Keycloak health
read -r code ms <<< "$(timed_curl "${AUTH_URL}/health/ready")"
if [ "$code" = "200" ]; then
    check "Keycloak health" "PASS" "$ms"
else
    check "Keycloak health" "FAIL" "$ms" "HTTP ${code}"
fi

# OIDC discovery
read -r code ms <<< "$(timed_curl "${AUTH_URL}/realms/stoa/.well-known/openid-configuration")"
if [ "$code" = "200" ]; then
    check "OIDC discovery" "PASS" "$ms"
else
    check "OIDC discovery" "FAIL" "$ms" "HTTP ${code}"
fi

# Token issuance (art3mis persona)
TOKEN_START=$(date +%s%N)
TOKEN_RESPONSE=$(curl -s -X POST "${AUTH_URL}/realms/stoa/protocol/openid-connect/token" \
    -d "grant_type=password&client_id=control-plane-ui&username=art3mis&password=demo" \
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

echo ""

# --------------------------------------------------------------------------
# Segment 2: API (Control Plane)
# --------------------------------------------------------------------------

echo -e "${CYAN}Segment 2: API (Control Plane)${NC}"
echo "──────────────────────────────────"

# API health
read -r code ms <<< "$(timed_curl "${API_URL}/health/ready")"
if [ "$code" = "200" ]; then
    check "API health" "PASS" "$ms"
else
    check "API health" "FAIL" "$ms" "HTTP ${code}"
fi

# API catalog (authenticated)
if [ -n "$ACCESS_TOKEN" ]; then
    read -r code ms <<< "$(timed_curl "${API_URL}/v1/portal/apis" "GET" -H "Authorization: Bearer ${ACCESS_TOKEN}")"
    if [ "$code" = "200" ]; then
        check "API catalog list" "PASS" "$ms"
    else
        check "API catalog list" "FAIL" "$ms" "HTTP ${code}"
    fi

    # Search petstore
    read -r code ms <<< "$(timed_curl "${API_URL}/v1/portal/apis?search=petstore" "GET" -H "Authorization: Bearer ${ACCESS_TOKEN}")"
    if [ "$code" = "200" ]; then
        check "API search (petstore)" "PASS" "$ms"
    else
        check "API search (petstore)" "FAIL" "$ms" "HTTP ${code}"
    fi
else
    check "API catalog list" "FAIL" "0" "No auth token"
    check "API search (petstore)" "FAIL" "0" "No auth token"
fi

echo ""

# --------------------------------------------------------------------------
# Segment 3: Portal
# --------------------------------------------------------------------------

echo -e "${CYAN}Segment 3: Portal${NC}"
echo "──────────────────────────────────"

read -r code ms <<< "$(timed_curl "${PORTAL_URL}")"
if [ "$code" = "200" ]; then
    check "Portal health" "PASS" "$ms"
else
    check "Portal health" "FAIL" "$ms" "HTTP ${code}"
fi

echo ""

# --------------------------------------------------------------------------
# Segment 4: Gateway (MCP)
# --------------------------------------------------------------------------

echo -e "${CYAN}Segment 4: Gateway (MCP)${NC}"
echo "──────────────────────────────────"

read -r code ms <<< "$(timed_curl "${MCP_URL}/health")"
if [ "$code" = "200" ]; then
    check "MCP Gateway health" "PASS" "$ms"
else
    check "MCP Gateway health" "FAIL" "$ms" "HTTP ${code}"
fi

# Tool list
read -r code ms <<< "$(timed_curl "${MCP_URL}/mcp/v1/tools")"
if [ "$code" = "200" ]; then
    check "MCP tools list" "PASS" "$ms"
else
    check "MCP tools list" "FAIL" "$ms" "HTTP ${code}"
fi

echo ""

# --------------------------------------------------------------------------
# Segment 5: Console
# --------------------------------------------------------------------------

echo -e "${CYAN}Segment 5: Console${NC}"
echo "──────────────────────────────────"

read -r code ms <<< "$(timed_curl "${CONSOLE_URL}")"
if [ "$code" = "200" ]; then
    check "Console health" "PASS" "$ms"
else
    check "Console health" "FAIL" "$ms" "HTTP ${code}"
fi

echo ""

# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------

TOTAL_END=$(date +%s%N)
TOTAL_MS=$(( (TOTAL_END - TOTAL_START) / 1000000 ))
TOTAL=$((PASSED + FAILED))

echo -e "${CYAN}=====================================================================${NC}"
echo ""
echo -e "  Summary: ${GREEN}${PASSED} passed${NC}, ${RED}${FAILED} failed${NC} (${TOTAL} checks, ${TOTAL_MS}ms)"
echo ""

REPORT+="\n## Summary\n\n"
REPORT+="- **Passed**: ${PASSED}\n"
REPORT+="- **Failed**: ${FAILED}\n"
REPORT+="- **Total**: ${TOTAL} checks in ${TOTAL_MS}ms\n"

if [ "$FAILED" -eq 0 ]; then
    echo -e "  ${GREEN}ALL CHECKS PASSED — Ready for demo${NC}"
    REPORT+="\n**Verdict**: PASS\n"
else
    echo -e "  ${RED}${FAILED} CHECK(S) FAILED — Fix before demo${NC}"
    REPORT+="\n**Verdict**: FAIL — ${FAILED} check(s) need attention\n"
fi

echo ""

# Print markdown report to stdout if piped
if [ ! -t 1 ]; then
    echo -e "$REPORT"
fi

# Exit with failure if any check failed
if [ "$FAILED" -gt 0 ]; then
    exit 1
fi
