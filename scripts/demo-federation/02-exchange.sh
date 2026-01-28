#!/usr/bin/env bash
# =============================================================================
# STOA Federation Demo — Token Exchange (RFC 8693)
# Exchanges a user token for a scoped API token
# Usage: ./02-exchange.sh <realm: alpha|beta|gamma> [target-audience]
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOKEN_DIR="${SCRIPT_DIR}/.tokens"

GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

REALM="${1:-}"
TARGET_AUDIENCE="${2:-stoa-federation-api}"

if [ -z "${REALM}" ]; then
  echo "Usage: $0 <realm: alpha|beta|gamma> [target-audience]"
  echo ""
  echo "Example: $0 alpha stoa-federation-api"
  exit 1
fi

TOKEN_FILE="${TOKEN_DIR}/${REALM}.token"
if [ ! -f "${TOKEN_FILE}" ]; then
  echo -e "${RED}No token found for ${REALM}. Run ./01-login.sh first.${NC}"
  exit 1
fi

USER_TOKEN=$(cat "${TOKEN_FILE}")
KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:8080}"
REALM_NAME="demo-org-${REALM}"

case "${REALM}" in
  alpha) CLIENT_SECRET="alpha-demo-secret" ;;
  beta)  CLIENT_SECRET="beta-demo-secret" ;;
  gamma) CLIENT_SECRET="gamma-demo-secret" ;;
esac

echo -e "${CYAN}Token Exchange (RFC 8693)${NC}"
echo -e "  Realm:    ${REALM_NAME}"
echo -e "  Audience: ${TARGET_AUDIENCE}"
echo ""

RESPONSE=$(curl -s -X POST "${KEYCLOAK_URL}/realms/${REALM_NAME}/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=urn:ietf:params:oauth:grant-type:token-exchange" \
  -d "client_id=federation-demo" \
  -d "client_secret=${CLIENT_SECRET}" \
  -d "subject_token=${USER_TOKEN}" \
  -d "subject_token_type=urn:ietf:params:oauth:token-type:access_token" \
  -d "requested_token_type=urn:ietf:params:oauth:token-type:access_token" \
  -d "audience=${TARGET_AUDIENCE}")

EXCHANGED_TOKEN=$(echo "${RESPONSE}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")

if [ -z "${EXCHANGED_TOKEN}" ] || [ "${EXCHANGED_TOKEN}" = "None" ]; then
  echo -e "${YELLOW}Token exchange not available (Keycloak preview feature).${NC}"
  echo -e "${YELLOW}Using original token instead — isolation demo still works.${NC}"
  echo ""
  ERROR=$(echo "${RESPONSE}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('error_description', d.get('error','Unknown')))" 2>/dev/null || echo "")
  echo -e "  Detail: ${ERROR}"
  echo ""
  # Copy original token as API token
  cp "${TOKEN_FILE}" "${TOKEN_DIR}/${REALM}-api.token"
  echo "Using user token as API token."
else
  echo -e "${GREEN}Token exchange successful.${NC}"
  echo "${EXCHANGED_TOKEN}" > "${TOKEN_DIR}/${REALM}-api.token"
  echo ""
  echo -e "${CYAN}Exchanged token claims:${NC}"
  echo "${EXCHANGED_TOKEN}" | python3 -c "
import sys, json, base64
token = sys.stdin.read().strip()
payload = token.split('.')[1]
payload += '=' * (4 - len(payload) % 4)
claims = json.loads(base64.urlsafe_b64decode(payload))
for key in ['iss', 'sub', 'aud', 'stoa_realm', 'exp']:
    if key in claims:
        print(f'  {key}: {claims[key]}')
"
fi

echo ""
echo "API token saved to ${TOKEN_DIR}/${REALM}-api.token"
