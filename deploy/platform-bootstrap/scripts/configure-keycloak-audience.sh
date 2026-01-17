#!/bin/bash
# =============================================================================
# Configure Keycloak Audience Mappers
# =============================================================================
# This script configures Audience Mappers in Keycloak so that all client
# applications emit tokens with `aud: control-plane-api` (the Resource Server)
# instead of `aud: <client-id>`.
#
# This follows OAuth2/OIDC best practices where:
# - `aud` (audience) = the API/Resource Server that will consume the token
# - `azp` (authorized party) = the client application that requested the token
#
# Usage:
#   ./configure-keycloak-audience.sh
#
# Environment Variables:
#   KEYCLOAK_URL        - Keycloak base URL (default: https://auth.stoa.cab-i.com)
#   KEYCLOAK_REALM      - Realm name (default: stoa)
#   KEYCLOAK_ADMIN_USER - Admin username (default: admin)
#   KEYCLOAK_ADMIN_PASS - Admin password (required)
#   RESOURCE_SERVER_ID  - Target audience client ID (default: control-plane-api)
#   DRY_RUN             - Set to "true" to preview changes without applying
#
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
KEYCLOAK_URL="${KEYCLOAK_URL:-https://auth.stoa.cab-i.com}"
KEYCLOAK_REALM="${KEYCLOAK_REALM:-stoa}"
KEYCLOAK_ADMIN_USER="${KEYCLOAK_ADMIN_USER:-admin}"
KEYCLOAK_ADMIN_PASS="${KEYCLOAK_ADMIN_PASS:-}"
RESOURCE_SERVER_ID="${RESOURCE_SERVER_ID:-control-plane-api}"
DRY_RUN="${DRY_RUN:-false}"

# Clients to configure (space-separated)
CLIENTS_TO_CONFIGURE="${CLIENTS_TO_CONFIGURE:-control-plane-ui stoa-portal mcp-gateway-client}"

# Mapper configuration
MAPPER_NAME="api-audience-mapper"
MAPPER_PROTOCOL="openid-connect"
MAPPER_PROTOCOL_MAPPER="oidc-audience-mapper"

# =============================================================================
# Logging functions
# =============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "\n${BLUE}==>${NC} $1"
}

# =============================================================================
# Validation
# =============================================================================

if [[ -z "$KEYCLOAK_ADMIN_PASS" ]]; then
    log_error "KEYCLOAK_ADMIN_PASS environment variable is required"
    exit 1
fi

# =============================================================================
# Get Admin Token
# =============================================================================

log_step "Authenticating with Keycloak Admin API"

