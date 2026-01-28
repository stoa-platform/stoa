#!/usr/bin/env bash
# =============================================================================
# STOA Federation Demo — Login
# Authenticates a user against a tenant realm via direct grant
# Usage: ./01-login.sh <realm: alpha|beta|gamma> <username> <password>
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOKEN_DIR="${SCRIPT_DIR}/.tokens"
mkdir -p "${TOKEN_DIR}"

GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

REALM="${1:-}"
USER="${2:-}"
PASS="${3:-}"

if [ -z "${REALM}" ] || [ -z "${USER}" ] || [ -z "${PASS}" ]; then
  echo "Usage: $0 <realm: alpha|beta|gamma> <username> <password>"
  echo ""
  echo "Examples:"
  echo "  $0 alpha demo-alpha demo"
  echo "  $0 beta  demo-beta  demo"
  echo "  $0 gamma eve-gamma  demo"
  exit 1
fi

KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:8080}"
REALM_NAME="demo-org-${REALM}"

# Client secrets per realm
case "${REALM}" in
  alpha) CLIENT_SECRET="alpha-demo-secret" ;;
  beta)  CLIENT_SECRET="beta-demo-secret" ;;
  gamma) CLIENT_SECRET="gamma-demo-secret" ;;
  *)
    echo -e "${RED}Unknown realm: ${REALM}${NC}"
    exit 1
    ;;
esac

echo -e "${CYAN}Authenticating ${USER} @ ${REALM_NAME}...${NC}"

RESPONSE=$(curl -s -X POST "${KEYCLOAK_URL}/realms/${REALM_NAME}/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "client_id=federation-demo" \
  -d "client_secret=${CLIENT_SECRET}" \
  -d "username=${USER}" \
  -d "password=${PASS}")

TOKEN=$(echo "${RESPONSE}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")

if [ -z "${TOKEN}" ] || [ "${TOKEN}" = "None" ]; then
  ERROR=$(echo "${RESPONSE}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error_description','Unknown error'))" 2>/dev/null || echo "Auth failed")
  echo -e "${RED}Login failed: ${ERROR}${NC}"
  exit 1
fi

# Save token
echo "${TOKEN}" > "${TOKEN_DIR}/${REALM}.token"

# Decode and display claims
echo -e "${GREEN}Login successful.${NC}"
echo ""
echo -e "${CYAN}Token claims:${NC}"
echo "${TOKEN}" | python3 -c "
import sys, json, base64
token = sys.stdin.read().strip()
payload = token.split('.')[1]
payload += '=' * (4 - len(payload) % 4)
claims = json.loads(base64.urlsafe_b64decode(payload))
for key in ['iss', 'sub', 'preferred_username', 'aud', 'stoa_realm', 'exp']:
    if key in claims:
        print(f'  {key}: {claims[key]}')
"

echo ""
echo "Token saved to ${TOKEN_DIR}/${REALM}.token"
