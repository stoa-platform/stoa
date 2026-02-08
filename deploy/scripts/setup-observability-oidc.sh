#!/usr/bin/env bash
# =============================================================================
# STOA Platform — Keycloak Observability OIDC Client Setup (CAB-1103 Phase 6B)
# =============================================================================
# Creates the 'stoa-observability' client in Keycloak for:
#   - Grafana OIDC login
#   - oauth2-proxy (Prometheus access)
#
# Usage:
#   ./deploy/scripts/setup-observability-oidc.sh
#
# Prerequisites:
#   - Keycloak running and accessible
#   - curl and jq installed
#   - KEYCLOAK_URL, KEYCLOAK_ADMIN, KEYCLOAK_ADMIN_PASSWORD set (or defaults used)
#
# WARNING: This script calls live Keycloak APIs. Run manually, not in CI.
# =============================================================================

set -euo pipefail

KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost/auth}"
KEYCLOAK_ADMIN="${KEYCLOAK_ADMIN:-admin}"
KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-admin}"
REALM="${KEYCLOAK_REALM:-stoa}"
CLIENT_ID="stoa-observability"

GRAFANA_REDIRECT_URI="${GRAFANA_REDIRECT_URI:-http://localhost/grafana/login/generic_oauth}"
PROMETHEUS_REDIRECT_URI="${PROMETHEUS_REDIRECT_URI:-http://localhost/prometheus/oauth2/callback}"

echo "=== STOA Observability OIDC Client Setup ==="
echo "Keycloak URL: ${KEYCLOAK_URL}"
echo "Realm: ${REALM}"
echo "Client ID: ${CLIENT_ID}"
echo ""

# Step 1: Obtain admin access token
echo "[1/4] Obtaining admin access token..."
TOKEN_RESPONSE=$(curl -s -X POST \
  "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=${KEYCLOAK_ADMIN}" \
  -d "password=${KEYCLOAK_ADMIN_PASSWORD}" \
  -d "grant_type=password" \
  -d "client_id=admin-cli")

ACCESS_TOKEN=$(echo "${TOKEN_RESPONSE}" | jq -r '.access_token')
if [ "${ACCESS_TOKEN}" = "null" ] || [ -z "${ACCESS_TOKEN}" ]; then
  echo "ERROR: Failed to obtain access token. Response:"
  echo "${TOKEN_RESPONSE}" | jq .
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
  "name": "STOA Observability",
  "description": "OIDC client for Grafana and Prometheus oauth2-proxy (CAB-1103)",
  "enabled": true,
  "protocol": "openid-connect",
  "publicClient": false,
  "standardFlowEnabled": true,
  "directAccessGrantsEnabled": false,
  "serviceAccountsEnabled": false,
  "authorizationServicesEnabled": false,
  "redirectUris": [
    "${GRAFANA_REDIRECT_URI}",
    "${PROMETHEUS_REDIRECT_URI}"
  ],
  "webOrigins": [
    "http://localhost",
    "https://grafana.gostoa.dev",
    "https://prometheus.gostoa.dev"
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

# Step 4: Retrieve and display the client secret
echo "[4/4] Retrieving client secret..."

CLIENT_INFO=$(curl -s \
  "${KEYCLOAK_URL}/admin/realms/${REALM}/clients?clientId=${CLIENT_ID}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}")
CLIENT_UUID=$(echo "${CLIENT_INFO}" | jq -r '.[0].id')

SECRET_RESPONSE=$(curl -s \
  "${KEYCLOAK_URL}/admin/realms/${REALM}/clients/${CLIENT_UUID}/client-secret" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}")
CLIENT_SECRET=$(echo "${SECRET_RESPONSE}" | jq -r '.value')

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Add the following to your .env file:"
echo ""
echo "  GRAFANA_OIDC_CLIENT_SECRET=${CLIENT_SECRET}"
echo "  OAUTH2_PROXY_CLIENT_SECRET=${CLIENT_SECRET}"
echo "  OAUTH2_PROXY_COOKIE_SECRET=$(openssl rand -base64 32 | tr -d '\n')"
echo ""
echo "Then restart the stack:"
echo "  docker compose down && docker compose up -d"
echo ""
