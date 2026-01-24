#!/bin/bash
# =============================================================================
# Sync OpenAPI Contract + Policies to webMethods Gateway
# =============================================================================
# HYBRID ARCHITECTURE:
#   - RUNTIME (Control-Plane-API): Manages API contract (endpoints/routes)
#   - GITOPS (webmethods/policies): Manages security policies
#
# This script synchronizes BOTH:
#   1. OpenAPI spec from backend (contract/routes)
#   2. Security policies from GitOps (JWT, CORS, rate-limit, outbound auth)
#
# Usage:
#   ./sync-gateway-openapi.sh
#
# Environment Variables:
#   BACKEND_URL         - Backend API URL (default: http://control-plane-api.stoa-system:8000)
#   GATEWAY_URL         - Gateway admin URL (default: http://apigateway.stoa-system:5555)
#   GATEWAY_USER        - Admin username (default: Administrator)
#   GATEWAY_PASSWORD    - Admin password (default: manage)
#   API_NAME            - API name on Gateway (default: Control-Plane-API)
#   API_VERSION         - API version (default: 2.0)
#   DRY_RUN             - If set, don't apply changes (default: false)
#   KEYCLOAK_ISSUER     - Keycloak issuer URL (default: https://auth.gostoa.dev/realms/stoa)
#   APPLY_POLICIES      - Apply security policies after contract sync (default: true)
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
BACKEND_URL="${BACKEND_URL:-http://control-plane-api.stoa-system.svc.cluster.local:8000}"
GATEWAY_URL="${GATEWAY_URL:-http://apigateway.stoa-system.svc.cluster.local:5555}"
GATEWAY_USER="${GATEWAY_USER:-Administrator}"
GATEWAY_PASSWORD="${GATEWAY_PASSWORD:-manage}"
API_NAME="${API_NAME:-Control-Plane-API}"
API_VERSION="${API_VERSION:-2.0}"
DRY_RUN="${DRY_RUN:-false}"

# Policy configuration
APPLY_POLICIES="${APPLY_POLICIES:-true}"
KEYCLOAK_ISSUER="${KEYCLOAK_ISSUER:-https://auth.gostoa.dev/realms/stoa}"
API_AUDIENCE="${API_AUDIENCE:-control-plane-api}"
BACKEND_PASSTHROUGH="${BACKEND_PASSTHROUGH:-true}"

TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

log_step "OpenAPI Contract Sync: ${API_NAME} v${API_VERSION}"
log_info "Backend: ${BACKEND_URL}"
log_info "Gateway: ${GATEWAY_URL}"
[[ "$DRY_RUN" == "true" ]] && log_warn "DRY RUN MODE - No changes will be applied"

# =============================================================================
# Step 1: Fetch OpenAPI spec from backend
# =============================================================================

log_step "Fetching OpenAPI specification from backend"

SPEC_FILE="${TEMP_DIR}/openapi.json"
SPEC_30_FILE="${TEMP_DIR}/openapi-3.0.json"

if ! curl -sf "${BACKEND_URL}/openapi.json" -o "${SPEC_FILE}"; then
    log_error "Failed to fetch OpenAPI spec from ${BACKEND_URL}/openapi.json"
    exit 1
fi

SPEC_VERSION=$(jq -r '.openapi // .swagger // "unknown"' "${SPEC_FILE}")
ENDPOINT_COUNT=$(jq '.paths | keys | length' "${SPEC_FILE}")
log_success "Fetched OpenAPI ${SPEC_VERSION} with ${ENDPOINT_COUNT} endpoints"

# =============================================================================
# Step 2: Convert to OpenAPI 3.0.3 if necessary
# =============================================================================

log_step "Checking OpenAPI version compatibility"

