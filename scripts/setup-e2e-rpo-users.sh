#!/bin/bash
# Copyright 2026 STOA Platform Authors
# SPDX-License-Identifier: Apache-2.0
#===============================================================================
# Setup E2E Test Users - Ready Player One Theme
# Creates all 6 RPO personas in Keycloak for E2E testing
#===============================================================================

set -euo pipefail
set +x

# Demo accounts must never target a shared production realm by default.
if [ "${KEYCLOAK_BOOTSTRAP_ENV:-prod}" != "dev" ]; then
  echo "This account seeder requires KEYCLOAK_BOOTSTRAP_ENV=dev." >&2
  exit 1
fi
: "${KEYCLOAK_URL:?Set an explicit development Keycloak URL}"
: "${KEYCLOAK_REALM:?Set a dedicated development realm}"
case "$KEYCLOAK_REALM" in
  stoa|master) echo "A dedicated development realm is required." >&2; exit 1 ;;
esac

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

: "${PARZIVAL_PASSWORD:?PARZIVAL_PASSWORD is required}"
: "${ART3MIS_PASSWORD:?ART3MIS_PASSWORD is required}"
: "${AECH_PASSWORD:?AECH_PASSWORD is required}"
: "${SORRENTO_PASSWORD:?SORRENTO_PASSWORD is required}"
: "${I_R0K_PASSWORD:?I_R0K_PASSWORD is required}"
: "${ANORAK_PASSWORD:?ANORAK_PASSWORD is required}"

# Get admin token
log_info "Getting admin token..."
# shellcheck source=scripts/lib/secret-input.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/lib/secret-input.sh"
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

    local response

    response=$(curl -s -w "\n%{http_code}" -X POST "${KEYCLOAK_URL}/admin/realms/${REALM}/users" \
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

    local status

    status=$(echo "$response" | tail -n1)

    if [ "$status" = "201" ]; then
        log_success "User created"

        # Get user ID and assign role
        local user_id
        user_id=$(curl -s "${KEYCLOAK_URL}/admin/realms/${REALM}/users?username=${username}&exact=true" \
            -H "Authorization: Bearer ${TOKEN}" | jq -r '.[0].id // empty')

        if [ -n "$user_id" ] && [ "$user_id" != "null" ]; then
            assign_role "$user_id" "$role"
        fi
        return 0
    elif [ "$status" = "409" ]; then
        log_warning "User already exists - updating password"

        # Get user ID
        local user_id
        user_id=$(curl -s "${KEYCLOAK_URL}/admin/realms/${REALM}/users?username=${username}&exact=true" \
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

    local role

    role=$(curl -s "${KEYCLOAK_URL}/admin/realms/${REALM}/roles/${role_name}" \
        -H "Authorization: Bearer ${TOKEN}")

    if [ "$(echo "$role" | jq -r '.name // empty')" = "" ]; then
        log_warning "  Role not found: ${role_name}"
        return 0
    fi

    local status

    status=$(curl -s -o /dev/null -w "%{http_code}" \
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
create_user "parzival" "parzival@example.com" "Wade" "Watts" "${PARZIVAL_PASSWORD}" "high-five" "tenant-admin"
create_user "art3mis" "art3mis@example.com" "Samantha" "Cook" "${ART3MIS_PASSWORD}" "high-five" "devops"
create_user "aech" "aech@example.com" "Helen" "Harris" "${AECH_PASSWORD}" "high-five" "viewer"

# IOI Tenant (the competitors)
create_user "sorrento" "sorrento@example.com" "Nolan" "Sorrento" "${SORRENTO_PASSWORD}" "ioi" "tenant-admin"
create_user "i-r0k" "i-r0k@example.com" "Todd" "Paluga" "${I_R0K_PASSWORD}" "ioi" "viewer"

# Platform Admin
create_user "anorak" "anorak@example.com" "James" "Halliday" "${ANORAK_PASSWORD}" "oasis" "cpi-admin"

echo ""
echo "=============================================="
echo "E2E Users Setup Complete"
echo "=============================================="
echo ""
echo "Credentials are supplied by the operator; retain them in the on-site secret store."
