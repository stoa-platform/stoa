#!/bin/bash
# =============================================================================
# Ready Player One Demo - Keycloak User Setup
# =============================================================================
# Creates the 3 RPO demo users in Keycloak with their roles.
#
# Usage:
#   KC_ADMIN_PASSWORD=<password> ./scripts/demo/setup-rpo-keycloak-users.sh
#
# Or get password from K8s secret:
#   KC_ADMIN_PASSWORD=$(kubectl get secret keycloak-admin-secret -n stoa-system -o jsonpath='{.data.admin-password}' | base64 -d)
#   ./scripts/demo/setup-rpo-keycloak-users.sh
# =============================================================================

set -e

# Configuration
KEYCLOAK_URL="${KEYCLOAK_URL:-https://auth.gostoa.dev}"
REALM="${KEYCLOAK_REALM:-stoa}"
ADMIN_USER="${KC_ADMIN_USER:-admin}"
ADMIN_PASSWORD="${KC_ADMIN_PASSWORD:-}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=============================================="
echo "Ready Player One Demo - Keycloak Setup"
echo "=============================================="
echo "Keycloak URL: ${KEYCLOAK_URL}"
echo "Realm: ${REALM}"
echo ""

# Check password
if [ -z "$ADMIN_PASSWORD" ]; then
    echo -e "${RED}Error: KC_ADMIN_PASSWORD not set${NC}"
    echo "Get it with: kubectl get secret keycloak-admin-secret -n stoa-system -o jsonpath='{.data.admin-password}' | base64 -d"
    exit 1
fi

# Get admin token
echo "Getting admin token..."
TOKEN=$(curl -s -X POST "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "client_id=admin-cli" \
    -d "username=${ADMIN_USER}" \
    -d "password=${ADMIN_PASSWORD}" \
    -d "grant_type=password" | jq -r '.access_token')

if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
    echo -e "${RED}Failed to get admin token${NC}"
    exit 1
fi
echo -e "${GREEN}Admin token obtained${NC}"

# Function to create user
create_user() {
    local username=$1
    local email=$2
    local first=$3
    local last=$4
    local password=$5
    local tenant=$6

    echo ""
    echo "Creating user: ${username} (${first} ${last})"

    local response=$(curl -s -w "\n%{http_code}" -X POST "${KEYCLOAK_URL}/admin/realms/${REALM}/users" \
        -H "Authorization: Bearer ${TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{
            \"username\": \"${username}\",
            \"email\": \"${email}\",
            \"firstName\": \"${first}\",
            \"lastName\": \"${last}\",
            \"enabled\": true,
            \"emailVerified\": true,
            \"attributes\": {
                \"tenant_id\": [\"${tenant}\"]
            },
            \"credentials\": [{
                \"type\": \"password\",
                \"value\": \"${password}\",
                \"temporary\": false
            }]
        }")

    local status=$(echo "$response" | tail -n1)
    local body=$(echo "$response" | head -n-1)

    if [ "$status" = "201" ]; then
        echo -e "  ${GREEN}[OK] User created${NC}"
        return 0
    elif [ "$status" = "409" ]; then
        echo -e "  ${YELLOW}[SKIP] User already exists${NC}"
        return 0
    else
        echo -e "  ${RED}[FAIL] HTTP ${status}${NC}"
        echo "  Response: ${body}"
        return 1
    fi
}

# Function to get user ID
get_user_id() {
    local username=$1
    curl -s "${KEYCLOAK_URL}/admin/realms/${REALM}/users?username=${username}&exact=true" \
        -H "Authorization: Bearer ${TOKEN}" | jq -r '.[0].id // empty'
}

# Function to assign realm role
assign_role() {
    local user_id=$1
    local role_name=$2

    echo "  Assigning role: ${role_name}"

    # Get role
    local role=$(curl -s "${KEYCLOAK_URL}/admin/realms/${REALM}/roles/${role_name}" \
        -H "Authorization: Bearer ${TOKEN}")

    if [ "$(echo "$role" | jq -r '.name // empty')" = "" ]; then
        echo -e "    ${RED}[FAIL] Role not found: ${role_name}${NC}"
        return 1
    fi

    # Assign role
    local status=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST "${KEYCLOAK_URL}/admin/realms/${REALM}/users/${user_id}/role-mappings/realm" \
        -H "Authorization: Bearer ${TOKEN}" \
        -H "Content-Type: application/json" \
        -d "[${role}]")

    if [ "$status" = "204" ] || [ "$status" = "200" ]; then
        echo -e "    ${GREEN}[OK] Role assigned${NC}"
        return 0
    else
        echo -e "    ${YELLOW}[WARN] HTTP ${status} (may already be assigned)${NC}"
        return 0
    fi
}

# =============================================================================
# Create RPO Users
# =============================================================================

echo ""
echo "=============================================="
echo "Creating Ready Player One Users"
echo "=============================================="

# Parzival (Wade Watts) - High Five tenant admin
create_user "parzival" "parzival@highfive.oasis" "Wade" "Watts" "Wade2045!" "high-five"
USER_ID=$(get_user_id "parzival")
if [ -n "$USER_ID" ]; then
    assign_role "$USER_ID" "tenant-admin"
fi

# Sorrento (Nolan Sorrento) - IOI tenant admin
create_user "sorrento" "sorrento@ioi.corp" "Nolan" "Sorrento" "Ioi2045!" "ioi"
USER_ID=$(get_user_id "sorrento")
if [ -n "$USER_ID" ]; then
    assign_role "$USER_ID" "tenant-admin"
fi

# Halliday (James Halliday) - Platform admin
create_user "halliday" "halliday@oasis.admin" "James" "Halliday" "Easter2045!" "oasis"
USER_ID=$(get_user_id "halliday")
if [ -n "$USER_ID" ]; then
    assign_role "$USER_ID" "cpi-admin"
fi

# =============================================================================
# Summary
# =============================================================================

echo ""
echo "=============================================="
echo "Ready Player One Demo - Setup Complete"
echo "=============================================="
echo ""
echo "Demo Credentials:"
echo "  parzival / Wade2045!   - High Five (resistance)"
echo "  sorrento / Ioi2045!    - IOI (corporation)"
echo "  halliday / Easter2045! - OASIS (platform admin)"
echo ""
echo "Test login:"
echo "  curl -X POST '${KEYCLOAK_URL}/realms/${REALM}/protocol/openid-connect/token' \\"
echo "    -d 'client_id=control-plane-ui' -d 'username=parzival' \\"
echo "    -d 'password=Wade2045!' -d 'grant_type=password'"
echo ""
