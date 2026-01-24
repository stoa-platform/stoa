#!/bin/bash
# =============================================================================
# Register Application in webMethods Gateway
# =============================================================================
# This script registers an application in the Gateway with the correct
# OIDC identifier to match the JWT 'azp' claim.
#
# Usage:
#   ./register-gateway-application.sh
#
# Environment Variables:
#   GATEWAY_URL         - Gateway admin URL (default: internal K8s service)
#   GATEWAY_USER        - Admin username (default: Administrator)
#   GATEWAY_PASSWORD    - Admin password (default: manage)
#   APP_NAME            - Application name (default: control-plane-ui)
#   APP_CLIENT_ID       - Keycloak client ID (default: control-plane-ui)
#   API_ID              - API ID to associate (optional)
#
# =============================================================================

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "\n${BLUE}==>${NC} $1"; }

# Configuration
GATEWAY_URL="${GATEWAY_URL:-http://apigateway.stoa-system.svc.cluster.local:5555}"
GATEWAY_USER="${GATEWAY_USER:-Administrator}"
GATEWAY_PASSWORD="${GATEWAY_PASSWORD:-manage}"
APP_NAME="${APP_NAME:-control-plane-ui}"
APP_CLIENT_ID="${APP_CLIENT_ID:-control-plane-ui}"
APP_DESCRIPTION="${APP_DESCRIPTION:-STOA Console UI - API Consumer application}"
CONTACT_EMAIL="${CONTACT_EMAIL:-admin@cab-i.com}"
API_ID="${API_ID:-}"

log_step "Registering Application: ${APP_NAME}"
log_info "Gateway: ${GATEWAY_URL}"
log_info "Client ID (azp): ${APP_CLIENT_ID}"

# =============================================================================
# Check if application exists
# =============================================================================

log_step "Checking existing applications"

APPS_RESPONSE=$(curl -s -u "${GATEWAY_USER}:${GATEWAY_PASSWORD}" \
    -H "Accept: application/json" \
    "${GATEWAY_URL}/rest/apigateway/applications" 2>/dev/null)

if [[ -z "$APPS_RESPONSE" ]]; then
    log_error "Failed to connect to Gateway"
    exit 1
fi

# Find existing application
EXISTING_APP=$(echo "$APPS_RESPONSE" | jq -r --arg name "$APP_NAME" \
    '.applications[]? | select(.name == $name)')

if [[ -n "$EXISTING_APP" ]]; then
    APP_ID=$(echo "$EXISTING_APP" | jq -r '.id')
    log_warn "Application '${APP_NAME}' already exists (ID: ${APP_ID})"

    # Check identifiers
    IDENTIFIERS=$(echo "$EXISTING_APP" | jq '.identifiers')
    log_info "Current identifiers: $IDENTIFIERS"

    # Check if azp identifier exists
    HAS_AZP=$(echo "$EXISTING_APP" | jq -r \
        '.identifiers[]? | select(.key == "openIdClaims" and .name == "azp") | .value[]?' | grep -c "$APP_CLIENT_ID" || true)

    if [[ "$HAS_AZP" -gt 0 ]]; then
        log_success "Application already has correct 'azp' identifier"
    else
        log_warn "Application missing 'azp' identifier - updating..."

        # Update application with correct identifier
        UPDATE_BODY=$(cat <<EOF
{
    "name": "${APP_NAME}",
    "description": "${APP_DESCRIPTION}",
    "contactEmails": ["${CONTACT_EMAIL}"],
    "identifiers": [
        {
            "key": "openIdClaims",
            "name": "azp",
            "value": ["${APP_CLIENT_ID}"]
        }
    ]
}
EOF
)

        UPDATE_RESULT=$(curl -s -X PUT \
            -u "${GATEWAY_USER}:${GATEWAY_PASSWORD}" \
            -H "Content-Type: application/json" \
            -H "Accept: application/json" \
            "${GATEWAY_URL}/rest/apigateway/applications/${APP_ID}" \
            -d "$UPDATE_BODY" 2>/dev/null)

        if echo "$UPDATE_RESULT" | jq -e '.id' > /dev/null 2>&1; then
            log_success "Application updated with 'azp' identifier"
        else
            log_error "Failed to update application: $UPDATE_RESULT"
            exit 1
        fi
    fi
else
    log_info "Application not found - creating new one"

    # Create application with azp identifier
    CREATE_BODY=$(cat <<EOF
{
    "name": "${APP_NAME}",
    "description": "${APP_DESCRIPTION}",
    "contactEmails": ["${CONTACT_EMAIL}"],
    "identifiers": [
        {
            "key": "openIdClaims",
            "name": "azp",
            "value": ["${APP_CLIENT_ID}"]
        }
    ],
    "subscription": false
}
EOF
)

    log_info "Creating application with body:"
    echo "$CREATE_BODY" | jq .

    CREATE_RESULT=$(curl -s -X POST \
        -u "${GATEWAY_USER}:${GATEWAY_PASSWORD}" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json" \
        "${GATEWAY_URL}/rest/apigateway/applications" \
        -d "$CREATE_BODY" 2>/dev/null)

    if echo "$CREATE_RESULT" | jq -e '.id' > /dev/null 2>&1; then
        APP_ID=$(echo "$CREATE_RESULT" | jq -r '.id')
        log_success "Application created (ID: ${APP_ID})"
    else
        log_error "Failed to create application: $CREATE_RESULT"
        exit 1
    fi
fi

# =============================================================================
# Associate with API (if specified)
# =============================================================================

if [[ -n "$API_ID" ]]; then
    log_step "Associating application with API: ${API_ID}"

    ASSOC_BODY=$(cat <<EOF
{
    "apiIDs": ["${API_ID}"]
}
EOF
)

    ASSOC_RESULT=$(curl -s -X PUT \
        -u "${GATEWAY_USER}:${GATEWAY_PASSWORD}" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json" \
        "${GATEWAY_URL}/rest/apigateway/applications/${APP_ID}/apis" \
        -d "$ASSOC_BODY" 2>/dev/null)

    log_success "Application associated with API"
fi

# =============================================================================
# Summary
# =============================================================================

log_step "Summary"
echo -e "Application: ${GREEN}${APP_NAME}${NC}"
echo -e "ID: ${GREEN}${APP_ID}${NC}"
echo -e "Client ID (azp): ${GREEN}${APP_CLIENT_ID}${NC}"

log_step "Verification"
echo -e "
To test, get a token and make a request:

${BLUE}# The JWT token should have:${NC}
{
  \"azp\": \"${APP_CLIENT_ID}\",    ${GREEN}<-- Gateway will match this${NC}
  \"aud\": \"control-plane-api\"
}

${BLUE}# Test API call:${NC}
curl -H 'Authorization: Bearer \$TOKEN' \\
    https://apis.gostoa.dev/gateway/Control-Plane-API/2.0/health/live
"

exit 0
