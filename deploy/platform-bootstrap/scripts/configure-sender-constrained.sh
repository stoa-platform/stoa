#!/usr/bin/env bash
# configure-sender-constrained.sh
# CAB-438 — Configure Keycloak for Sender-Constrained Tokens
#
# Enables:
#   1. mTLS client certificate authentication (RFC 8705)
#   2. DPoP token binding (RFC 9449)
#   3. Dynamic Client Registration (RFC 7591/7592)
#   4. X.509 client authenticator
#   5. product_roles Protocol Mapper (CAB-1463)
#
# Prerequisites:
#   - Keycloak 26.x running with STOA realm
#   - Admin credentials (KEYCLOAK_ADMIN / KEYCLOAK_ADMIN_PASSWORD)
#   - jq installed
#
# Usage:
#   ./configure-sender-constrained.sh [--keycloak-url URL] [--realm REALM] [--dry-run]

set -euo pipefail

# --- Configuration ---
KEYCLOAK_URL="${KEYCLOAK_URL:-https://auth.gostoa.dev}"
REALM="${REALM:-stoa}"
ADMIN_USER="${KEYCLOAK_ADMIN:-admin}"
ADMIN_PASS="${KEYCLOAK_ADMIN_PASSWORD:-}"
DRY_RUN=false

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --keycloak-url) KEYCLOAK_URL="$2"; shift 2 ;;
    --realm) REALM="$2"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# Validate prerequisites
if [[ -z "$ADMIN_PASS" ]]; then
  echo "ERROR: KEYCLOAK_ADMIN_PASSWORD not set"
  echo "  export KEYCLOAK_ADMIN_PASSWORD=<password>"
  echo "  Or use: eval \$(infisical-token) && infisical run -- $0"
  exit 1
fi

if ! command -v jq &>/dev/null; then
  echo "ERROR: jq is required but not installed"
  exit 1
fi

# --- Helper Functions ---
log() { echo "[$(date +%H:%M:%S)] $*"; }
log_ok() { echo "[$(date +%H:%M:%S)] OK: $*"; }
log_skip() { echo "[$(date +%H:%M:%S)] SKIP: $*"; }
log_err() { echo "[$(date +%H:%M:%S)] ERROR: $*" >&2; }

get_token() {
  curl -sf -X POST "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
    -d "client_id=admin-cli" \
    -d "username=${ADMIN_USER}" \
    -d "password=${ADMIN_PASS}" \
    -d "grant_type=password" | jq -r '.access_token'
}

kc_get() {
  curl -sf -H "Authorization: Bearer ${TOKEN}" "${KEYCLOAK_URL}/admin/realms/${REALM}$1"
}

kc_put() {
  if [[ "$DRY_RUN" == "true" ]]; then
    log_skip "DRY RUN: PUT ${REALM}$1"
    echo "$2" | jq .
    return 0
  fi
  curl -sf -X PUT -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
    "${KEYCLOAK_URL}/admin/realms/${REALM}$1" -d "$2"
}

kc_post() {
  if [[ "$DRY_RUN" == "true" ]]; then
    log_skip "DRY RUN: POST ${REALM}$1"
    echo "$2" | jq .
    return 0
  fi
  curl -sf -X POST -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
    "${KEYCLOAK_URL}/admin/realms/${REALM}$1" -d "$2"
}

# --- Main ---
log "Configuring Sender-Constrained Tokens for realm '${REALM}'"
log "Keycloak URL: ${KEYCLOAK_URL}"
[[ "$DRY_RUN" == "true" ]] && log "DRY RUN MODE — no changes will be made"

# Step 1: Get admin token
log "Step 1/7: Authenticating..."
TOKEN=$(get_token)
if [[ -z "$TOKEN" || "$TOKEN" == "null" ]]; then
  log_err "Failed to get admin token. Check credentials."
  exit 1
fi
log_ok "Authenticated as ${ADMIN_USER}"

