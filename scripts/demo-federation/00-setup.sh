#!/usr/bin/env bash
# =============================================================================
# STOA Federation Demo — Setup
# Starts all containers and waits for readiness
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="${SCRIPT_DIR}/../../deploy/demo-federation"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}=== STOA Federation Demo — Setup ===${NC}"
echo ""

# Ensure .env exists
if [ ! -f "${COMPOSE_DIR}/.env" ]; then
  echo -e "${YELLOW}Creating .env from .env.example...${NC}"
  cp "${COMPOSE_DIR}/.env.example" "${COMPOSE_DIR}/.env"
fi

# Start stack
echo -e "${YELLOW}Starting Docker Compose stack...${NC}"
docker compose -f "${COMPOSE_DIR}/docker-compose.yml" up -d

# Wait for Keycloak
echo -e "${YELLOW}Waiting for Keycloak to be ready...${NC}"
KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:8080}"
until curl -sf "${KEYCLOAK_URL}/health/ready" > /dev/null 2>&1; do
  echo -n "."
  sleep 3
done
echo ""
echo -e "${GREEN}Keycloak is ready.${NC}"

# Wait for mock gateway
echo -e "${YELLOW}Waiting for mock gateway...${NC}"
GATEWAY_URL="${GATEWAY_URL:-http://localhost:9000}"
until curl -sf "${GATEWAY_URL}/health" > /dev/null 2>&1; do
  echo -n "."
  sleep 2
done
echo ""
echo -e "${GREEN}Mock gateway is ready.${NC}"

# Seed LDAP data (osixia bootstrap is unreliable with bind mounts)
echo -e "${YELLOW}Seeding LDAP data for gamma org...${NC}"
for i in 1 2 3 4 5; do
  LDAP_RESULT=$(docker exec stoa-federation-ldap ldapadd -x -H ldap://localhost:389 \
    -D "cn=admin,dc=demo,dc=stoa" -w "admin-password" \
    -f /ldif-seed/seed.ldif 2>&1) && break
  echo -n "."
  sleep 2
done
if echo "${LDAP_RESULT}" | grep -q "adding new entry" 2>/dev/null; then
  echo -e "${GREEN}LDAP users seeded (eve-gamma, frank-gamma).${NC}"
else
  echo -e "${YELLOW}LDAP seed result: ${LDAP_RESULT}${NC}"
fi

# Trigger LDAP sync in Keycloak for gamma realm
echo -e "${YELLOW}Triggering LDAP sync for demo-org-gamma...${NC}"
ADMIN_TOKEN=$(curl -s -X POST "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=admin-cli" \
  -d "username=admin" \
  -d "password=admin" \
  -d "grant_type=password" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")

if [ -n "${ADMIN_TOKEN}" ] && [ "${ADMIN_TOKEN}" != "None" ]; then
  COMPONENT_ID=$(curl -s -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    "${KEYCLOAK_URL}/admin/realms/demo-org-gamma/components?type=org.keycloak.storage.UserStorageProvider" \
    | python3 -c "import sys,json; data=json.load(sys.stdin); print(data[0]['id'] if data else '')" 2>/dev/null || echo "")

  if [ -n "${COMPONENT_ID}" ]; then
    curl -s -X POST -H "Authorization: Bearer ${ADMIN_TOKEN}" \
      "${KEYCLOAK_URL}/admin/realms/demo-org-gamma/user-storage/${COMPONENT_ID}/sync?action=triggerFullSync" > /dev/null 2>&1
    echo -e "${GREEN}LDAP sync triggered.${NC}"
  else
    echo -e "${YELLOW}LDAP provider not found — Keycloak will sync on first login attempt.${NC}"
  fi
else
  echo -e "${YELLOW}Admin API requires HTTPS — LDAP sync will happen on first login attempt.${NC}"
fi

echo ""
echo -e "${GREEN}=== Federation Demo Stack Ready ===${NC}"
echo ""
echo "  Keycloak Admin:  ${KEYCLOAK_URL}/admin  (admin/admin)"
echo "  Mock Gateway:    ${GATEWAY_URL}/health"
echo ""
echo "  Realms:"
echo "    - idp-source-alpha  (OIDC source)"
echo "    - idp-source-beta   (SAML source)"
echo "    - demo-org-alpha    (OIDC federation)"
echo "    - demo-org-beta     (SAML federation)"
echo "    - demo-org-gamma    (LDAP federation)"
echo ""
echo "  Next: ./01-login.sh alpha demo-alpha demo"
