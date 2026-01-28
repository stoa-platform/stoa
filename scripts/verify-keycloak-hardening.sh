#!/bin/bash
# CAB-940: Keycloak Hardening Verification Script
# Tests all hardening measures and exits 1 on failure
#
# Usage:
#   ./scripts/verify-keycloak-hardening.sh
#   KEYCLOAK_URL=https://auth.example.com ./scripts/verify-keycloak-hardening.sh

set -euo pipefail

KEYCLOAK_URL="${KEYCLOAK_URL:-https://auth.gostoa.dev}"
REALM="${KEYCLOAK_REALM:-stoa}"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASSED=0
FAILED=0
WARNED=0

pass() {
    echo -e "${GREEN}PASS${NC} $1"
    ((PASSED++))
}

fail() {
    echo -e "${RED}FAIL${NC} $1"
    ((FAILED++))
}

warn() {
    echo -e "${YELLOW}WARN${NC} $1"
    ((WARNED++))
}

echo "=== CAB-940: Keycloak Hardening Verification ==="
echo "Target: ${KEYCLOAK_URL}"
echo "Realm: ${REALM}"
echo ""

# Test 1: Admin console should be blocked (403)
echo -n "[1/8] Admin console blocked... "
ADMIN_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${KEYCLOAK_URL}/admin/" 2>/dev/null || echo "000")
if [[ "${ADMIN_STATUS}" == "403" ]]; then
    pass "(HTTP 403)"
elif [[ "${ADMIN_STATUS}" == "000" ]]; then
    fail "(Connection failed)"
else
    fail "(HTTP ${ADMIN_STATUS}, expected 403)"
fi

# Test 2: Master realm should be blocked (403)
echo -n "[2/8] Master realm blocked... "
MASTER_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${KEYCLOAK_URL}/realms/master/.well-known/openid-configuration" 2>/dev/null || echo "000")
if [[ "${MASTER_STATUS}" == "403" ]]; then
    pass "(HTTP 403)"
elif [[ "${MASTER_STATUS}" == "000" ]]; then
    fail "(Connection failed)"
else
    fail "(HTTP ${MASTER_STATUS}, expected 403)"
fi

# Test 3: Account self-service should be blocked (403)
echo -n "[3/8] Account self-service blocked... "
ACCOUNT_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${KEYCLOAK_URL}/realms/${REALM}/account/" 2>/dev/null || echo "000")
if [[ "${ACCOUNT_STATUS}" == "403" ]]; then
    pass "(HTTP 403)"
elif [[ "${ACCOUNT_STATUS}" == "000" ]]; then
    fail "(Connection failed)"
else
    fail "(HTTP ${ACCOUNT_STATUS}, expected 403)"
fi

# Test 4: OIDC discovery should work (200)
echo -n "[4/8] OIDC discovery accessible... "
OIDC_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${KEYCLOAK_URL}/realms/${REALM}/.well-known/openid-configuration" 2>/dev/null || echo "000")
if [[ "${OIDC_STATUS}" == "200" ]]; then
    pass "(HTTP 200)"
elif [[ "${OIDC_STATUS}" == "000" ]]; then
    fail "(Connection failed)"
else
    fail "(HTTP ${OIDC_STATUS}, expected 200)"
fi

# Test 5: JWKS endpoint should work (200) - Critical for MCP Gateway
echo -n "[5/8] JWKS endpoint accessible... "
JWKS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${KEYCLOAK_URL}/realms/${REALM}/protocol/openid-connect/certs" 2>/dev/null || echo "000")
if [[ "${JWKS_STATUS}" == "200" ]]; then
    pass "(HTTP 200) - MCP Gateway OK"
elif [[ "${JWKS_STATUS}" == "000" ]]; then
    fail "(Connection failed) - MCP Gateway BROKEN!"
else
    fail "(HTTP ${JWKS_STATUS}, expected 200) - MCP Gateway may be broken!"
fi

