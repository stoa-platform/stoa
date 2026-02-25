#!/usr/bin/env bash
# configure-product-roles-mapper.sh
# CAB-1463 — Configure Keycloak Protocol Mapper for product_roles JWT claim
#
# This script:
#   1. Creates the stoa-identity client scope with the product_roles mapper
#   2. Adds it as a default scope to all platform clients
#   3. Validates the mapper is producing the expected JWT claim
#
# The product_roles claim is a JSON array derived from SCIM group membership
# via the roles-matrix.yaml configuration.
#
# Prerequisites:
#   - Keycloak 26.x with STOA realm
#   - Admin credentials
#   - jq installed
#
# Usage:
#   ./configure-product-roles-mapper.sh [--keycloak-url URL] [--realm REALM] [--validate]

set -euo pipefail

KEYCLOAK_URL="${KEYCLOAK_URL:-https://auth.gostoa.dev}"
REALM="${REALM:-stoa}"
ADMIN_USER="${KEYCLOAK_ADMIN:-admin}"
ADMIN_PASS="${KEYCLOAK_ADMIN_PASSWORD:-}"
VALIDATE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keycloak-url) KEYCLOAK_URL="$2"; shift 2 ;;
    --realm) REALM="$2"; shift 2 ;;
    --validate) VALIDATE=true; shift ;;
    *) echo "Unknown: $1"; exit 1 ;;
  esac
done

if [[ -z "$ADMIN_PASS" ]]; then
  echo "ERROR: KEYCLOAK_ADMIN_PASSWORD not set"
  exit 1
fi

log() { echo "[$(date +%H:%M:%S)] $*"; }
log_ok() { echo "[$(date +%H:%M:%S)] OK: $*"; }

get_token() {
  curl -sf -X POST "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
    -d "client_id=admin-cli" \
    -d "username=${ADMIN_USER}" \
    -d "password=${ADMIN_PASS}" \
    -d "grant_type=password" | jq -r '.access_token'
}

log "Configuring product_roles Protocol Mapper"

TOKEN=$(get_token)
if [[ -z "$TOKEN" || "$TOKEN" == "null" ]]; then
  echo "ERROR: Failed to authenticate"; exit 1
fi
log_ok "Authenticated"

# Step 1: Create stoa-identity scope if missing
log "Step 1/3: Checking stoa-identity client scope..."
SCOPE_ID=$(curl -sf -H "Authorization: Bearer ${TOKEN}" \
  "${KEYCLOAK_URL}/admin/realms/${REALM}/client-scopes" | \
  jq -r '.[] | select(.name == "stoa-identity") | .id')

if [[ -z "$SCOPE_ID" ]]; then
  log "Creating stoa-identity scope..."
  RESPONSE=$(curl -sf -X POST -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    "${KEYCLOAK_URL}/admin/realms/${REALM}/client-scopes" \
    -d '{
      "name": "stoa-identity",
      "description": "STOA Identity — product_roles claim",
      "protocol": "openid-connect",
      "attributes": {
        "include.in.token.scope": "true",
        "display.on.consent.screen": "false"
      },
      "protocolMappers": [
        {
          "name": "product-roles-mapper",
          "protocol": "openid-connect",
          "protocolMapper": "oidc-usermodel-attribute-mapper",
          "config": {
            "user.attribute": "product_roles",
            "claim.name": "product_roles",
            "jsonType.label": "JSON",
            "multivalued": "true",
            "id.token.claim": "true",
            "access.token.claim": "true",
            "userinfo.token.claim": "true"
          }
        }
      ]
    }')
  SCOPE_ID=$(curl -sf -H "Authorization: Bearer ${TOKEN}" \
    "${KEYCLOAK_URL}/admin/realms/${REALM}/client-scopes" | \
    jq -r '.[] | select(.name == "stoa-identity") | .id')
  log_ok "Created stoa-identity scope (id: ${SCOPE_ID})"
else
  log_ok "stoa-identity scope exists (id: ${SCOPE_ID})"
fi

