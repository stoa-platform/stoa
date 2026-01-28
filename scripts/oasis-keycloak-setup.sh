#!/bin/bash
# =============================================================================
# 🎮 OASIS TENANT - KEYCLOAK USER SETUP
# =============================================================================
# Creates the 5 OASIS personas for Team Coca audit / dry-run demo.
#
# Usage:
#   KC_ADMIN_PASSWORD=<password> ./scripts/oasis-keycloak-setup.sh
#
# Or get password from K8s secret:
#   KC_ADMIN_PASSWORD=$(kubectl get secret keycloak-admin-secret -n stoa-system -o jsonpath='{.data.admin-password}' | base64 -d)
#   ./scripts/oasis-keycloak-setup.sh
#
# Personas:
#   🎮 Parzival  - wade@oasis.io           - namespace_developer - oasis
#   🏹 Art3mis   - samantha@oasis.io       - project_owner       - oasis
#   🔧 Aech      - helen@oasis.io          - namespace_developer - oasis
#   💀 Sorrento  - nolan@ioi.com           - tenant_admin        - ioi
#   🧙 Halliday  - james@gregarious.games  - security_officer    - oasis
# =============================================================================

set -e

# Configuration
KEYCLOAK_URL="${KEYCLOAK_URL:-https://auth.stoa.cab-i.com}"
REALM="${KEYCLOAK_REALM:-stoa}"
ADMIN_USER="${KC_ADMIN_USER:-admin}"
ADMIN_PASSWORD="${KC_ADMIN_PASSWORD:-}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo "╔═══════════════════════════════════════════════════════════════════════════╗"
echo "║  🎮 OASIS TENANT - KEYCLOAK SETUP                                         ║"
echo "║  Team Coca Audit Personas                                                 ║"
echo "╚═══════════════════════════════════════════════════════════════════════════╝"
echo ""
echo "Keycloak URL: ${KEYCLOAK_URL}"
echo "Realm: ${REALM}"
echo ""

# Check password
if [ -z "$ADMIN_PASSWORD" ]; then
    echo -e "${RED}Error: KC_ADMIN_PASSWORD not set${NC}"
    echo ""
    echo "Get it with:"
    echo "  kubectl get secret keycloak-admin-secret -n stoa-system -o jsonpath='{.data.admin-password}' | base64 -d"
    echo ""
    echo "Or:"
    echo "  export KC_ADMIN_PASSWORD=\$(kubectl get secret keycloak-admin-secret -n stoa-system -o jsonpath='{.data.admin-password}' | base64 -d)"
    echo "  ./scripts/oasis-keycloak-setup.sh"
    exit 1
fi

# Get admin token
echo "🔑 Getting admin token..."
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
echo -e "${GREEN}✓ Admin token obtained${NC}"

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

create_role_if_not_exists() {
    local role_name=$1
    local description=$2

    # Check if role exists
    local exists=$(curl -s -o /dev/null -w "%{http_code}" \
        "${KEYCLOAK_URL}/admin/realms/${REALM}/roles/${role_name}" \
        -H "Authorization: Bearer ${TOKEN}")

    if [ "$exists" = "404" ]; then
        echo "  Creating role: ${role_name}"
        curl -s -X POST "${KEYCLOAK_URL}/admin/realms/${REALM}/roles" \
            -H "Authorization: Bearer ${TOKEN}" \
            -H "Content-Type: application/json" \
            -d "{
                \"name\": \"${role_name}\",
                \"description\": \"${description}\"
            }" > /dev/null
        echo -e "    ${GREEN}[OK] Role created${NC}"
    else
        echo -e "  Role ${role_name} ${YELLOW}[EXISTS]${NC}"
    fi
}

create_user() {
    local username=$1
    local email=$2
    local first=$3
    local last=$4
    local password=$5
    local tenant=$6
    local emoji=$7

    echo ""
    echo -e "${BLUE}${emoji} Creating user: ${username}${NC} (${first} ${last})"
    echo "   Email: ${email}"
    echo "   Tenant: ${tenant}"

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
        echo -e "   ${GREEN}[OK] User created${NC}"
        return 0
    elif [ "$status" = "409" ]; then
        echo -e "   ${YELLOW}[SKIP] User already exists${NC}"
        return 0
    else
        echo -e "   ${RED}[FAIL] HTTP ${status}${NC}"
        echo "   Response: ${body}"
        return 1
    fi
}

get_user_id() {
    local email=$1
    curl -s "${KEYCLOAK_URL}/admin/realms/${REALM}/users?email=${email}&exact=true" \
        -H "Authorization: Bearer ${TOKEN}" | jq -r '.[0].id // empty'
}

