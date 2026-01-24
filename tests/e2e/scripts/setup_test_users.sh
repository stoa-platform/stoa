#!/bin/bash
#
# Setup E2E Test Users in Keycloak and AWS Secrets Manager
# CAB-238: E2E Testing Infrastructure
#
# Prerequisites:
#   - AWS CLI configured with appropriate permissions
#   - Access to Keycloak admin API (via kubectl port-forward or direct access)
#
# Usage:
#   ./setup_test_users.sh [--keycloak-url URL] [--realm REALM] [--aws-region REGION]
#

set -eo pipefail

# Default configuration
KEYCLOAK_URL="${KEYCLOAK_URL:-https://auth.gostoa.dev}"
KEYCLOAK_REALM="${KEYCLOAK_REALM:-stoa}"
AWS_REGION="${AWS_REGION:-eu-west-1}"
SECRET_NAME="stoa/e2e-test-credentials"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --keycloak-url) KEYCLOAK_URL="$2"; shift 2 ;;
        --realm) KEYCLOAK_REALM="$2"; shift 2 ;;
        --aws-region) AWS_REGION="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Generate secure random passwords
generate_password() {
    openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 20
}

log_info "Setting up E2E test users for STOA Platform"
log_info "Keycloak URL: $KEYCLOAK_URL"
log_info "Realm: $KEYCLOAK_REALM"
log_info "AWS Region: $AWS_REGION"

# Generate passwords for test users
E2E_ADMIN_PASSWORD=$(generate_password)
E2E_TENANT_ADMIN_PASSWORD=$(generate_password)
E2E_DEVOPS_PASSWORD=$(generate_password)
E2E_VIEWER_PASSWORD=$(generate_password)

# Step 1: Get Keycloak admin token
log_info "Authenticating with Keycloak..."

# Check if we have admin credentials
if [[ -z "${KEYCLOAK_ADMIN_USER:-}" ]] || [[ -z "${KEYCLOAK_ADMIN_PASSWORD:-}" ]]; then
    log_warn "KEYCLOAK_ADMIN_USER and KEYCLOAK_ADMIN_PASSWORD not set"
    log_info "Attempting to get credentials from AWS Secrets Manager..."

    ADMIN_CREDS=$(aws secretsmanager get-secret-value \
        --secret-id "stoa/keycloak-admin" \
        --region "$AWS_REGION" \
        --query 'SecretString' \
        --output text 2>/dev/null || echo "")

    if [[ -n "$ADMIN_CREDS" ]]; then
        KEYCLOAK_ADMIN_USER=$(echo "$ADMIN_CREDS" | jq -r '.username // "admin"')
        KEYCLOAK_ADMIN_PASSWORD=$(echo "$ADMIN_CREDS" | jq -r '.password')
    else
        log_error "Could not get Keycloak admin credentials"
        log_info "Please set KEYCLOAK_ADMIN_USER and KEYCLOAK_ADMIN_PASSWORD environment variables"
        exit 1
    fi
fi

# Get admin token
ADMIN_TOKEN=$(curl -s -X POST \
    "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=${KEYCLOAK_ADMIN_USER}" \
    -d "password=${KEYCLOAK_ADMIN_PASSWORD}" \
    -d "grant_type=password" \
    -d "client_id=admin-cli" | jq -r '.access_token')

if [[ "$ADMIN_TOKEN" == "null" ]] || [[ -z "$ADMIN_TOKEN" ]]; then
    log_error "Failed to authenticate with Keycloak admin"
    exit 1
fi

log_info "Successfully authenticated with Keycloak"