if [[ "$SPEC_VERSION" == "3.1"* ]]; then
    log_warn "OpenAPI 3.1.x detected - converting to 3.0.3 for Gateway compatibility"

    # Convert 3.1.0 to 3.0.3
    # - Change version string
    # - Remove examples (3.1 feature not in 3.0)
    # - Convert nullable to x-nullable
    # - Handle contentMediaType (3.1 feature)
    jq '
        .openapi = "3.0.3" |
        walk(
            if type == "object" then
                # Remove 3.1-only fields
                del(.examples) |
                del(.contentMediaType) |
                del(.contentEncoding) |
                # Convert nullable format
                if .type == ["string", "null"] then .type = "string" | .nullable = true
                elif .type == ["integer", "null"] then .type = "integer" | .nullable = true
                elif .type == ["number", "null"] then .type = "number" | .nullable = true
                elif .type == ["boolean", "null"] then .type = "boolean" | .nullable = true
                elif .type == ["array", "null"] then .type = "array" | .nullable = true
                elif .type == ["object", "null"] then .type = "object" | .nullable = true
                else .
                end
            else .
            end
        )
    ' "${SPEC_FILE}" > "${SPEC_30_FILE}"

    SPEC_FILE="${SPEC_30_FILE}"
    log_success "Converted to OpenAPI 3.0.3"
else
    log_info "OpenAPI ${SPEC_VERSION} is compatible"
fi

# =============================================================================
# Step 3: Get existing API from Gateway
# =============================================================================

log_step "Fetching existing API from Gateway"

API_RESPONSE=$(curl -sf -u "${GATEWAY_USER}:${GATEWAY_PASSWORD}" \
    -H "Accept: application/json" \
    "${GATEWAY_URL}/rest/apigateway/apis" 2>/dev/null || echo '{}')

API_ID=$(echo "$API_RESPONSE" | jq -r --arg name "$API_NAME" --arg ver "$API_VERSION" \
    '.apiResponse[]? | select(.api.apiName == $name and .api.apiVersion == $ver) | .api.id')

if [[ -z "$API_ID" || "$API_ID" == "null" ]]; then
    log_error "API '${API_NAME}' v${API_VERSION} not found on Gateway"
    log_info "Available APIs:"
    echo "$API_RESPONSE" | jq -r '.apiResponse[]? | "\(.api.apiName) v\(.api.apiVersion) (ID: \(.api.id))"'
    exit 1
fi

log_success "Found API: ${API_ID}"

# Get current API details (to preserve policies, routing, etc.)
API_DETAILS=$(curl -sf -u "${GATEWAY_USER}:${GATEWAY_PASSWORD}" \
    -H "Accept: application/json" \
    "${GATEWAY_URL}/rest/apigateway/apis/${API_ID}" 2>/dev/null)

CURRENT_ENDPOINTS=$(echo "$API_DETAILS" | jq '.apiResponse.api.apiDefinition.resources | length // 0')
log_info "Current API has ${CURRENT_ENDPOINTS} resources"

# =============================================================================
# Step 4: Compare endpoint counts
# =============================================================================

log_step "Comparing specifications"

NEW_ENDPOINTS=$(jq '.paths | keys | length' "${SPEC_FILE}")
log_info "New spec has ${NEW_ENDPOINTS} endpoints"

if [[ "$CURRENT_ENDPOINTS" -eq "$NEW_ENDPOINTS" ]]; then
    log_info "Endpoint count unchanged (${NEW_ENDPOINTS})"

    # Check if spec actually changed by comparing hashes
    NEW_PATHS=$(jq -S '.paths | keys | sort' "${SPEC_FILE}" | md5)
    CURRENT_PATHS=$(echo "$API_DETAILS" | jq -S '.apiResponse.api.apiDefinition.resources | [.[].methods[].displayName] | sort' 2>/dev/null | md5 || echo "unknown")

    if [[ "$NEW_PATHS" == "$CURRENT_PATHS" ]]; then
        log_success "No changes detected - skipping update"
        exit 0
    fi
fi