assign_role() {
    local user_id=$1
    local role_name=$2

    echo "   Assigning role: ${role_name}"

    # Get role
    local role=$(curl -s "${KEYCLOAK_URL}/admin/realms/${REALM}/roles/${role_name}" \
        -H "Authorization: Bearer ${TOKEN}")

    if [ "$(echo "$role" | jq -r '.name // empty')" = "" ]; then
        echo -e "     ${RED}[FAIL] Role not found: ${role_name}${NC}"
        return 1
    fi

    # Assign role
    local status=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST "${KEYCLOAK_URL}/admin/realms/${REALM}/users/${user_id}/role-mappings/realm" \
        -H "Authorization: Bearer ${TOKEN}" \
        -H "Content-Type: application/json" \
        -d "[${role}]")

    if [ "$status" = "204" ] || [ "$status" = "200" ]; then
        echo -e "     ${GREEN}[OK] Role assigned${NC}"
        return 0
    else
        echo -e "     ${YELLOW}[WARN] HTTP ${status} (may already be assigned)${NC}"
        return 0
    fi
}

# =============================================================================
# CREATE ROLES (if they don't exist)
# =============================================================================

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 Ensuring roles exist..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

create_role_if_not_exists "namespace_developer" "Developer with access to namespace-scoped resources"
create_role_if_not_exists "project_owner" "Owner of a project, can create quests and manage project resources"
create_role_if_not_exists "tenant_admin" "Administrator of a tenant, full control over tenant resources"
create_role_if_not_exists "security_officer" "Security officer, approves critical operations"

# =============================================================================
# CREATE OASIS PERSONAS
# =============================================================================

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "👥 Creating OASIS Personas..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 🎮 Parzival (Wade Watts) - namespace_developer @ oasis
create_user "parzival" "wade@oasis.io" "Wade" "Watts" "parzival123" "oasis" "🎮"
USER_ID=$(get_user_id "wade@oasis.io")
if [ -n "$USER_ID" ]; then
    assign_role "$USER_ID" "namespace_developer"
fi

# 🏹 Art3mis (Samantha Cook) - project_owner @ oasis
create_user "art3mis" "samantha@oasis.io" "Samantha" "Cook" "art3mis123" "oasis" "🏹"
USER_ID=$(get_user_id "samantha@oasis.io")
if [ -n "$USER_ID" ]; then
    assign_role "$USER_ID" "project_owner"
fi

# 🔧 Aech (Helen Harris) - namespace_developer @ oasis
create_user "aech" "helen@oasis.io" "Helen" "Harris" "aech123" "oasis" "🔧"
USER_ID=$(get_user_id "helen@oasis.io")
if [ -n "$USER_ID" ]; then
    assign_role "$USER_ID" "namespace_developer"
fi

# 💀 Sorrento (Nolan Sorrento) - tenant_admin @ ioi
create_user "sorrento" "nolan@ioi.com" "Nolan" "Sorrento" "sorrento123" "ioi" "💀"
USER_ID=$(get_user_id "nolan@ioi.com")
if [ -n "$USER_ID" ]; then
    assign_role "$USER_ID" "tenant_admin"
fi

# 🧙 Halliday (James Halliday) - security_officer @ oasis
create_user "halliday" "james@gregarious.games" "James" "Halliday" "halliday123" "oasis" "🧙"
USER_ID=$(get_user_id "james@gregarious.games")
if [ -n "$USER_ID" ]; then
    assign_role "$USER_ID" "security_officer"
fi

# =============================================================================
# SUMMARY
# =============================================================================

echo ""
echo "╔═══════════════════════════════════════════════════════════════════════════╗"
echo "║  ✅ OASIS KEYCLOAK SETUP COMPLETE                                         ║"
echo "╚═══════════════════════════════════════════════════════════════════════════╝"
echo ""
echo "┌─────────────────────────────────────────────────────────────────────────────┐"
echo "│ Persona     │ Email                    │ Password     │ Role              │"
echo "├─────────────┼──────────────────────────┼──────────────┼───────────────────┤"
echo "│ 🎮 Parzival │ wade@oasis.io            │ parzival123  │ namespace_developer│"
echo "│ 🏹 Art3mis  │ samantha@oasis.io        │ art3mis123   │ project_owner     │"
echo "│ 🔧 Aech     │ helen@oasis.io           │ aech123      │ namespace_developer│"
echo "│ 💀 Sorrento │ nolan@ioi.com            │ sorrento123  │ tenant_admin      │"
echo "│ 🧙 Halliday │ james@gregarious.games   │ halliday123  │ security_officer  │"
echo "└─────────────┴──────────────────────────┴──────────────┴───────────────────┘"
echo ""
echo "Test login:"
echo "  curl -X POST '${KEYCLOAK_URL}/realms/${REALM}/protocol/openid-connect/token' \\"
echo "    -d 'client_id=stoa-portal' -d 'username=wade@oasis.io' \\"
echo "    -d 'password=parzival123' -d 'grant_type=password'"
echo ""
echo "Next steps:"
echo "  1. kubectl apply -f deploy/demo-rpo/oasis-tools.yaml"
echo "  2. ./scripts/team-coca-test-suite.sh"
echo ""