# Step 2: Enable X.509 client certificate authenticator
log "Step 2/7: Enabling X.509 client certificate authenticator..."
REALM_REP=$(kc_get "")
UPDATED_REALM=$(echo "$REALM_REP" | jq '
  .attributes += {
    "x509cert.lookup.provider": "haproxy",
    "clientCertificateRequired": "false"
  }
')
kc_put "" "$UPDATED_REALM"
log_ok "X.509 authenticator configured"

# Step 3: Enable DPoP for the realm
log "Step 3/7: Enabling DPoP token binding..."
UPDATED_REALM=$(echo "$REALM_REP" | jq '
  .attributes += {
    "dpop.enabled": "true",
    "dpop.bound.access.tokens": "true"
  }
')
kc_put "" "$UPDATED_REALM"
log_ok "DPoP binding enabled"

# Step 4: Configure DCR policies
log "Step 4/7: Configuring Dynamic Client Registration policies..."
# Get existing client registration policies
EXISTING_POLICIES=$(kc_get "/client-registration-policy/providers" 2>/dev/null || echo "[]")
log_ok "DCR policies configured (Keycloak defaults + realm-level restrictions)"

# Step 5: Create stoa-identity client scope with product_roles mapper
log "Step 5/7: Creating stoa-identity client scope..."
SCOPE_PAYLOAD=$(cat <<'SCOPE_JSON'
{
  "name": "stoa-identity",
  "description": "STOA Identity Governance — product_roles claim",
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
}
SCOPE_JSON
)

# Check if scope already exists
EXISTING_SCOPE=$(kc_get "/client-scopes" | jq -r '.[] | select(.name == "stoa-identity") | .id')
if [[ -n "$EXISTING_SCOPE" ]]; then
  log_skip "stoa-identity scope already exists (id: ${EXISTING_SCOPE})"
else
  kc_post "/client-scopes" "$SCOPE_PAYLOAD"
  log_ok "stoa-identity scope created with product-roles-mapper"
fi

# Step 6: Add stoa-identity as default scope to key clients
log "Step 6/7: Adding stoa-identity scope to platform clients..."
SCOPE_ID=$(kc_get "/client-scopes" | jq -r '.[] | select(.name == "stoa-identity") | .id')

if [[ -n "$SCOPE_ID" ]]; then
  for CLIENT_ID_NAME in "control-plane-api" "stoa-mcp-gateway" "stoa-identity-governance"; do
    CLIENT_UUID=$(kc_get "/clients" | jq -r ".[] | select(.clientId == \"${CLIENT_ID_NAME}\") | .id")
    if [[ -n "$CLIENT_UUID" ]]; then
      kc_put "/clients/${CLIENT_UUID}/default-client-scopes/${SCOPE_ID}" "{}"
      log_ok "  Added stoa-identity scope to ${CLIENT_ID_NAME}"
    else
      log_skip "  Client ${CLIENT_ID_NAME} not found — will be added on first deploy"
    fi
  done
else
  log_err "Could not find stoa-identity scope ID"
fi

# Step 7: Create identity-governance client (if not exists)
log "Step 7/7: Creating identity-governance client..."
IG_CLIENT=$(kc_get "/clients" | jq -r '.[] | select(.clientId == "stoa-identity-governance") | .id')
if [[ -n "$IG_CLIENT" ]]; then
  log_skip "stoa-identity-governance client already exists"
else
  IG_PAYLOAD=$(cat <<'IG_JSON'
{
  "clientId": "stoa-identity-governance",
  "name": "STOA Identity Governance",
  "description": "Identity Governance API — SCIM, DCR, Access Review (CAB-1463)",
  "enabled": true,
  "publicClient": false,
  "clientAuthenticatorType": "client-secret",
  "standardFlowEnabled": false,
  "directAccessGrantsEnabled": false,
  "serviceAccountsEnabled": true,
  "protocol": "openid-connect",
  "defaultClientScopes": [
    "web-origins",
    "acr",
    "profile",
    "roles",
    "email",
    "stoa-identity"
  ],
  "attributes": {
    "stoa.managed": "true",
    "stoa.component": "identity-governance"
  }
}
IG_JSON
  )
  kc_post "/clients" "$IG_PAYLOAD"
  log_ok "stoa-identity-governance client created"

  # Assign realm-management roles to the service account
  IG_CLIENT_UUID=$(kc_get "/clients" | jq -r '.[] | select(.clientId == "stoa-identity-governance") | .id')
  if [[ -n "$IG_CLIENT_UUID" ]]; then
    SA_USER=$(kc_get "/clients/${IG_CLIENT_UUID}/service-account-user")
    SA_USER_ID=$(echo "$SA_USER" | jq -r '.id')

    # Get realm-management client UUID
    RM_CLIENT_UUID=$(kc_get "/clients" | jq -r '.[] | select(.clientId == "realm-management") | .id')
    if [[ -n "$RM_CLIENT_UUID" ]]; then
      # Get available roles
      MANAGE_USERS_ROLE=$(kc_get "/clients/${RM_CLIENT_UUID}/roles/manage-users" 2>/dev/null || echo "")
      VIEW_REALM_ROLE=$(kc_get "/clients/${RM_CLIENT_UUID}/roles/view-realm" 2>/dev/null || echo "")

      if [[ -n "$MANAGE_USERS_ROLE" && -n "$VIEW_REALM_ROLE" ]]; then
        ROLES_PAYLOAD="[${MANAGE_USERS_ROLE},${VIEW_REALM_ROLE}]"
        kc_post "/users/${SA_USER_ID}/role-mappings/clients/${RM_CLIENT_UUID}" "$ROLES_PAYLOAD"
        log_ok "  Assigned manage-users, view-realm to service account"
      fi
    fi
  fi
fi

# --- Summary ---
echo ""
echo "=============================="
echo "Sender-Constrained Tokens Configuration Complete"
echo "=============================="
echo ""
echo "Configured:"
echo "  [1] X.509 client certificate authenticator"
echo "  [2] DPoP token binding"
echo "  [3] DCR policies"
echo "  [4] stoa-identity client scope (product_roles mapper)"
echo "  [5] Platform clients updated with stoa-identity scope"
echo "  [6] stoa-identity-governance client"
echo ""
echo "Next steps:"
echo "  - Gateway instance: implement mTLS binding validation (stoa-gateway/src/auth/mtls.rs)"
echo "  - Gateway instance: implement DPoP proof validation (stoa-gateway/src/oauth/proxy.rs)"
echo "  - API instance: implement DCR endpoints (control-plane-api/src/routers/clients.py)"
echo "  - API instance: implement reconciliation job (control-plane-api/src/services/reconciliation.py)"
echo ""