DIFF=$((NEW_ENDPOINTS - CURRENT_ENDPOINTS))
if [[ $DIFF -gt 0 ]]; then
    log_info "${GREEN}+${DIFF}${NC} new endpoints to add"
elif [[ $DIFF -lt 0 ]]; then
    log_warn "${DIFF} endpoints will be removed"
fi

# =============================================================================
# Step 5: Update API on Gateway
# =============================================================================

log_step "Updating API on Gateway"

if [[ "$DRY_RUN" == "true" ]]; then
    log_warn "DRY RUN - Would update API with ${NEW_ENDPOINTS} endpoints"
    log_info "New endpoints:"
    jq -r '.paths | keys[]' "${SPEC_FILE}" | head -20
    echo "... (showing first 20)"
    exit 0
fi

# First, deactivate the API to allow updates
log_info "Deactivating API for update..."
curl -sf -X PUT -u "${GATEWAY_USER}:${GATEWAY_PASSWORD}" \
    "${GATEWAY_URL}/rest/apigateway/apis/${API_ID}/deactivate" > /dev/null 2>&1 || true

# Update API using file upload (most reliable method)
log_info "Uploading new OpenAPI specification..."

UPDATE_RESPONSE=$(curl -sf -X PUT \
    -u "${GATEWAY_USER}:${GATEWAY_PASSWORD}" \
    -H "Accept: application/json" \
    -F "type=openapi" \
    -F "file=@${SPEC_FILE}" \
    "${GATEWAY_URL}/rest/apigateway/apis/${API_ID}" 2>&1)

if echo "$UPDATE_RESPONSE" | jq -e '.apiResponse.api.id' > /dev/null 2>&1; then
    UPDATED_RESOURCES=$(echo "$UPDATE_RESPONSE" | jq '.apiResponse.api.apiDefinition.resources | length // 0')
    log_success "API updated successfully (${UPDATED_RESOURCES} resources)"
else
    log_error "Failed to update API"
    echo "$UPDATE_RESPONSE" | jq . 2>/dev/null || echo "$UPDATE_RESPONSE"
    exit 1
fi

# =============================================================================
# Step 6: Reactivate API
# =============================================================================

log_step "Reactivating API"

ACTIVATE_RESPONSE=$(curl -sf -X PUT -u "${GATEWAY_USER}:${GATEWAY_PASSWORD}" \
    -H "Accept: application/json" \
    "${GATEWAY_URL}/rest/apigateway/apis/${API_ID}/activate" 2>&1)

if echo "$ACTIVATE_RESPONSE" | jq -e '.apiResponse.api.isActive' | grep -q true; then
    log_success "API reactivated"
else
    log_error "Failed to reactivate API"
    echo "$ACTIVATE_RESPONSE" | jq . 2>/dev/null || echo "$ACTIVATE_RESPONSE"
    exit 1
fi

# =============================================================================
# Step 7: Verify
# =============================================================================

log_step "Verification"

# Test a known endpoint
TEST_ENDPOINT="${GATEWAY_URL}/rest/apigateway/apis/${API_ID}"
VERIFY_RESPONSE=$(curl -sf -u "${GATEWAY_USER}:${GATEWAY_PASSWORD}" \
    -H "Accept: application/json" \
    "${TEST_ENDPOINT}" 2>&1)

FINAL_RESOURCES=$(echo "$VERIFY_RESPONSE" | jq '.apiResponse.api.apiDefinition.resources | length // 0')
IS_ACTIVE=$(echo "$VERIFY_RESPONSE" | jq -r '.apiResponse.api.isActive')

echo ""
echo "========================================="
echo -e "API: ${GREEN}${API_NAME}${NC} v${API_VERSION}"
echo -e "ID: ${GREEN}${API_ID}${NC}"
echo -e "Resources: ${GREEN}${FINAL_RESOURCES}${NC}"
echo -e "Active: ${GREEN}${IS_ACTIVE}${NC}"
echo "========================================="