# Test 6: Token endpoint should be reachable (400/401 without creds is expected)
echo -n "[6/8] Token endpoint accessible... "
TOKEN_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${KEYCLOAK_URL}/realms/${REALM}/protocol/openid-connect/token" -d "" 2>/dev/null || echo "000")
if [[ "${TOKEN_STATUS}" == "400" || "${TOKEN_STATUS}" == "401" || "${TOKEN_STATUS}" == "415" ]]; then
    pass "(HTTP ${TOKEN_STATUS}) - Endpoint reachable"
elif [[ "${TOKEN_STATUS}" == "000" ]]; then
    fail "(Connection failed)"
else
    fail "(HTTP ${TOKEN_STATUS}, expected 400/401/415)"
fi

# Test 7: Token lifespan check (via test token if credentials available)
echo -n "[7/8] Token lifespan ≤ 300s... "
if [[ -n "${TEST_CLIENT_SECRET:-}" ]]; then
    # Get a token and check expires_in
    TOKEN_RESPONSE=$(curl -s -X POST "${KEYCLOAK_URL}/realms/${REALM}/protocol/openid-connect/token" \
        -d "grant_type=client_credentials" \
        -d "client_id=${TEST_CLIENT_ID:-stoa-mcp-gateway}" \
        -d "client_secret=${TEST_CLIENT_SECRET}" 2>/dev/null || echo "{}")
    EXPIRES_IN=$(echo "${TOKEN_RESPONSE}" | jq -r '.expires_in // 0' 2>/dev/null || echo "0")
    if [[ "${EXPIRES_IN}" -gt 0 && "${EXPIRES_IN}" -le 300 ]]; then
        pass "(expires_in=${EXPIRES_IN}s)"
    elif [[ "${EXPIRES_IN}" -gt 300 ]]; then
        fail "(expires_in=${EXPIRES_IN}s > 300s MAX)"
    else
        warn "(Could not obtain token to verify)"
    fi
else
    warn "(Set TEST_CLIENT_SECRET to verify token lifespan)"
fi

# Test 8: Security headers present
echo -n "[8/8] Security headers present... "
HEADERS=$(curl -s -I "${KEYCLOAK_URL}/realms/${REALM}/.well-known/openid-configuration" 2>/dev/null)

HEADERS_OK=true
MISSING_HEADERS=""

if ! echo "${HEADERS}" | grep -qi "x-frame-options"; then
    HEADERS_OK=false
    MISSING_HEADERS="${MISSING_HEADERS} X-Frame-Options"
fi

if ! echo "${HEADERS}" | grep -qi "x-content-type-options"; then
    HEADERS_OK=false
    MISSING_HEADERS="${MISSING_HEADERS} X-Content-Type-Options"
fi

if ! echo "${HEADERS}" | grep -qi "strict-transport-security"; then
    HEADERS_OK=false
    MISSING_HEADERS="${MISSING_HEADERS} HSTS"
fi

if [[ "${HEADERS_OK}" == "true" ]]; then
    pass "(All headers present)"
else
    warn "(Missing:${MISSING_HEADERS})"
fi

echo ""
echo "=== Results ==="
echo -e "Passed: ${GREEN}${PASSED}${NC}"
echo -e "Failed: ${RED}${FAILED}${NC}"
echo -e "Warnings: ${YELLOW}${WARNED}${NC}"
echo ""

if [[ ${FAILED} -gt 0 ]]; then
    echo -e "${RED}HARDENING VERIFICATION FAILED${NC}"
    echo "Review the failed tests above and fix before proceeding."
    exit 1
fi

if [[ ${WARNED} -gt 0 ]]; then
    echo -e "${YELLOW}HARDENING VERIFICATION PASSED WITH WARNINGS${NC}"
    echo "Consider addressing the warnings for full compliance."
    exit 0
fi

echo -e "${GREEN}HARDENING VERIFICATION PASSED${NC}"
echo "Keycloak is properly hardened per CAB-940 requirements."
exit 0
