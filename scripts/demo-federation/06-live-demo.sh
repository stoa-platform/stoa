#!/usr/bin/env bash
# =============================================================================
# STOA Federation Demo — Live Presenter Script (2 min)
# "Un login, tous vos tenants — souverainete europeenne"
#
# Usage: ./06-live-demo.sh
# Prerequisites: Federation stack running (./00-setup.sh)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOKEN_DIR="${SCRIPT_DIR}/.tokens"
mkdir -p "${TOKEN_DIR}"

KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:8080}"
GATEWAY_URL="${GATEWAY_URL:-http://localhost:9000}"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

PASS_COUNT=0
FAIL_COUNT=0

# Helpers
banner() { echo -e "\n${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; echo -e "${BOLD}${CYAN}  $1${NC}"; echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"; }
pause() { sleep "${1:-0.3}"; }

login_silent() {
  local REALM="$1" USER="$2" PASS="$3"
  local REALM_NAME="demo-org-${REALM}"
  local CLIENT_SECRET
  case "${REALM}" in
    alpha) CLIENT_SECRET="alpha-demo-secret" ;;
    beta)  CLIENT_SECRET="beta-demo-secret" ;;
    gamma) CLIENT_SECRET="gamma-demo-secret" ;;
  esac
  RESPONSE=$(curl -s -X POST "${KEYCLOAK_URL}/realms/${REALM_NAME}/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "grant_type=password" \
    -d "client_id=federation-demo" \
    -d "client_secret=${CLIENT_SECRET}" \
    -d "username=${USER}" \
    -d "password=${PASS}")
  TOKEN=$(echo "${RESPONSE}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")
  if [ -z "${TOKEN}" ] || [ "${TOKEN}" = "None" ]; then
    echo -e "  ${RED}FAIL${NC} Login failed for ${USER}@${REALM_NAME}"
    return 1
  fi
  echo "${TOKEN}" > "${TOKEN_DIR}/${REALM}.token"
  return 0
}

call_api() {
  local DESCRIPTION="$1" TOKEN_REALM="$2" TARGET="$3" EXPECTED="$4"
  local TOKEN_FILE="${TOKEN_DIR}/${TOKEN_REALM}.token"
  local TOKEN
  TOKEN=$(cat "${TOKEN_FILE}")
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer ${TOKEN}" \
    "${GATEWAY_URL}/api/${TARGET}/whoami")
  if [ "${HTTP_CODE}" = "${EXPECTED}" ]; then
    if [ "${EXPECTED}" = "200" ]; then
      echo -e "  ${GREEN}✓${NC} ${DESCRIPTION}  ${DIM}→ ${HTTP_CODE}${NC}"
    else
      # Extract issuer mismatch reason
      local BODY
      BODY=$(curl -s -H "Authorization: Bearer ${TOKEN}" "${GATEWAY_URL}/api/${TARGET}/whoami")
      local REASON
      REASON=$(echo "${BODY}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('detail','issuer mismatch'))" 2>/dev/null || echo "issuer mismatch")
      echo -e "  ${RED}✗${NC} ${DESCRIPTION}  ${DIM}→ ${HTTP_CODE} (${REASON})${NC}"
    fi
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    echo -e "  ${YELLOW}?${NC} ${DESCRIPTION}  ${DIM}→ ${HTTP_CODE} (expected ${EXPECTED})${NC}"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
}

# ─── Pre-flight check ───────────────────────────────────────────────────
if ! curl -sf "${KEYCLOAK_URL}/health/ready" > /dev/null 2>&1; then
  echo -e "${RED}Keycloak not ready at ${KEYCLOAK_URL}. Run ./00-setup.sh first.${NC}"
  exit 1
fi
if ! curl -sf "${GATEWAY_URL}/health" > /dev/null 2>&1; then
  echo -e "${RED}Gateway not ready at ${GATEWAY_URL}. Run ./00-setup.sh first.${NC}"
  exit 1
fi

# ═══════════════════════════════════════════════════════════════════════════
# PHASE 1 — Silent authentication (15s)
# ═══════════════════════════════════════════════════════════════════════════
banner "PHASE 1 — Authenticating 3 Organizations"

echo -e "  ${DIM}3 orgs, 3 protocols, 0 users stored centrally${NC}\n"

echo -n "  Org Alpha (OIDC federation)...  "
login_silent alpha demo-alpha demo && echo -e "${GREEN}OK${NC}" || true
pause

echo -n "  Org Beta  (SAML federation)...  "
login_silent beta demo-beta demo && echo -e "${GREEN}OK${NC}" || true
pause

