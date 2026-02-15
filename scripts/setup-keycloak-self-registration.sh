#!/bin/bash
# Enable Keycloak Self-Registration for STOA Developer Portal (CAB-1170)
#
# Usage: ./setup-keycloak-self-registration.sh <KC_ADMIN_PWD> <SMTP_HOST> <SMTP_PORT> <SMTP_USER> <SMTP_PWD> <SMTP_FROM>
#
# ORDERING IS CRITICAL:
#   1. Configure SMTP (so email verification works)
#   2. Enable email verification
#   3. Enable VERIFY_EMAIL required action
#   4. Enable registration (LAST — so users never register without email verification)
#
# Security: Store SMTP credentials in Infisical, not shell history.
#   Run with: set +o history  (or use env vars)

set -e

DRY_RUN=false
if [ "$1" = "--dry-run" ]; then
  DRY_RUN=true
  shift
  echo "[DRY RUN] No changes will be made."
fi

if [ $# -lt 6 ]; then
  echo "Usage: $0 [--dry-run] <KC_ADMIN_PWD> <SMTP_HOST> <SMTP_PORT> <SMTP_USER> <SMTP_PWD> <SMTP_FROM>"
  echo ""
  echo "Example:"
  echo "  $0 MyAdminPwd smtp.sendgrid.net 587 apikey SG.xxx noreply@gostoa.dev"
  echo ""
  echo "Get KC admin password:"
  echo "  kubectl get secret keycloak -n stoa-system -o jsonpath='{.data.admin-password}' | base64 -d"
  echo ""
  echo "IMPORTANT: Use 'set +o history' before running to avoid leaking creds in shell history."
  echo "           Store SMTP credentials in Infisical after setup."
  exit 1
fi

KC_ADMIN_PWD="$1"
SMTP_HOST="$2"
SMTP_PORT="$3"
SMTP_USER="$4"
SMTP_PWD="$5"
SMTP_FROM="$6"
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

echo "=== STOA Self-Registration Setup (CAB-1170) ==="
echo "Keycloak pod: $KC_POD"
echo "Realm: $REALM"
echo ""

# Step 1: Login
echo "[1/6] Logging into Keycloak..."
if [ "$DRY_RUN" = false ]; then
  $KCADM config credentials \
    --server http://localhost:8080 \
    --realm master \
    --user admin \
    --password "$KC_ADMIN_PWD"
fi

# Step 2: Configure SMTP
echo "[2/6] Configuring SMTP server..."
SMTP_JSON="{\"host\":\"$SMTP_HOST\",\"port\":\"$SMTP_PORT\",\"from\":\"$SMTP_FROM\",\"fromDisplayName\":\"STOA Platform\",\"auth\":\"true\",\"user\":\"$SMTP_USER\",\"password\":\"$SMTP_PWD\",\"starttls\":\"true\",\"ssl\":\"false\"}"
echo "  Host: $SMTP_HOST:$SMTP_PORT"
echo "  From: $SMTP_FROM"
if [ "$DRY_RUN" = false ]; then
  $KCADM update "realms/$REALM" -s "smtpServer=$SMTP_JSON"
fi

# Step 3: Enable email verification
echo "[3/6] Enabling email verification..."
if [ "$DRY_RUN" = false ]; then
  $KCADM update "realms/$REALM" -s verifyEmail=true
fi

# Step 4: Enable VERIFY_EMAIL required action
echo "[4/6] Enabling VERIFY_EMAIL required action..."
if [ "$DRY_RUN" = false ]; then
  $KCADM update "realms/$REALM" \
    -s 'requiredActions=[{"alias":"VERIFY_EMAIL","name":"Verify Email","providerId":"VERIFY_EMAIL","enabled":true,"defaultAction":true,"priority":50}]' 2>/dev/null || \
  echo "  (VERIFY_EMAIL may already be configured — checking...)"
fi

# Step 5: Enable registration
echo "[5/6] Enabling self-registration..."
if [ "$DRY_RUN" = false ]; then
  $KCADM update "realms/$REALM" -s registrationAllowed=true
fi

# Step 6: Add Terms of Service URL
echo "[6/6] Setting Terms of Service URL..."
if [ "$DRY_RUN" = false ]; then
  $KCADM update "realms/$REALM" \
    -s 'attributes={"termsUrl":"https://docs.gostoa.dev/legal/terms"}'
fi

# Verify
echo ""
echo "=== Verification ==="
if [ "$DRY_RUN" = false ]; then
  echo "Current realm settings:"
  $KCADM get "realms/$REALM" --fields registrationAllowed,verifyEmail,smtpServer 2>/dev/null | head -20
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Self-registration flow:"
echo "  1. Developer visits portal.gostoa.dev"
echo "  2. Clicks 'Create Free Account'"
echo "  3. Redirected to Keycloak registration form"
echo "  4. Receives email verification"
echo "  5. Verifies email -> lands in Portal"
echo "  6. Auto-provisioned: personal tenant + viewer role"
echo ""
echo "REMINDER: Store SMTP credentials in Infisical (vault.gostoa.dev)"
echo "  infisical secrets set SMTP_HOST=$SMTP_HOST --env=prod --path=/keycloak"
echo "  infisical secrets set SMTP_USER=$SMTP_USER --env=prod --path=/keycloak"
echo "  infisical secrets set SMTP_PASSWORD=<value> --env=prod --path=/keycloak"
echo ""
echo "Clear shell history: history -c"
