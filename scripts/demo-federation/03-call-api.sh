#!/usr/bin/env bash
# =============================================================================
# STOA Federation Demo — Call API
# Calls the mock gateway with a tenant-scoped token
# Usage: ./03-call-api.sh <realm: alpha|beta|gamma>
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOKEN_DIR="${SCRIPT_DIR}/.tokens"

GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

REALM="${1:-}"

if [ -z "${REALM}" ]; then
  echo "Usage: $0 <realm: alpha|beta|gamma>"
  exit 1
fi

# Use API token if available, fall back to user token
TOKEN_FILE="${TOKEN_DIR}/${REALM}-api.token"
if [ ! -f "${TOKEN_FILE}" ]; then
  TOKEN_FILE="${TOKEN_DIR}/${REALM}.token"
fi
if [ ! -f "${TOKEN_FILE}" ]; then
  echo -e "${RED}No token found for ${REALM}. Run ./01-login.sh first.${NC}"
  exit 1
fi

TOKEN=$(cat "${TOKEN_FILE}")
GATEWAY_URL="${GATEWAY_URL:-http://localhost:9000}"

echo -e "${CYAN}Calling API as tenant ${REALM}...${NC}"
echo -e "  GET ${GATEWAY_URL}/api/${REALM}/whoami"
echo ""

RESPONSE=$(curl -s -w "\n%{http_code}" \
  -H "Authorization: Bearer ${TOKEN}" \
  "${GATEWAY_URL}/api/${REALM}/whoami")

HTTP_CODE=$(echo "${RESPONSE}" | tail -1)
BODY=$(echo "${RESPONSE}" | sed '$d')

if [ "${HTTP_CODE}" = "200" ]; then
  echo -e "${GREEN}200 OK — Access granted${NC}"
else
  echo -e "${RED}${HTTP_CODE} — Access denied${NC}"
fi

echo ""
echo "${BODY}" | python3 -m json.tool 2>/dev/null || echo "${BODY}"
