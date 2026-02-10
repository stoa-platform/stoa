#!/usr/bin/env bash
# =============================================================================
# STOA Federation Demo — Integrated Setup
# Seeds LDAP and syncs Keycloak when running with the main docker-compose stack.
#
# Prerequisites:
#   docker compose --profile federation up -d  (from deploy/docker-compose/)
#
# The federation realms are auto-imported by Keycloak on first start.
# This script only needs to run once to seed LDAP users for gamma org.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:8080}"
GATEWAY_URL="${GATEWAY_URL:-http://localhost:9000}"
LDAP_CONTAINER="${LDAP_CONTAINER:-stoa-federation-ldap}"

echo -e "${GREEN}=== STOA Federation Demo — Integrated Setup ===${NC}"
echo ""

# Check Keycloak is ready
echo -e "${YELLOW}Checking Keycloak...${NC}"
if ! curl -sf "${KEYCLOAK_URL}/health/ready" > /dev/null 2>&1; then
  echo -e "${RED}Keycloak not ready at ${KEYCLOAK_URL}${NC}"
  echo "Start the stack first: docker compose --profile federation up -d"
  exit 1
fi
echo -e "${GREEN}Keycloak is ready.${NC}"

# Check federation gateway
echo -e "${YELLOW}Checking federation gateway...${NC}"
if ! curl -sf "${GATEWAY_URL}/health" > /dev/null 2>&1; then
  echo -e "${RED}Federation gateway not ready at ${GATEWAY_URL}${NC}"
  echo "Did you start with --profile federation?"
  exit 1
fi
echo -e "${GREEN}Federation gateway is ready.${NC}"

# Seed LDAP data for gamma org
echo -e "${YELLOW}Seeding LDAP data for gamma org...${NC}"
LDAP_RESULT=""
for i in 1 2 3 4 5; do
  LDAP_RESULT=$(docker exec "${LDAP_CONTAINER}" ldapadd -x -H ldap://localhost:389 \
    -D "cn=admin,dc=demo,dc=stoa" -w "admin-password" \
    -f /ldif-seed/seed.ldif 2>&1) && break
  echo -n "."
  sleep 2
done
if echo "${LDAP_RESULT}" | grep -q "adding new entry" 2>/dev/null; then
  echo -e "${GREEN}LDAP users seeded (eve-gamma, frank-gamma).${NC}"
elif echo "${LDAP_RESULT}" | grep -q "Already exists" 2>/dev/null; then
  echo -e "${YELLOW}LDAP users already seeded (idempotent).${NC}"
else
  echo -e "${YELLOW}LDAP seed: ${LDAP_RESULT}${NC}"
fi

# Trigger LDAP sync in Keycloak for gamma realm
echo -e "${YELLOW}Triggering LDAP sync for demo-org-gamma...${NC}"
ADMIN_TOKEN=$(curl -s -X POST "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=admin-cli" \
  -d "username=admin" \
  -d "password=${KEYCLOAK_ADMIN_PASSWORD:-admin}" \
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
    echo -e "${YELLOW}LDAP provider not found — will sync on first login.${NC}"
  fi
else
  echo -e "${YELLOW}Could not get admin token — LDAP sync will happen on first login.${NC}"
fi

# Verify realms exist
echo ""
echo -e "${YELLOW}Verifying federation realms...${NC}"
REALMS_OK=true
for REALM in idp-source-alpha idp-source-beta demo-org-alpha demo-org-beta demo-org-gamma; do
  if curl -sf "${KEYCLOAK_URL}/realms/${REALM}" > /dev/null 2>&1; then
    echo -e "  ${GREEN}OK${NC}  ${REALM}"
  else
    echo -e "  ${RED}MISSING${NC}  ${REALM}"
    REALMS_OK=false
  fi
done

echo ""
if [ "${REALMS_OK}" = true ]; then
  echo -e "${GREEN}=== Federation Demo Ready ===${NC}"
  echo ""
  echo "  Keycloak Admin:      ${KEYCLOAK_URL}/admin  (admin/admin)"
  echo "  Federation Gateway:  ${GATEWAY_URL}/health"
  echo ""
  echo "  Run the isolation test (the money shot):"
  echo "    ./scripts/demo-federation/04-test-isolation.sh"
else
  echo -e "${RED}Some realms are missing. Check Keycloak logs.${NC}"
  exit 1
fi