get_admin_token() {
    local response
    response=$(curl -s -X POST \
        "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "username=${KEYCLOAK_ADMIN_USER}" \
        -d "password=${KEYCLOAK_ADMIN_PASS}" \
        -d "grant_type=password" \
        -d "client_id=admin-cli")

    echo "$response" | jq -r '.access_token // empty'
}

ADMIN_TOKEN=$(get_admin_token)

if [[ -z "$ADMIN_TOKEN" ]]; then
    log_error "Failed to authenticate with Keycloak"
    exit 1
fi

log_success "Authenticated as ${KEYCLOAK_ADMIN_USER}"

# =============================================================================
# Helper Functions
# =============================================================================

# Get client UUID by client_id
get_client_uuid() {
    local client_id="$1"
    curl -s -X GET \
        "${KEYCLOAK_URL}/admin/realms/${KEYCLOAK_REALM}/clients?clientId=${client_id}" \
        -H "Authorization: Bearer ${ADMIN_TOKEN}" \
        | jq -r '.[0].id // empty'
}

# Get dedicated client scope ID
get_dedicated_scope_id() {
    local client_id="$1"
    local client_uuid="$2"

    # Try to get the dedicated client scope (format: <client_id>-dedicated)
    curl -s -X GET \
        "${KEYCLOAK_URL}/admin/realms/${KEYCLOAK_REALM}/clients/${client_uuid}/default-client-scopes" \
        -H "Authorization: Bearer ${ADMIN_TOKEN}" \
        | jq -r --arg name "${client_id}-dedicated" '.[] | select(.name == $name) | .id // empty'
}

# Check if mapper exists in client scope
mapper_exists_in_scope() {
    local scope_id="$1"
    local mapper_name="$2"

    local result
    result=$(curl -s -X GET \
        "${KEYCLOAK_URL}/admin/realms/${KEYCLOAK_REALM}/client-scopes/${scope_id}/protocol-mappers/models" \
        -H "Authorization: Bearer ${ADMIN_TOKEN}" \
        | jq -r --arg name "$mapper_name" '.[] | select(.name == $name) | .id // empty')

    [[ -n "$result" ]]
}

# Check if mapper exists directly on client
mapper_exists_in_client() {
    local client_uuid="$1"
    local mapper_name="$2"

    local result
    result=$(curl -s -X GET \
        "${KEYCLOAK_URL}/admin/realms/${KEYCLOAK_REALM}/clients/${client_uuid}/protocol-mappers/models" \
        -H "Authorization: Bearer ${ADMIN_TOKEN}" \
        | jq -r --arg name "$mapper_name" '.[] | select(.name == $name) | .id // empty')

    [[ -n "$result" ]]
}

# Create mapper in client scope
create_mapper_in_scope() {
    local scope_id="$1"
    local mapper_json="$2"

    curl -s -X POST \
        "${KEYCLOAK_URL}/admin/realms/${KEYCLOAK_REALM}/client-scopes/${scope_id}/protocol-mappers/models" \
        -H "Authorization: Bearer ${ADMIN_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "$mapper_json"
}

# Create mapper directly on client (fallback)
create_mapper_in_client() {
    local client_uuid="$1"
    local mapper_json="$2"

    curl -s -X POST \
        "${KEYCLOAK_URL}/admin/realms/${KEYCLOAK_REALM}/clients/${client_uuid}/protocol-mappers/models" \
        -H "Authorization: Bearer ${ADMIN_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "$mapper_json"
}

# =============================================================================
# Main Logic
# =============================================================================

log_step "Configuring Audience Mappers for Resource Server: ${RESOURCE_SERVER_ID}"

# Build mapper JSON
MAPPER_JSON=$(cat <<EOF
{
    "name": "${MAPPER_NAME}",
    "protocol": "${MAPPER_PROTOCOL}",
    "protocolMapper": "${MAPPER_PROTOCOL_MAPPER}",
    "consentRequired": false,
    "config": {
        "included.client.audience": "${RESOURCE_SERVER_ID}",
        "id.token.claim": "false",
        "access.token.claim": "true"
    }
}
EOF
)

log_info "Mapper configuration:"
echo "$MAPPER_JSON" | jq .

CONFIGURED_COUNT=0
SKIPPED_COUNT=0
FAILED_COUNT=0

for CLIENT_ID in $CLIENTS_TO_CONFIGURE; do
    log_step "Processing client: ${CLIENT_ID}"

    # Get client UUID
    CLIENT_UUID=$(get_client_uuid "$CLIENT_ID")

    if [[ -z "$CLIENT_UUID" ]]; then
        log_warn "Client '${CLIENT_ID}' not found in realm '${KEYCLOAK_REALM}' - skipping"
        ((SKIPPED_COUNT++))
        continue
    fi

    log_info "Found client UUID: ${CLIENT_UUID}"

    # Try to get dedicated client scope
    SCOPE_ID=$(get_dedicated_scope_id "$CLIENT_ID" "$CLIENT_UUID")

    if [[ -n "$SCOPE_ID" ]]; then
        log_info "Found dedicated scope: ${CLIENT_ID}-dedicated (${SCOPE_ID})"

        # Check if mapper already exists
        if mapper_exists_in_scope "$SCOPE_ID" "$MAPPER_NAME"; then
            log_success "Mapper '${MAPPER_NAME}' already exists in scope - skipping"
            ((SKIPPED_COUNT++))
            continue
        fi

        if [[ "$DRY_RUN" == "true" ]]; then
            log_warn "[DRY RUN] Would create mapper in scope ${CLIENT_ID}-dedicated"
            continue
        fi

        # Create mapper in dedicated scope
        log_info "Creating mapper in dedicated scope..."
        RESULT=$(create_mapper_in_scope "$SCOPE_ID" "$MAPPER_JSON")

        if [[ -z "$RESULT" || "$RESULT" == "null" ]]; then
            log_success "Mapper created successfully in scope"
            ((CONFIGURED_COUNT++))
        else
            log_error "Failed to create mapper: $RESULT"
            ((FAILED_COUNT++))
        fi
    else
        log_warn "No dedicated scope found for '${CLIENT_ID}' - using client-level mapper"

        # Check if mapper already exists on client
        if mapper_exists_in_client "$CLIENT_UUID" "$MAPPER_NAME"; then
            log_success "Mapper '${MAPPER_NAME}' already exists on client - skipping"
            ((SKIPPED_COUNT++))
            continue
        fi

        if [[ "$DRY_RUN" == "true" ]]; then
            log_warn "[DRY RUN] Would create mapper directly on client ${CLIENT_ID}"
            continue
        fi

        # Create mapper directly on client
        log_info "Creating mapper directly on client..."
        RESULT=$(create_mapper_in_client "$CLIENT_UUID" "$MAPPER_JSON")

        if [[ -z "$RESULT" || "$RESULT" == "null" ]]; then
            log_success "Mapper created successfully on client"
            ((CONFIGURED_COUNT++))
        else
            log_error "Failed to create mapper: $RESULT"
            ((FAILED_COUNT++))
        fi
    fi
done

# =============================================================================
# Summary
# =============================================================================

log_step "Summary"
echo -e "${GREEN}Configured:${NC} ${CONFIGURED_COUNT}"
echo -e "${YELLOW}Skipped:${NC} ${SKIPPED_COUNT}"
echo -e "${RED}Failed:${NC} ${FAILED_COUNT}"

if [[ "$DRY_RUN" == "true" ]]; then
    log_warn "This was a dry run - no changes were made"
    log_info "Set DRY_RUN=false to apply changes"
fi

# =============================================================================
# Verification Instructions
# =============================================================================

log_step "Verification"
echo -e "
To verify the configuration, obtain a token and decode it:

${BLUE}# Get a token (example with password grant for testing)${NC}
TOKEN=\$(curl -s -X POST '${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token' \\
    -d 'grant_type=password' \\
    -d 'client_id=control-plane-ui' \\
    -d 'username=<user>' \\
    -d 'password=<pass>' \\
    -d 'scope=openid' | jq -r '.access_token')

${BLUE}# Decode and check audience${NC}
echo \$TOKEN | cut -d. -f2 | base64 -d 2>/dev/null | jq '{aud, azp, iss}'

${BLUE}# Expected output:${NC}
{
  \"aud\": \"${RESOURCE_SERVER_ID}\",    ${GREEN}<-- Should be the API${NC}
  \"azp\": \"control-plane-ui\",          ${GREEN}<-- Should be the client${NC}
  \"iss\": \"${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}\"
}
"

if [[ $FAILED_COUNT -gt 0 ]]; then
    exit 1
fi

exit 0
