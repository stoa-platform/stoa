#!/bin/bash
# Setup Keycloak Client for Observability Stack
# This script creates the OIDC client in Keycloak

set -e

: "${KEYCLOAK_ADMIN_PASSWORD:?An explicit admin password is required}"

KEYCLOAK_URL="${KEYCLOAK_URL:-https://auth.gostoa.dev}"
KEYCLOAK_REALM="${KEYCLOAK_REALM:-stoa}"
KEYCLOAK_ADMIN="${KEYCLOAK_ADMIN:-admin}"
KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:?Set KEYCLOAK_ADMIN_PASSWORD}"

BASE_DOMAIN="${BASE_DOMAIN:-gostoa.dev}"

echo "=== Setting up Keycloak Client for Observability ==="
echo "Keycloak URL: $KEYCLOAK_URL"
echo "Realm: $KEYCLOAK_REALM"

# Get admin token
echo "Getting admin token..."
TOKEN=$(curl -s -X POST "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=${KEYCLOAK_ADMIN}" \
  -d "password=${KEYCLOAK_ADMIN_PASSWORD}" \
  -d "grant_type=password" \
  -d "client_id=admin-cli" | jq -r '.access_token')

if [ "$TOKEN" == "null" ] || [ -z "$TOKEN" ]; then
  echo "ERROR: Failed to get admin token"
  exit 1
fi
echo "Got admin token"

# Check if client already exists
echo "Checking if client 'observability' exists..."
EXISTING=$(curl -s -X GET "${KEYCLOAK_URL}/admin/realms/${KEYCLOAK_REALM}/clients?clientId=observability" \
  -H "Authorization: Bearer $TOKEN" | jq -r '.[0].id // empty')

if [ -n "$EXISTING" ]; then
  echo "Client 'observability' already exists (ID: $EXISTING)"
  # Client lookup above already establishes the client identity.
  echo "Sensitive values are withheld; use the approved secret store."
else
  # Create the client
  echo "Creating client 'observability'..."

  CLIENT_CONFIG=$(cat <<EOF
{
  "clientId": "observability",
  "name": "Observability Stack",
  "description": "OIDC client for Grafana, Prometheus, and Loki",
  "enabled": true,
  "protocol": "openid-connect",
  "publicClient": false,
  "standardFlowEnabled": true,
  "implicitFlowEnabled": false,
  "directAccessGrantsEnabled": false,
  "serviceAccountsEnabled": false,
  "authorizationServicesEnabled": false,
  "redirectUris": [
    "https://grafana.${BASE_DOMAIN}/login/generic_oauth",
    "https://prometheus.${BASE_DOMAIN}/oauth2/callback",
    "https://loki.${BASE_DOMAIN}/oauth2/callback"
  ],
  "webOrigins": ["+"],
  "attributes": {
    "pkce.code.challenge.method": "S256",
    "post.logout.redirect.uris": "https://grafana.${BASE_DOMAIN}/login/generic_oauth##https://prometheus.${BASE_DOMAIN}/##https://loki.${BASE_DOMAIN}/"
  },
  "defaultClientScopes": ["openid", "profile", "email", "roles"],
  "optionalClientScopes": []
}
EOF
)

  RESPONSE=$(curl -s -X POST "${KEYCLOAK_URL}/admin/realms/${KEYCLOAK_REALM}/clients" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "$CLIENT_CONFIG" \
    -w "\n%{http_code}")

  HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)

  if [ "$HTTP_CODE" == "201" ]; then
    echo "Client created successfully"

    # Get the client ID
    CLIENT_ID=$(curl -s -X GET "${KEYCLOAK_URL}/admin/realms/${KEYCLOAK_REALM}/clients?clientId=observability" \
      -H "Authorization: Bearer $TOKEN" | jq -r '.[0].id')

    # Client lookup above already establishes the client identity.

    echo "Client ID (internal): $CLIENT_ID"
    echo "Sensitive values are withheld; use the approved secret store."
  else
    echo "ERROR: Failed to create client (HTTP $HTTP_CODE)"
    echo "$RESPONSE"
    exit 1
  fi
fi

echo ""
echo "=== Configuration Values ==="
echo ""
echo "Client ID: observability"
echo "Sensitive values are withheld; use the approved secret store."
echo "Sensitive values are withheld; use the approved secret store."
echo ""
echo "=== Next Steps ==="
echo ""
echo "1. Update Grafana with OIDC config (helm upgrade)"
echo "2. Create oauth2-proxy secrets:"
echo ""
echo "kubectl create secret generic oauth2-proxy-secret -n stoa-monitoring \\"
echo "Sensitive values are withheld; use the approved secret store."
echo "Sensitive values are withheld; use the approved secret store."
echo "  --dry-run=client -o yaml | kubectl apply -f -"
echo ""
echo "kubectl create secret generic oauth2-proxy-secret -n stoa-system \\"
echo "Sensitive values are withheld; use the approved secret store."
echo "Sensitive values are withheld; use the approved secret store."
echo "  --dry-run=client -o yaml | kubectl apply -f -"
