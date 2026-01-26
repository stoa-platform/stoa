#!/bin/bash
# CAB-940: Keycloak Realm Hardening Script
# Uses kcadm.sh for idempotent incremental changes
#
# Usage:
#   ./scripts/harden-keycloak-realm.sh
#
# Prerequisites:
#   - kcadm.sh configured with admin credentials
#   - Run: kcadm.sh config credentials --server <url> --realm master --user admin

set -euo pipefail

REALM="${KEYCLOAK_REALM:-stoa}"

echo "=== CAB-940: Hardening Keycloak Realm '${REALM}' ==="
echo ""

# Check if kcadm.sh is available
if ! command -v kcadm.sh &> /dev/null; then
    echo "ERROR: kcadm.sh not found. Install Keycloak admin CLI or run from Keycloak pod."
    exit 1
fi

# Token lifespans (15 min access, 8h session max)
echo "[1/6] Setting token lifespans..."
kcadm.sh update realms/${REALM} -s accessTokenLifespan=900
kcadm.sh update realms/${REALM} -s accessTokenLifespanForImplicitFlow=900
kcadm.sh update realms/${REALM} -s ssoSessionMaxLifespan=28800
kcadm.sh update realms/${REALM} -s clientSessionIdleTimeout=1800
kcadm.sh update realms/${REALM} -s clientSessionMaxLifespan=28800
echo "    Access token: 900s (15 min)"
echo "    SSO max: 28800s (8 hours)"

# Refresh token security
echo "[2/6] Configuring refresh token security..."
kcadm.sh update realms/${REALM} -s revokeRefreshToken=true
kcadm.sh update realms/${REALM} -s refreshTokenMaxReuse=0
echo "    Revoke on use: enabled"
echo "    Max reuse: 0"

# Brute force protection (enhanced)
echo "[3/6] Enhancing brute force protection..."
kcadm.sh update realms/${REALM} -s bruteForceProtected=true
kcadm.sh update realms/${REALM} -s maxFailureWaitSeconds=900
kcadm.sh update realms/${REALM} -s minimumQuickLoginWaitSeconds=60
kcadm.sh update realms/${REALM} -s waitIncrementSeconds=60
kcadm.sh update realms/${REALM} -s quickLoginCheckMilliSeconds=1000
kcadm.sh update realms/${REALM} -s maxDeltaTimeSeconds=43200
kcadm.sh update realms/${REALM} -s failureFactor=5
echo "    Lockout after: 5 failures"
echo "    Max wait: 900s (15 min)"

# Password policy
echo "[4/6] Setting password policy..."
kcadm.sh update realms/${REALM} -s 'passwordPolicy=length(12) and digits(1) and upperCase(1) and lowerCase(1) and specialChars(1) and notUsername and passwordHistory(5)'
echo "    Min length: 12"
echo "    Requirements: digit, upper, lower, special"
echo "    History: 5 passwords"

# Disable self-registration and self-service (belt + suspenders)
echo "[5/6] Disabling self-service features..."
kcadm.sh update realms/${REALM} -s registrationAllowed=false
kcadm.sh update realms/${REALM} -s registrationEmailAsUsername=false
kcadm.sh update realms/${REALM} -s editUsernameAllowed=false
echo "    Self-registration: disabled"
echo "    Edit username: disabled"

# Audit logging
echo "[6/6] Enabling audit logging..."
kcadm.sh update realms/${REALM} -s eventsEnabled=true
kcadm.sh update realms/${REALM} -s eventsExpiration=604800
kcadm.sh update realms/${REALM} -s adminEventsEnabled=true
kcadm.sh update realms/${REALM} -s adminEventsDetailsEnabled=true
kcadm.sh update realms/${REALM} -s 'eventsListeners=["jboss-logging"]'
echo "    User events: enabled (7 day retention)"
echo "    Admin events: enabled with details"

echo ""
echo "=== Keycloak realm '${REALM}' hardened ==="
echo ""
echo "Next steps:"
echo "  1. Apply NetworkPolicy: kubectl apply -f k8s/networkpolicy-keycloak.yaml"
echo "  2. Apply Ingress: kubectl apply -f k8s/ingress/keycloak-hardened.yaml"
echo "  3. Verify: ./scripts/verify-keycloak-hardening.sh"