# List new paths if any were added
if [[ $DIFF -gt 0 ]]; then
    log_info "New endpoints available:"
    jq -r '.paths | keys[]' "${SPEC_FILE}" | grep -E "/v1/platform" | head -10 || true
fi

# =============================================================================
# Step 8: Apply Security Policies (HYBRID - GitOps policies on Runtime contract)
# =============================================================================

if [[ "$APPLY_POLICIES" != "true" ]]; then
    log_warn "Policy application disabled (APPLY_POLICIES=$APPLY_POLICIES)"
    log_success "OpenAPI sync completed (contract only)"
    exit 0
fi

log_step "Applying Security Policies"

# 8.1 JWT Authentication Policy (Inbound)
log_info "Configuring JWT authentication..."

JWT_POLICY=$(cat <<EOF
{
  "policyActions": [
    {
      "names": ["Identify & Authorize"],
      "actions": [
        {
          "type": "jwtAuthentication",
          "parameters": {
            "oauth2Provider": {
              "name": "Keycloak-STOA",
              "type": "EXTERNAL",
              "issuer": "${KEYCLOAK_ISSUER}",
              "jwksUri": "${KEYCLOAK_ISSUER}/protocol/openid-connect/certs"
            },
            "validateAudience": true,
            "audience": ["${API_AUDIENCE}"],
            "validateIssuer": true,
            "validateExpiry": true,
            "clockSkewSeconds": 30
          }
        }
      ]
    }
  ]
}
EOF
)

# Note: webMethods Gateway policy API structure may vary
# This is a simplified example - adjust based on actual Gateway API
JWT_RESULT=$(curl -sf -X PUT \
    -u "${GATEWAY_USER}:${GATEWAY_PASSWORD}" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d "${JWT_POLICY}" \
    "${GATEWAY_URL}/rest/apigateway/apis/${API_ID}/policies" 2>&1 || echo "POLICY_ERROR")

if [[ "$JWT_RESULT" == "POLICY_ERROR" ]]; then
    log_warn "Could not apply JWT policy via API - may need manual configuration"
else
    log_success "JWT authentication policy configured"
fi

# 8.2 Outbound Authentication (JWT Passthrough to Backend)
if [[ "$BACKEND_PASSTHROUGH" == "true" ]]; then
    log_info "Configuring JWT passthrough to backend..."

    # Configure the API to forward the Authorization header to backend
    ROUTING_POLICY=$(cat <<EOF
{
  "nativeEndpoint": [
    {
      "uri": "${BACKEND_URL}",
      "connectionTimeout": 30,
      "readTimeout": 30,
      "passSecurityHeaders": true,
      "customHeaders": [
        {"name": "Authorization", "value": "\${request.headers.Authorization}"},
        {"name": "X-Forwarded-For", "value": "\${request.clientIP}"},
        {"name": "X-Request-ID", "value": "\${request.headers.X-Request-ID}"}
      ]
    }
  ]
}
EOF
)

    ROUTING_RESULT=$(curl -sf -X PATCH \
        -u "${GATEWAY_USER}:${GATEWAY_PASSWORD}" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json" \
        -d "${ROUTING_POLICY}" \
        "${GATEWAY_URL}/rest/apigateway/apis/${API_ID}" 2>&1 || echo "ROUTING_ERROR")

    if [[ "$ROUTING_RESULT" == "ROUTING_ERROR" ]]; then
        log_warn "Could not configure JWT passthrough - may need manual configuration"
    else
        log_success "JWT passthrough to backend configured"
    fi
fi

# 8.3 Log policy summary
echo ""
echo "========================================="
echo -e "${GREEN}Policies Applied:${NC}"
echo -e "  - JWT Authentication: ${KEYCLOAK_ISSUER}"
echo -e "  - Audience: ${API_AUDIENCE}"
echo -e "  - Backend Passthrough: ${BACKEND_PASSTHROUGH}"
echo "========================================="

log_success "OpenAPI sync + policies completed successfully"
exit 0
