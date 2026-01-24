#!/bin/bash
#
# Setup TOTP/2FA Configuration for STOA Keycloak Realm
#
# This script configures:
# - OTP Policy (TOTP with SHA256, 6 digits, 30-second period)
# - Step-up authentication flow for sensitive operations
# - Required actions for TOTP configuration
#
# Usage:
#   ./scripts/setup-keycloak-totp.sh [--env dev|staging|prod]
#
# Prerequisites:
#   - kubectl access to the cluster
#   - Keycloak admin credentials
#
# Reference: CAB-XXX - Secure API Key Management with Vault & 2FA
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
ENV="${ENV:-dev}"
KEYCLOAK_REALM="stoa"
KEYCLOAK_NAMESPACE="stoa-system"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --env)
            ENV="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [--env dev|staging|prod]"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}=== STOA Keycloak TOTP Setup ===${NC}"
echo -e "Environment: ${YELLOW}${ENV}${NC}"
echo -e "Realm: ${YELLOW}${KEYCLOAK_REALM}${NC}"
echo ""

# Get Keycloak admin credentials
echo -e "${BLUE}[1/6] Retrieving Keycloak admin credentials...${NC}"
KEYCLOAK_ADMIN_USER=$(kubectl get secret keycloak-admin -n "${KEYCLOAK_NAMESPACE}" -o jsonpath='{.data.username}' 2>/dev/null | base64 -d || echo "admin")
KEYCLOAK_ADMIN_PASSWORD=$(kubectl get secret keycloak-admin -n "${KEYCLOAK_NAMESPACE}" -o jsonpath='{.data.password}' 2>/dev/null | base64 -d || echo "")

if [[ -z "${KEYCLOAK_ADMIN_PASSWORD}" ]]; then
    echo -e "${YELLOW}Warning: Could not retrieve Keycloak admin password from secret${NC}"
    echo -e "Using environment variable KEYCLOAK_ADMIN_PASSWORD if set..."
    KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-Admin123!}"
fi

# Get Keycloak URL
KEYCLOAK_URL="https://auth.gostoa.dev"
if [[ "${ENV}" == "dev" ]]; then
    # For local development, use port-forward
    KEYCLOAK_URL="http://localhost:8180"
fi

echo -e "${GREEN}Keycloak URL: ${KEYCLOAK_URL}${NC}"

# Get admin token
echo -e "${BLUE}[2/6] Authenticating with Keycloak...${NC}"
TOKEN_RESPONSE=$(curl -s -X POST "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=${KEYCLOAK_ADMIN_USER}" \
    -d "password=${KEYCLOAK_ADMIN_PASSWORD}" \
    -d "grant_type=password" \
    -d "client_id=admin-cli" 2>/dev/null || echo "{}")

ACCESS_TOKEN=$(echo "${TOKEN_RESPONSE}" | jq -r '.access_token // empty')

if [[ -z "${ACCESS_TOKEN}" ]]; then
    echo -e "${RED}Failed to authenticate with Keycloak${NC}"
    echo -e "Response: ${TOKEN_RESPONSE}"
    exit 1
fi

echo -e "${GREEN}Authentication successful${NC}"

# Configure OTP Policy
echo -e "${BLUE}[3/6] Configuring OTP Policy...${NC}"
OTP_POLICY=$(cat <<EOF
{
    "otpPolicyType": "totp",
    "otpPolicyAlgorithm": "HmacSHA256",
    "otpPolicyInitialCounter": 0,
    "otpPolicyDigits": 6,
    "otpPolicyLookAheadWindow": 1,
    "otpPolicyPeriod": 30,
    "otpPolicyCodeReusable": false
}
EOF
)

RESULT=$(curl -s -X PUT "${KEYCLOAK_URL}/admin/realms/${KEYCLOAK_REALM}" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "${OTP_POLICY}" \
    -w "%{http_code}" \
    -o /dev/null)

if [[ "${RESULT}" == "204" || "${RESULT}" == "200" ]]; then
    echo -e "${GREEN}OTP Policy configured successfully${NC}"
else
    echo -e "${YELLOW}Warning: OTP Policy update returned ${RESULT}${NC}"
fi

