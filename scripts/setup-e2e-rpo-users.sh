#!/bin/bash
# Copyright 2026 STOA Platform Authors
# SPDX-License-Identifier: Apache-2.0
#===============================================================================
# Setup E2E Test Users - Ready Player One Theme
# Creates all 6 RPO personas in Keycloak for E2E testing
#===============================================================================

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
CYAN='\033[0;36m'
NC='\033[0m'

log_info()    { echo -e "${CYAN}[i]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[!]${NC} $1"; }
log_error()   { echo -e "${RED}[X]${NC} $1"; }

echo "=============================================="
echo "STOA E2E Users Setup - Ready Player One"
echo "=============================================="
echo "Keycloak URL: ${KEYCLOAK_URL}"
echo "Realm: ${REALM}"
echo ""

# Check password
if [ -z "$ADMIN_PASSWORD" ]; then
    log_error "KC_ADMIN_PASSWORD not set"
    echo "Get it with: kubectl get secret keycloak-admin-secret -n stoa-system -o jsonpath='{.data.admin-password}' | base64 -d"
    exit 1
fi

# Get admin token
log_info "Getting admin token..."
TOKEN=$(curl -s -X POST "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "client_id=admin-cli" \
    -d "username=${ADMIN_USER}" \
    -d "password=${ADMIN_PASSWORD}" \
    -d "grant_type=password" | jq -r '.access_token')

if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
    log_error "Failed to get admin token"
    exit 1
fi
log_success "Admin token obtained"

# Function to create user
create_user() {
    local username=$1
    local email=$2
    local first=$3
    local last=$4
    local password=$5
    local tenant=$6
    local role=$7

    echo ""
    log_info "Creating user: ${username} (${first} ${last}) - ${role}"

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

    if [ "$status" = "201" ]; then
        log_success "User created"

        # Get user ID and assign role
        local user_id=$(curl -s "${KEYCLOAK_URL}/admin/realms/${REALM}/users?username=${username}&exact=true" \
            -H "Authorization: Bearer ${TOKEN}" | jq -r '.[0].id // empty')

        if [ -n "$user_id" ] && [ "$user_id" != "null" ]; then
            assign_role "$user_id" "$role"
        fi
        return 0
    elif [ "$status" = "409" ]; then
        log_warning "User already exists - updating password"

        # Get user ID
        local user_id=$(curl -s "${KEYCLOAK_URL}/admin/realms/${REALM}/users?username=${username}&exact=true" \
            -H "Authorization: Bearer ${TOKEN}" | jq -r '.[0].id // empty')

        if [ -n "$user_id" ] && [ "$user_id" != "null" ]; then
            # Reset password
            curl -s -X PUT "${KEYCLOAK_URL}/admin/realms/${REALM}/users/${user_id}/reset-password" \
                -H "Authorization: Bearer ${TOKEN}" \
                -H "Content-Type: application/json" \
                -d "{\"type\":\"password\",\"value\":\"${password}\",\"temporary\":false}"
            log_success "Password updated"
            assign_role "$user_id" "$role"
        fi
        return 0
    else
        log_error "HTTP ${status}"
        return 1
    fi
}

# Function to assign role
assign_role() {
    local user_id=$1
    local role_name=$2

    log_info "  Assigning role: ${role_name}"

    local role=$(curl -s "${KEYCLOAK_URL}/admin/realms/${REALM}/roles/${role_name}" \
        -H "Authorization: Bearer ${TOKEN}")

    if [ "$(echo "$role" | jq -r '.name // empty')" = "" ]; then
        log_warning "  Role not found: ${role_name}"
        return 0
    fi

    local status=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST "${KEYCLOAK_URL}/admin/realms/${REALM}/users/${user_id}/role-mappings/realm" \
        -H "Authorization: Bearer ${TOKEN}" \
        -H "Content-Type: application/json" \
        -d "[${role}]")

    if [ "$status" = "204" ] || [ "$status" = "200" ]; then
        log_success "  Role assigned"
    fi
}

echo ""
echo "=============================================="
echo "Creating Ready Player One Users"
echo "=============================================="

# HIGH-FIVE Tenant (the good guys)
create_user "parzival" "parzival@high-five.io" "Wade" "Watts" "Wade2045!" "high-five" "tenant-admin"
create_user "art3mis" "art3mis@high-five.io" "Samantha" "Cook" "Art3mis2045!" "high-five" "devops"
create_user "aech" "aech@high-five.io" "Helen" "Harris" "Aech2045!" "high-five" "viewer"

# IOI Tenant (the competitors)
create_user "sorrento" "sorrento@ioi.corp" "Nolan" "Sorrento" "Ioi2045!" "ioi" "tenant-admin"
create_user "i-r0k" "i-r0k@ioi.corp" "Todd" "Paluga" "Ir0k2045!" "ioi" "viewer"

# Platform Admin
create_user "anorak" "anorak@gostoa.dev" "James" "Halliday" "Anorak2045!" "oasis" "cpi-admin"

echo ""
echo "=============================================="
echo "E2E Users Setup Complete"
echo "=============================================="
echo ""
echo "Credentials for GitHub Secrets:"
echo ""
echo "  PARZIVAL_USER=parzival"
echo "  PARZIVAL_PASSWORD=Wade2045!"
echo ""
echo "  ART3MIS_USER=art3mis"
echo "  ART3MIS_PASSWORD=Art3mis2045!"
echo ""
echo "  AECH_USER=aech"
echo "  AECH_PASSWORD=Aech2045!"
echo ""
echo "  SORRENTO_USER=sorrento"
echo "  SORRENTO_PASSWORD=Ioi2045!"
echo ""
echo "  I_R0K_USER=i-r0k"
echo "  I_R0K_PASSWORD=Ir0k2045!"
echo ""
echo "  ANORAK_USER=anorak"
echo "  ANORAK_PASSWORD=Anorak2045!"
echo ""
