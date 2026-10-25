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
: "${TERMS_URL:?TERMS_URL is required: set the on-site Terms of Service URL}"
: "${SMTP_HOST:?SMTP_HOST is required}"
: "${SMTP_PORT:?SMTP_PORT is required}"
: "${SMTP_USER:?SMTP_USER is required}"
: "${SMTP_PWD:?SMTP_PWD is required}"
: "${SMTP_FROM:?SMTP_FROM is required}"
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

echo "=== STOA Self-Registration Setup (CAB-1170) ==="
echo "Keycloak pod: $KC_POD"
echo "Realm: $REALM"
echo ""

# Step 1: Login
echo "[1/6] Logging into Keycloak..."
if [ "$DRY_RUN" = false ]; then
  printf '%s\n' "$KC_ADMIN_PWD" | kubectl exec -i -n stoa-system "$KC_POD" -- /opt/keycloak/bin/kcadm.sh config credentials \
    --server http://localhost:8080 \
    --realm master \
    --user admin
fi

# Step 2: Configure SMTP
echo "[2/6] Configuring SMTP server..."
SMTP_JSON="{\"host\":\"$SMTP_HOST\",\"port\":\"$SMTP_PORT\",\"from\":\"$SMTP_FROM\",\"fromDisplayName\":\"STOA Platform\",\"auth\":\"true\",\"user\":\"$SMTP_USER\",\"password\":\"$SMTP_PWD\",\"starttls\":\"true\",\"ssl\":\"false\"}"
echo "  Host: $SMTP_HOST:$SMTP_PORT"
echo "  From: $SMTP_FROM"
if [ "$DRY_RUN" = false ]; then
  printf '{"smtpServer":%s}\n' "$SMTP_JSON" | kubectl exec -i -n stoa-system "$KC_POD" -- /opt/keycloak/bin/kcadm.sh update "realms/$REALM" -f -
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
  $KCADM get "realms/$REALM" --fields registrationAllowed,verifyEmail,resetPasswordAllowed 2>/dev/null | sed -n '1,20p'
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Registration is closed. Onboarding requires an approved invitation."
echo ""
echo "Store SMTP credentials through stdin using your on-site secret store."
echo "See docs/runbooks/first-admin-bootstrap.md."