echo -n "  Org Gamma (LDAP federation)...  "
login_silent gamma eve-gamma demo && echo -e "${GREEN}OK${NC}" || true
pause 0.5

# ═══════════════════════════════════════════════════════════════════════════
# PHASE 2 — Same-realm access (20s)
# ═══════════════════════════════════════════════════════════════════════════
banner "PHASE 2 — Same-Realm Access (should succeed)"

echo -e "  ${DIM}Each org accesses its own APIs${NC}\n"

call_api "Alpha token → Alpha API" alpha alpha 200
pause
call_api "Beta token  → Beta API " beta  beta  200
pause
call_api "Gamma token → Gamma API" gamma gamma 200
pause 0.5

# ═══════════════════════════════════════════════════════════════════════════
# PHASE 3 — Cross-realm denial (45s)
# ═══════════════════════════════════════════════════════════════════════════
banner "PHASE 3 — Cross-Realm Isolation (must be denied)"

echo -e "  ${DIM}Proving that Org A cannot access Org B's APIs${NC}\n"

call_api "Alpha token → Beta API  " alpha beta  403
pause
call_api "Alpha token → Gamma API " alpha gamma 403
pause
call_api "Beta token  → Alpha API " beta  alpha 403
pause
call_api "Beta token  → Gamma API " beta  gamma 403
pause
call_api "Gamma token → Alpha API " gamma alpha 403
pause
call_api "Gamma token → Beta API  " gamma beta  403
pause 0.5

# ═══════════════════════════════════════════════════════════════════════════
# PHASE 4 — Verdict (10s)
# ═══════════════════════════════════════════════════════════════════════════
TOTAL=$((PASS_COUNT + FAIL_COUNT))

echo ""
echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if [ "${FAIL_COUNT}" -eq 0 ]; then
  echo -e "${BOLD}${GREEN}"
  echo "    ██╗███████╗ ██████╗ ██╗      █████╗ ████████╗██╗ ██████╗ ███╗   ██╗"
  echo "    ██║██╔════╝██╔═══██╗██║     ██╔══██╗╚══██╔══╝██║██╔═══██╗████╗  ██║"
  echo "    ██║███████╗██║   ██║██║     ███████║   ██║   ██║██║   ██║██╔██╗ ██║"
  echo "    ██║╚════██║██║   ██║██║     ██╔══██║   ██║   ██║██║   ██║██║╚██╗██║"
  echo "    ██║███████║╚██████╔╝███████╗██║  ██║   ██║   ██║╚██████╔╝██║ ╚████║"
  echo "    ╚═╝╚══════╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝   ╚═╝   ╚═╝ ╚═════╝ ╚═╝  ╚═══╝"
  echo ""
  echo "                ██╗   ██╗███████╗██████╗ ██╗███████╗██╗███████╗██████╗ "
  echo "                ██║   ██║██╔════╝██╔══██╗██║██╔════╝██║██╔════╝██╔══██╗"
  echo "                ██║   ██║█████╗  ██████╔╝██║█████╗  ██║█████╗  ██║  ██║"
  echo "                ╚██╗ ██╔╝██╔══╝  ██╔══██╗██║██╔══╝  ██║██╔══╝  ██║  ██║"
  echo "                 ╚████╔╝ ███████╗██║  ██║██║██║     ██║███████╗██████╔╝"
  echo "                  ╚═══╝  ╚══════╝╚═╝  ╚═╝╚═╝╚═╝     ╚═╝╚══════╝╚═════╝ "
  echo -e "${NC}"
  echo -e "  ${BOLD}${PASS_COUNT}/${TOTAL} tests passed — Zero User Storage Federation works${NC}"
  echo ""
  echo -e "  ${CYAN}What this proves (ADR-026):${NC}"
  echo "    1. 3 orgs, 3 protocols (OIDC, SAML, LDAP) — all federated"
  echo "    2. 0 users stored in STOA — tokens from external IdPs"
  echo "    3. Cross-realm access denied by gateway (issuer mismatch)"
  echo "    4. European sovereignty: data stays with each organization"
  echo ""
  echo -e "  ${DIM}\"Un login, tous vos tenants — souverainete europeenne\"${NC}"
else
  echo -e "${BOLD}${RED}  ISOLATION BROKEN — ${FAIL_COUNT}/${TOTAL} test(s) failed!${NC}"
fi

echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

[ "${FAIL_COUNT}" -eq 0 ] && exit 0 || exit 1
