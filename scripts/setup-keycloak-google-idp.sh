#!/bin/bash
# Configure the realm using credentials supplied through the environment.
# Usage: script [--dry-run]. Positional credentials are refused.
# Keep credentials in the on-site secret store and disable shell tracing.
set -euo pipefail
set +x

DRY_RUN=false
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=true
  shift
  echo "[DRY RUN] No changes will be made."
fi

if [ $# -ne 0 ]; then
  echo "Positional credentials are unsupported; use environment inputs." >&2
  exit 2
fi
KC_ADMIN_PWD="${KEYCLOAK_ADMIN_PASSWORD:?An explicit admin password is required}"
: "${GOOGLE_CLIENT_ID:?GOOGLE_CLIENT_ID is required}"
: "${GOOGLE_CLIENT_SECRET:?GOOGLE_CLIENT_SECRET is required}"
REALM="stoa"

# Find Keycloak pod
KC_POD=$(kubectl get pods -n stoa-system -l app=keycloak -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
if [ -z "$KC_POD" ]; then
  KC_POD=$(kubectl get pods -n stoa-system -l app.kubernetes.io/name=keycloak -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
fi

if [ -z "$KC_POD" ]; then
  echo "ERROR: Keycloak pod not found in stoa-system namespace"
  exit 1
fi

KCADM="kubectl exec -n stoa-system $KC_POD -- /opt/keycloak/bin/kcadm.sh"

echo "=== STOA Google Social Login Setup (CAB-1873) ==="
echo "Keycloak pod: $KC_POD"
echo "Realm: $REALM"
echo "Google Client ID: ${GOOGLE_CLIENT_ID:0:20}..."
echo ""

# Step 1: Login
echo "[1/5] Logging into Keycloak..."
if [ "$DRY_RUN" = false ]; then
  printf '%s\n' "$KC_ADMIN_PWD" | kubectl exec -i -n stoa-system "$KC_POD" -- /opt/keycloak/bin/kcadm.sh config credentials \
    --server http://localhost:8080 \
    --realm master \
    --user admin
fi

# Step 2: Configure the provider without enabling broker account creation.
echo "[2/5] Configuring Google Identity Provider (disabled)..."
if [ "$DRY_RUN" = false ]; then
  EXISTING=$($KCADM get "identity-provider/instances/google" -r "$REALM" 2>/dev/null || echo "NOT_FOUND")
  OPERATION=update
  RESOURCE=identity-provider/instances/google
  if [ "$EXISTING" = "NOT_FOUND" ]; then
    OPERATION=create
    RESOURCE=identity-provider/instances
  fi
  export GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET
  if ! python3 -c '
import json, os
print(json.dumps({
    "alias": "google", "displayName": "Google", "providerId": "google",
    "enabled": False, "trustEmail": True, "storeToken": False,
    "firstBrokerLoginFlowAlias": "first broker login",
    "config": {"clientId": os.environ["GOOGLE_CLIENT_ID"],
               "clientSecret": os.environ["GOOGLE_CLIENT_SECRET"],
               "defaultScope": "openid profile email", "syncMode": "IMPORT"},
}))' | kubectl exec -i -n stoa-system "$KC_POD" -- /opt/keycloak/bin/kcadm.sh \
    "$OPERATION" "$RESOURCE" -r "$REALM" -f - >/dev/null 2>&1; then
    echo "Provider configuration failed; response details are withheld." >&2
    exit 1
  fi
fi

# Step 3: Create IDP mappers (default role: viewer)
echo "[3/5] Creating identity provider mappers..."
if [ "$DRY_RUN" = false ]; then
  # Hardcoded role mapper — assigns viewer role to all Google sign-ins
  $KCADM create "identity-provider/instances/google/mappers" -r "$REALM" \
    -s name=google-viewer-role \
    -s identityProviderAlias=google \
    -s identityProviderMapper=hardcoded-role-idp-mapper \
    -s "config.role=viewer" \
    -s "config.syncMode=INHERIT" 2>/dev/null || \
    echo "  (viewer role mapper may already exist — skipping)"

  # Email attribute mapper
  $KCADM create "identity-provider/instances/google/mappers" -r "$REALM" \
    -s name=google-email-mapper \
    -s identityProviderAlias=google \
    -s identityProviderMapper=google-user-attribute-mapper \
    -s "config.jsonField=email" \
    -s "config.userAttribute=email" \
    -s "config.syncMode=INHERIT" 2>/dev/null || \
    echo "  (email mapper may already exist — skipping)"

  # First name mapper
  $KCADM create "identity-provider/instances/google/mappers" -r "$REALM" \
    -s name=google-first-name-mapper \
    -s identityProviderAlias=google \
    -s identityProviderMapper=google-user-attribute-mapper \
    -s "config.jsonField=given_name" \
    -s "config.userAttribute=firstName" \
    -s "config.syncMode=INHERIT" 2>/dev/null || \
    echo "  (first name mapper may already exist — skipping)"

  # Last name mapper
  $KCADM create "identity-provider/instances/google/mappers" -r "$REALM" \
    -s name=google-last-name-mapper \
    -s identityProviderAlias=google \
    -s identityProviderMapper=google-user-attribute-mapper \
    -s "config.jsonField=family_name" \
    -s "config.userAttribute=lastName" \
    -s "config.syncMode=INHERIT" 2>/dev/null || \
    echo "  (last name mapper may already exist — skipping)"
fi

# Step 4: Configure Google OAuth consent screen redirect URI
echo "[4/5] Verifying redirect URI configuration..."
REDIRECT_URI="https://auth.gostoa.dev/realms/$REALM/broker/google/endpoint"
echo "  Ensure this URI is in your Google Cloud Console authorized redirect URIs:"
echo "  $REDIRECT_URI"

# Step 5: Verify
echo "[5/5] Verifying configuration..."
if [ "$DRY_RUN" = false ]; then
  echo ""
  echo "Google IDP configuration:"
  $KCADM get "identity-provider/instances/google" -r "$REALM" \
    --fields alias,displayName,enabled,trustEmail 2>/dev/null | sed -n '1,20p'
  echo ""
  echo "IDP mappers:"
  $KCADM get "identity-provider/instances/google/mappers" -r "$REALM" \
    --fields name,identityProviderMapper 2>/dev/null
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "The provider remains disabled. Configure the approved-user broker flow before enabling it."
echo "See docs/runbooks/first-admin-bootstrap.md for invitations and secret storage."
