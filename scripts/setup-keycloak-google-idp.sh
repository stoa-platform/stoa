#!/bin/bash
# Configure Google Social Login Identity Provider in Keycloak (CAB-1873)
#
# Prerequisites:
#   1. Create OAuth 2.0 credentials in Google Cloud Console:
#      - Go to https://console.cloud.google.com/apis/credentials
#      - Create OAuth client ID (Web application)
#      - Authorized redirect URI: https://auth.gostoa.dev/realms/stoa/broker/google/endpoint
#      - Scopes: openid, profile, email
#   2. Store credentials in Infisical:
#      infisical secrets set GOOGLE_CLIENT_ID=<value> --env=prod --path=/keycloak
#      infisical secrets set GOOGLE_CLIENT_SECRET=<value> --env=prod --path=/keycloak
#
# Usage: ./setup-keycloak-google-idp.sh <KC_ADMIN_PWD> <GOOGLE_CLIENT_ID> <GOOGLE_CLIENT_SECRET>
#
# Security: Run with 'set +o history' to avoid leaking creds in shell history.

set -e

DRY_RUN=false
if [ "$1" = "--dry-run" ]; then
  DRY_RUN=true
  shift
  echo "[DRY RUN] No changes will be made."
fi

if [ $# -lt 3 ]; then
  echo "Usage: $0 [--dry-run] <KC_ADMIN_PWD> <GOOGLE_CLIENT_ID> <GOOGLE_CLIENT_SECRET>"
  echo ""
  echo "Example:"
  echo "  $0 MyAdminPwd 123456789.apps.googleusercontent.com GOCSPX-xxxxx"
  echo ""
  echo "Get KC admin password:"
  echo "  kubectl get secret keycloak -n stoa-system -o jsonpath='{.data.admin-password}' | base64 -d"
  echo ""
  echo "Prerequisites:"
  echo "  1. Create OAuth 2.0 credentials at https://console.cloud.google.com/apis/credentials"
  echo "  2. Set authorized redirect URI:"
  echo "     https://auth.gostoa.dev/realms/stoa/broker/google/endpoint"
  echo ""
  echo "IMPORTANT: Use 'set +o history' before running to avoid leaking creds in shell history."
  exit 1
fi

KC_ADMIN_PWD="$1"
GOOGLE_CLIENT_ID="$2"
GOOGLE_CLIENT_SECRET="$3"
REALM="stoa"

# Find Keycloak pod
KC_POD=$(kubectl get pods -n stoa-system -l app=keycloak -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -z "$KC_POD" ]; then
  KC_POD=$(kubectl get pods -n stoa-system -l app.kubernetes.io/name=keycloak -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
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
  $KCADM config credentials \
    --server http://localhost:8080 \
    --realm master \
    --user admin \
    --password "$KC_ADMIN_PWD"
fi

# Step 2: Create Google Identity Provider
echo "[2/5] Creating Google Identity Provider..."
if [ "$DRY_RUN" = false ]; then
  # Check if google IDP already exists
  EXISTING=$($KCADM get "identity-provider/instances/google" -r "$REALM" 2>/dev/null || echo "NOT_FOUND")
  if [ "$EXISTING" = "NOT_FOUND" ]; then
    $KCADM create "identity-provider/instances" -r "$REALM" \
      -s alias=google \
      -s displayName=Google \
      -s providerId=google \
      -s enabled=true \
      -s trustEmail=true \
      -s storeToken=false \
      -s addReadTokenRoleOnCreate=false \
      -s "firstBrokerLoginFlowAlias=first broker login" \
      -s "config.clientId=$GOOGLE_CLIENT_ID" \
      -s "config.clientSecret=$GOOGLE_CLIENT_SECRET" \
      -s "config.defaultScope=openid profile email" \
      -s "config.syncMode=IMPORT" \
      -s "config.guiOrder=1"
    echo "  Google IDP created."
  else
    echo "  Google IDP already exists. Updating credentials..."
    $KCADM update "identity-provider/instances/google" -r "$REALM" \
      -s "config.clientId=$GOOGLE_CLIENT_ID" \
      -s "config.clientSecret=$GOOGLE_CLIENT_SECRET" \
      -s enabled=true
    echo "  Google IDP updated."
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
    --fields alias,displayName,enabled,trustEmail,config 2>/dev/null | head -20
  echo ""
  echo "IDP mappers:"
  $KCADM get "identity-provider/instances/google/mappers" -r "$REALM" \
    --fields name,identityProviderMapper 2>/dev/null
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Social login flow:"
echo "  1. User visits console.gostoa.dev"
echo "  2. Clicks 'Login with Keycloak'"
echo "  3. Keycloak login page shows 'Sign in with Google' button"
echo "  4. User authenticates with Google"
echo "  5. First broker login creates Keycloak account (email trusted)"
echo "  6. User gets 'viewer' role by default"
echo "  7. User lands in Console with read-only access"
echo ""
echo "REMINDER: Store Google OAuth credentials in Infisical (vault.gostoa.dev)"
echo "  infisical secrets set GOOGLE_CLIENT_ID=$GOOGLE_CLIENT_ID --env=prod --path=/keycloak"
echo "  infisical secrets set GOOGLE_CLIENT_SECRET=<value> --env=prod --path=/keycloak"
echo ""
echo "Clear shell history: history -c"
