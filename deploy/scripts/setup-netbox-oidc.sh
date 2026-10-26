#!/usr/bin/env bash
# =============================================================================
# STOA Platform — Keycloak Netbox OIDC Client Setup
# =============================================================================
# Creates the 'stoa-netbox' client in Keycloak for Netbox SSO login.
# Pattern identical to setup-observability-oidc.sh.
#
# Usage:
#   KEYCLOAK_URL=https://auth.gostoa.dev \
#   KEYCLOAK_ADMIN_PASSWORD=xxx \
#     ./deploy/scripts/setup-netbox-oidc.sh
#
# Prerequisites:
#   - Keycloak running and accessible
#   - curl and jq installed
#   - KEYCLOAK_URL, KEYCLOAK_ADMIN, KEYCLOAK_ADMIN_PASSWORD set (or defaults used)
#
# Client credentials are written to the configured on-site Vault path through stdin.
# WARNING: This script calls live Keycloak APIs. Run manually, not in CI.
# =============================================================================

set -euo pipefail
set +x
: "${NETBOX_SECRET_PATH:?Set NETBOX_SECRET_PATH to the on-site Vault path}"

KEYCLOAK_URL="${KEYCLOAK_URL:-https://auth.gostoa.dev}"
KEYCLOAK_ADMIN="${KEYCLOAK_ADMIN:-admin}"
KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:?KEYCLOAK_ADMIN_PASSWORD is required}"
REALM="${KEYCLOAK_REALM:-stoa}"
CLIENT_ID="stoa-netbox"

NETBOX_REDIRECT_URI="https://netbox.gostoa.dev/oauth/complete/oidc/"

echo "=== STOA Netbox OIDC Client Setup ==="
echo "Keycloak URL: ${KEYCLOAK_URL}"
echo "Realm: ${REALM}"
echo "Client ID: ${CLIENT_ID}"
echo ""

# Step 1: Obtain admin access token
echo "[1/4] Obtaining admin access token..."
# shellcheck source=scripts/lib/secret-input.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/../../scripts/lib/secret-input.sh"
TOKEN_RESPONSE=$(curl -s -X POST \
  "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "username=${KEYCLOAK_ADMIN}" \
  --data-urlencode "password=${KEYCLOAK_ADMIN_PASSWORD}" \
  -d "grant_type=password" \
  -d "client_id=admin-cli")

ACCESS_TOKEN=$(echo "${TOKEN_RESPONSE}" | jq -r '.access_token')
if [ "${ACCESS_TOKEN}" = "null" ] || [ -z "${ACCESS_TOKEN}" ]; then
  echo "ERROR: Failed to obtain access token. Response:"
  echo "Authentication failed; response details are withheld."
  exit 1
fi
echo "  Access token obtained."

# Step 2: Check if client already exists
echo "[2/4] Checking if client '${CLIENT_ID}' already exists..."
EXISTING_CLIENT=$(curl -s \
  "${KEYCLOAK_URL}/admin/realms/${REALM}/clients?clientId=${CLIENT_ID}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}")

CLIENT_COUNT=$(echo "${EXISTING_CLIENT}" | jq 'length')
if [ "${CLIENT_COUNT}" -gt 0 ]; then
  EXISTING_UUID=$(echo "${EXISTING_CLIENT}" | jq -r '.[0].id')
  echo "  Client already exists (UUID: ${EXISTING_UUID}). Updating..."
  HTTP_METHOD="PUT"
  CLIENT_URL="${KEYCLOAK_URL}/admin/realms/${REALM}/clients/${EXISTING_UUID}"
else
  echo "  Client does not exist. Creating..."
  HTTP_METHOD="POST"
  CLIENT_URL="${KEYCLOAK_URL}/admin/realms/${REALM}/clients"
fi

# Step 3: Create or update the client
echo "[3/4] ${HTTP_METHOD}ing client '${CLIENT_ID}'..."
CLIENT_PAYLOAD=$(cat <<ENDJSON
{
  "clientId": "${CLIENT_ID}",
  "name": "STOA Netbox",
  "description": "OIDC client for Netbox infrastructure cartography SSO",
  "enabled": true,
  "protocol": "openid-connect",
  "publicClient": false,
  "standardFlowEnabled": true,
  "directAccessGrantsEnabled": false,
  "serviceAccountsEnabled": false,
  "authorizationServicesEnabled": false,
  "redirectUris": [
    "${NETBOX_REDIRECT_URI}"
  ],
  "webOrigins": [
    "https://netbox.gostoa.dev"
  ],
  "protocolMappers": [
    {
      "name": "realm-roles",
      "protocol": "openid-connect",
      "protocolMapper": "oidc-usermodel-realm-role-mapper",
      "consentRequired": false,
      "config": {
        "multivalued": "true",
        "userinfo.token.claim": "true",
        "id.token.claim": "true",
        "access.token.claim": "true",
        "claim.name": "roles",
        "jsonType.label": "String"
      }
    },
    {
      "name": "groups",
      "protocol": "openid-connect",
      "protocolMapper": "oidc-group-membership-mapper",
      "consentRequired": false,
      "config": {
        "full.path": "false",
        "userinfo.token.claim": "true",
        "id.token.claim": "true",
        "access.token.claim": "true",
        "claim.name": "groups"
      }
    },
    {
      "name": "email",
      "protocol": "openid-connect",
      "protocolMapper": "oidc-usermodel-attribute-mapper",
      "consentRequired": false,
      "config": {
        "userinfo.token.claim": "true",
        "id.token.claim": "true",
        "access.token.claim": "true",
        "claim.name": "email",
        "user.attribute": "email",
        "jsonType.label": "String"
      }
    }
  ]
}
ENDJSON
)

RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -X "${HTTP_METHOD}" \
  "${CLIENT_URL}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "${CLIENT_PAYLOAD}")

if [ "${RESPONSE}" = "201" ] || [ "${RESPONSE}" = "204" ]; then
  echo "  Client ${HTTP_METHOD}d successfully (HTTP ${RESPONSE})."
else
  echo "ERROR: Failed to ${HTTP_METHOD} client (HTTP ${RESPONSE})."
  exit 1
fi

# Store the retrieved value directly in the on-site vault.
CLIENT_UUID=$(curl -sf "${KEYCLOAK_URL}/admin/realms/${REALM}/clients?clientId=${CLIENT_ID}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" | jq -er '.[0].id')
curl -sf "${KEYCLOAK_URL}/admin/realms/${REALM}/clients/${CLIENT_UUID}/client-secret" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" |
  python3 "$(dirname -- "${BASH_SOURCE[0]}")/../../scripts/security/store_oidc_secret.py" \
    --vault-path "$NETBOX_SECRET_PATH" --key NETBOX_OIDC_CLIENT_SECRET
echo "See docs/runbooks/first-admin-bootstrap.md for secret verification and rotation."