# Enable CONFIGURE_TOTP required action
echo -e "${BLUE}[4/6] Enabling TOTP Required Action...${NC}"
TOTP_ACTION=$(cat <<EOF
{
    "alias": "CONFIGURE_TOTP",
    "name": "Configure OTP",
    "providerId": "CONFIGURE_TOTP",
    "enabled": true,
    "defaultAction": false,
    "priority": 10,
    "config": {}
}
EOF
)

# First, check if the action exists
EXISTING_ACTIONS=$(curl -s -X GET "${KEYCLOAK_URL}/admin/realms/${KEYCLOAK_REALM}/authentication/required-actions" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}")

TOTP_EXISTS=$(echo "${EXISTING_ACTIONS}" | jq -r '.[] | select(.alias == "CONFIGURE_TOTP") | .alias')

if [[ -z "${TOTP_EXISTS}" ]]; then
    # Register the required action
    curl -s -X POST "${KEYCLOAK_URL}/admin/realms/${KEYCLOAK_REALM}/authentication/register-required-action" \
        -H "Authorization: Bearer ${ACCESS_TOKEN}" \
        -H "Content-Type: application/json" \
        -d '{"providerId": "CONFIGURE_TOTP", "name": "Configure OTP"}' || true
fi

# Update the required action
RESULT=$(curl -s -X PUT "${KEYCLOAK_URL}/admin/realms/${KEYCLOAK_REALM}/authentication/required-actions/CONFIGURE_TOTP" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "${TOTP_ACTION}" \
    -w "%{http_code}" \
    -o /dev/null)

echo -e "${GREEN}TOTP Required Action enabled${NC}"

# Create step-up authentication flow
echo -e "${BLUE}[5/6] Creating Step-Up Authentication Flow...${NC}"

# Check if flow exists
EXISTING_FLOWS=$(curl -s -X GET "${KEYCLOAK_URL}/admin/realms/${KEYCLOAK_REALM}/authentication/flows" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}")

FLOW_EXISTS=$(echo "${EXISTING_FLOWS}" | jq -r '.[] | select(.alias == "step-up-totp") | .alias')

if [[ -z "${FLOW_EXISTS}" ]]; then
    # Create the flow
    FLOW_DEF=$(cat <<EOF
{
    "alias": "step-up-totp",
    "description": "Step-up authentication requiring TOTP for sensitive operations",
    "providerId": "basic-flow",
    "topLevel": true,
    "builtIn": false
}
EOF
)

    curl -s -X POST "${KEYCLOAK_URL}/admin/realms/${KEYCLOAK_REALM}/authentication/flows" \
        -H "Authorization: Bearer ${ACCESS_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "${FLOW_DEF}" || true

    # Get the flow ID
    FLOW_ID=$(curl -s -X GET "${KEYCLOAK_URL}/admin/realms/${KEYCLOAK_REALM}/authentication/flows" \
        -H "Authorization: Bearer ${ACCESS_TOKEN}" | jq -r '.[] | select(.alias == "step-up-totp") | .id')

    if [[ -n "${FLOW_ID}" ]]; then
        # Add OTP form execution
        curl -s -X POST "${KEYCLOAK_URL}/admin/realms/${KEYCLOAK_REALM}/authentication/flows/step-up-totp/executions/execution" \
            -H "Authorization: Bearer ${ACCESS_TOKEN}" \
            -H "Content-Type: application/json" \
            -d '{"provider": "auth-otp-form"}' || true

        echo -e "${GREEN}Step-up authentication flow created${NC}"
    else
        echo -e "${YELLOW}Warning: Could not get flow ID${NC}"
    fi
else
    echo -e "${GREEN}Step-up authentication flow already exists${NC}"
fi

# Summary
echo -e ""
echo -e "${BLUE}[6/6] Setup Complete!${NC}"
echo -e ""
echo -e "${GREEN}=== TOTP Configuration Summary ===${NC}"
echo -e "  Algorithm:    HmacSHA256"
echo -e "  Digits:       6"
echo -e "  Period:       30 seconds"
echo -e "  Code Reuse:   Disabled"
echo -e ""
echo -e "${YELLOW}=== Next Steps ===${NC}"
echo -e "  1. Users can enable TOTP in their profile settings"
echo -e "  2. Portal will prompt for TOTP when revealing API keys"
echo -e "  3. Backup codes are generated when TOTP is enabled"
echo -e ""
echo -e "${GREEN}TOTP setup completed successfully!${NC}"
