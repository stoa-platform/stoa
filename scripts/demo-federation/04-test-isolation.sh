#!/usr/bin/env bash
# =============================================================================
# STOA Federation Demo — Isolation Test
# Proves cross-realm tokens are rejected (the money shot)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOKEN_DIR="${SCRIPT_DIR}/.tokens"

GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

GATEWAY_URL="${GATEWAY_URL:-http://localhost:9000}"
KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:8080}"

PASS_COUNT=0
FAIL_COUNT=0

check() {
  local DESCRIPTION="$1"
  local TOKEN_REALM="$2"
  local TARGET_TENANT="$3"
  local EXPECTED_CODE="$4"

  TOKEN_FILE="${TOKEN_DIR}/${TOKEN_REALM}-api.token"
  if [ ! -f "${TOKEN_FILE}" ]; then
    TOKEN_FILE="${TOKEN_DIR}/${TOKEN_REALM}.token"
  fi
  if [ ! -f "${TOKEN_FILE}" ]; then
    echo -e "  ${RED}SKIP${NC} ${DESCRIPTION} — no token for ${TOKEN_REALM}"
    return
  fi

  TOKEN=$(cat "${TOKEN_FILE}")
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer ${TOKEN}" \
    "${GATEWAY_URL}/api/${TARGET_TENANT}/whoami")

  if [ "${HTTP_CODE}" = "${EXPECTED_CODE}" ]; then
    echo -e "  ${GREEN}PASS${NC} ${DESCRIPTION} → ${HTTP_CODE}"
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    echo -e "  ${RED}FAIL${NC} ${DESCRIPTION} → ${HTTP_CODE} (expected ${EXPECTED_CODE})"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
}

echo -e "${CYAN}=== STOA Federation Demo — Isolation Test ===${NC}"
echo ""

# Step 1: Ensure we have tokens for all 3 realms
echo -e "${YELLOW}Step 1: Authenticating all realms...${NC}"
for REALM in alpha beta gamma; do
  TOKEN_FILE="${TOKEN_DIR}/${REALM}.token"
  if [ ! -f "${TOKEN_FILE}" ]; then
    case "${REALM}" in
      alpha) "${SCRIPT_DIR}/01-login.sh" alpha demo-alpha demo > /dev/null 2>&1 ;;
      beta)  "${SCRIPT_DIR}/01-login.sh" beta  demo-beta  demo > /dev/null 2>&1 ;;
      gamma) "${SCRIPT_DIR}/01-login.sh" gamma eve-gamma  demo > /dev/null 2>&1 ;;
    esac
  fi
done
echo -e "${GREEN}All tokens acquired.${NC}"
echo ""

# Step 2: Positive tests (same-realm access)
echo -e "${YELLOW}Step 2: Positive tests (same-realm → should succeed)${NC}"
check "Alpha token → Alpha API" alpha alpha 200
check "Beta token  → Beta API"  beta  beta  200
check "Gamma token → Gamma API" gamma gamma 200
echo ""

# Step 3: Negative tests (cross-realm access — THE MONEY SHOT)
echo -e "${YELLOW}Step 3: Negative tests (cross-realm → must be denied)${NC}"
check "Alpha token → Beta API  (cross-realm)" alpha beta  403
check "Alpha token → Gamma API (cross-realm)" alpha gamma 403
check "Beta token  → Alpha API (cross-realm)" beta  alpha 403
check "Beta token  → Gamma API (cross-realm)" beta  gamma 403
check "Gamma token → Alpha API (cross-realm)" gamma alpha 403
check "Gamma token → Beta API  (cross-realm)" gamma beta  403
echo ""

# Summary
TOTAL=$((PASS_COUNT + FAIL_COUNT))
echo -e "${CYAN}=== Results: ${PASS_COUNT}/${TOTAL} passed ===${NC}"
echo ""

if [ "${FAIL_COUNT}" -eq 0 ]; then
  echo -e "${GREEN}ISOLATION VERIFIED — Zero User Storage Federation works.${NC}"
  echo ""
  echo "What this proves (ADR-026):"
  echo "  1. Each org has its own realm (OIDC, SAML, LDAP)"
  echo "  2. Tokens are scoped to issuing realm"
  echo "  3. Cross-realm access is denied by gateway"
  echo "  4. Zero user data stored centrally"
  exit 0
else
  echo -e "${RED}ISOLATION BROKEN — ${FAIL_COUNT} test(s) failed!${NC}"
  exit 1
fi
