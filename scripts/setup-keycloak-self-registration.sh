#!/bin/bash
# Configure email verification and keep self-registration closed
# TERMS_URL defaults to http://localhost:3000/legal/terms; set an on-site URL if needed.
#
# Usage: ./setup-keycloak-self-registration.sh <KC_ADMIN_PWD> <SMTP_HOST> <SMTP_PORT> <SMTP_USER> <SMTP_PWD> <SMTP_FROM>
#
# ORDERING IS CRITICAL:
#   1. Configure SMTP (so email verification works)
#   2. Enable email verification
#   3. Enable VERIFY_EMAIL required action
#   4. Keep registration closed; use an approved invitation process
#
# Security: Store SMTP credentials in Infisical, not shell history.
#   Run with: set +o history  (or use env vars)

TERMS_URL="${TERMS_URL:-http://localhost:3000/legal/terms}"

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
  $KCADM update authentication/required-actions/VERIFY_EMAIL -r "$REALM" \
    -s enabled=true -s defaultAction=true
fi

# Step 5: Keep registration closed
echo "[5/6] Closing self-registration..."
if [ "$DRY_RUN" = false ]; then
  $KCADM update "realms/$REALM" -s registrationAllowed=false -s resetPasswordAllowed=false
fi

# Step 6: Add Terms of Service URL
echo "[6/6] Setting Terms of Service URL..."
if [ "$DRY_RUN" = false ]; then
  $KCADM update "realms/$REALM" \
    -s "attributes.termsUrl=${TERMS_URL}"
fi

# Verify
echo ""
echo "=== Verification ==="
if [ "$DRY_RUN" = false ]; then
  echo "Current realm settings:"
  $KCADM get "realms/$REALM" --fields registrationAllowed,verifyEmail,resetPasswordAllowed 2>/dev/null | head -20
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Registration is closed. Onboarding requires an approved invitation."
echo ""
echo "REMINDER: Store SMTP credentials in Infisical (vault.gostoa.dev)"
echo "  infisical secrets set SMTP_HOST=$SMTP_HOST --env=prod --path=/keycloak"
echo "  infisical secrets set SMTP_USER=$SMTP_USER --env=prod --path=/keycloak"
echo "  infisical secrets set SMTP_PASSWORD=<value> --env=prod --path=/keycloak"
echo ""
echo "Clear shell history: history -c"