# Function to create or update a user
create_user() {
    local username="$1"
    local password="$2"
    local role="$3"
    local email="$4"

    log_info "Creating user: $username (role: $role)"

    # Check if user exists
    EXISTING_USER=$(curl -s -X GET \
        "${KEYCLOAK_URL}/admin/realms/${KEYCLOAK_REALM}/users?username=${username}" \
        -H "Authorization: Bearer ${ADMIN_TOKEN}" \
        -H "Content-Type: application/json")

    USER_COUNT=$(echo "$EXISTING_USER" | jq 'length')

    if [[ "$USER_COUNT" -gt 0 ]]; then
        log_warn "User $username already exists, updating password..."
        USER_ID=$(echo "$EXISTING_USER" | jq -r '.[0].id')

        # Reset password
        curl -s -X PUT \
            "${KEYCLOAK_URL}/admin/realms/${KEYCLOAK_REALM}/users/${USER_ID}/reset-password" \
            -H "Authorization: Bearer ${ADMIN_TOKEN}" \
            -H "Content-Type: application/json" \
            -d "{\"type\":\"password\",\"value\":\"${password}\",\"temporary\":false}"
    else
        # Create new user
        USER_PAYLOAD=$(cat <<EOF
{
    "username": "${username}",
    "email": "${email}",
    "emailVerified": true,
    "enabled": true,
    "firstName": "E2E",
    "lastName": "Test ${role}",
    "credentials": [{
        "type": "password",
        "value": "${password}",
        "temporary": false
    }]
}
EOF
)

        RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
            "${KEYCLOAK_URL}/admin/realms/${KEYCLOAK_REALM}/users" \
            -H "Authorization: Bearer ${ADMIN_TOKEN}" \
            -H "Content-Type: application/json" \
            -d "$USER_PAYLOAD")

        HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

        if [[ "$HTTP_CODE" == "201" ]]; then
            log_info "User $username created successfully"

            # Get user ID and assign role
            USER_ID=$(curl -s -X GET \
                "${KEYCLOAK_URL}/admin/realms/${KEYCLOAK_REALM}/users?username=${username}" \
                -H "Authorization: Bearer ${ADMIN_TOKEN}" | jq -r '.[0].id')

            # Get role ID
            ROLE_DATA=$(curl -s -X GET \
                "${KEYCLOAK_URL}/admin/realms/${KEYCLOAK_REALM}/roles/${role}" \
                -H "Authorization: Bearer ${ADMIN_TOKEN}")

            ROLE_ID=$(echo "$ROLE_DATA" | jq -r '.id')

            if [[ "$ROLE_ID" != "null" ]] && [[ -n "$ROLE_ID" ]]; then
                # Assign role to user
                curl -s -X POST \
                    "${KEYCLOAK_URL}/admin/realms/${KEYCLOAK_REALM}/users/${USER_ID}/role-mappings/realm" \
                    -H "Authorization: Bearer ${ADMIN_TOKEN}" \
                    -H "Content-Type: application/json" \
                    -d "[${ROLE_DATA}]"

                log_info "Assigned role $role to user $username"
            else
                log_warn "Role $role not found in realm, skipping role assignment"
            fi
        else
            log_error "Failed to create user $username (HTTP $HTTP_CODE)"
        fi
    fi
}

# Step 2: Create test users in Keycloak
log_info "Creating test users in Keycloak..."

create_user "e2e-admin" "$E2E_ADMIN_PASSWORD" "cpi-admin" "e2e-admin@test.gostoa.dev"
create_user "e2e-tenant-admin" "$E2E_TENANT_ADMIN_PASSWORD" "tenant-admin" "e2e-tenant-admin@test.gostoa.dev"
create_user "e2e-devops" "$E2E_DEVOPS_PASSWORD" "devops" "e2e-devops@test.gostoa.dev"
create_user "e2e-viewer" "$E2E_VIEWER_PASSWORD" "viewer" "e2e-viewer@test.gostoa.dev"

# Step 3: Store credentials in AWS Secrets Manager
log_info "Storing credentials in AWS Secrets Manager..."

SECRET_VALUE=$(cat <<EOF
{
    "admin": {
        "username": "e2e-admin",
        "password": "${E2E_ADMIN_PASSWORD}",
        "email": "e2e-admin@test.gostoa.dev"
    },
    "tenant_admin": {
        "username": "e2e-tenant-admin",
        "password": "${E2E_TENANT_ADMIN_PASSWORD}",
        "email": "e2e-tenant-admin@test.gostoa.dev"
    },
    "devops": {
        "username": "e2e-devops",
        "password": "${E2E_DEVOPS_PASSWORD}",
        "email": "e2e-devops@test.gostoa.dev"
    },
    "viewer": {
        "username": "e2e-viewer",
        "password": "${E2E_VIEWER_PASSWORD}",
        "email": "e2e-viewer@test.gostoa.dev"
    }
}
EOF
)

# Check if secret exists
if aws secretsmanager describe-secret --secret-id "$SECRET_NAME" --region "$AWS_REGION" >/dev/null 2>&1; then
    log_info "Updating existing secret: $SECRET_NAME"
    aws secretsmanager update-secret \
        --secret-id "$SECRET_NAME" \
        --secret-string "$SECRET_VALUE" \
        --region "$AWS_REGION"
else
    log_info "Creating new secret: $SECRET_NAME"
    aws secretsmanager create-secret \
        --name "$SECRET_NAME" \
        --description "E2E test user credentials for STOA Platform (CAB-238)" \
        --secret-string "$SECRET_VALUE" \
        --region "$AWS_REGION" \
        --tags Key=Project,Value=STOA Key=Environment,Value=test Key=Purpose,Value=e2e-testing
fi

log_info "Credentials stored in AWS Secrets Manager: $SECRET_NAME"

# Summary
echo ""
log_info "=========================================="
log_info "E2E Test Users Setup Complete"
log_info "=========================================="
echo ""
echo "Users created in Keycloak realm '$KEYCLOAK_REALM':"
echo "  - e2e-admin (cpi-admin role)"
echo "  - e2e-tenant-admin (tenant-admin role)"
echo "  - e2e-devops (devops role)"
echo "  - e2e-viewer (viewer role)"
echo ""
echo "Credentials stored in AWS Secrets Manager:"
echo "  Secret: $SECRET_NAME"
echo "  Region: $AWS_REGION"
echo ""
echo "To run E2E tests:"
echo "  cd tests/e2e && pytest -m smoke"
echo ""