# Step 2: Add scope to platform clients
log "Step 2/3: Assigning stoa-identity scope to platform clients..."
CLIENTS_JSON=$(curl -sf -H "Authorization: Bearer ${TOKEN}" \
  "${KEYCLOAK_URL}/admin/realms/${REALM}/clients")

PLATFORM_CLIENTS=("control-plane-api" "control-plane-ui" "stoa-portal" "stoa-mcp-gateway" "stoa-identity-governance")

for CLIENT_NAME in "${PLATFORM_CLIENTS[@]}"; do
  CLIENT_UUID=$(echo "$CLIENTS_JSON" | jq -r ".[] | select(.clientId == \"${CLIENT_NAME}\") | .id")
  if [[ -n "$CLIENT_UUID" ]]; then
    # Check if scope already assigned
    EXISTING=$(curl -sf -H "Authorization: Bearer ${TOKEN}" \
      "${KEYCLOAK_URL}/admin/realms/${REALM}/clients/${CLIENT_UUID}/default-client-scopes" | \
      jq -r ".[] | select(.id == \"${SCOPE_ID}\") | .id")
    if [[ -z "$EXISTING" ]]; then
      curl -sf -X PUT -H "Authorization: Bearer ${TOKEN}" \
        "${KEYCLOAK_URL}/admin/realms/${REALM}/clients/${CLIENT_UUID}/default-client-scopes/${SCOPE_ID}"
      log_ok "  Added stoa-identity to ${CLIENT_NAME}"
    else
      log_ok "  ${CLIENT_NAME} already has stoa-identity scope"
    fi
  else
    log "  SKIP: ${CLIENT_NAME} not found"
  fi
done

# Step 3: Validate (optional)
if [[ "$VALIDATE" == "true" ]]; then
  log "Step 3/3: Validating product_roles claim..."

  # Get a token for the control-plane-api service account
  API_CLIENT_UUID=$(echo "$CLIENTS_JSON" | jq -r '.[] | select(.clientId == "control-plane-api") | .id')
  API_SECRET=$(curl -sf -H "Authorization: Bearer ${TOKEN}" \
    "${KEYCLOAK_URL}/admin/realms/${REALM}/clients/${API_CLIENT_UUID}/client-secret" | jq -r '.value')

  if [[ -n "$API_SECRET" && "$API_SECRET" != "null" ]]; then
    SA_TOKEN=$(curl -sf -X POST "${KEYCLOAK_URL}/realms/${REALM}/protocol/openid-connect/token" \
      -d "client_id=control-plane-api" \
      -d "client_secret=${API_SECRET}" \
      -d "grant_type=client_credentials" | jq -r '.access_token')

    if [[ -n "$SA_TOKEN" && "$SA_TOKEN" != "null" ]]; then
      # Decode JWT payload (base64url)
      PAYLOAD=$(echo "$SA_TOKEN" | cut -d. -f2 | base64 -d 2>/dev/null || \
        echo "$SA_TOKEN" | cut -d. -f2 | python3 -c "import sys,base64; print(base64.urlsafe_b64decode(sys.stdin.read().strip() + '==').decode())")
      HAS_CLAIM=$(echo "$PAYLOAD" | jq -r 'has("product_roles")')
      if [[ "$HAS_CLAIM" == "true" ]]; then
        log_ok "product_roles claim present in access token"
        echo "$PAYLOAD" | jq '{product_roles, roles, tenant_id}'
      else
        log "WARN: product_roles claim not yet in token (user attribute not set — expected for service accounts without SCIM provisioning)"
      fi
    fi
  else
    log "SKIP: Cannot validate — control-plane-api secret not accessible"
  fi
else
  log "Step 3/3: Skipped validation (use --validate to enable)"
fi

echo ""
log_ok "product_roles Protocol Mapper configuration complete"
echo ""
echo "JWT claim 'product_roles' will contain:"
echo '  ["cpi-admin", "tenant-admin", "devops", "viewer", ...]'
echo ""
echo "Values are derived from SCIM group membership via:"
echo "  deploy/platform-bootstrap/rbac/roles-matrix.yaml"
echo ""
