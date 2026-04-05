#!/bin/bash
# validate-keycloak.sh — Post-boot validation for Keycloak realm integrity
#
# Verifies that all required OIDC scopes exist and are assigned to clients.
# Catches the silent failure where KC imports a realm but skips undefined scopes.
#
# Usage:
#   docker compose exec keycloak /scripts/validate-keycloak.sh
#   ./deploy/docker-compose/scripts/validate-keycloak.sh          # from host
#
# Exit codes:
#   0 = all checks passed
#   1 = missing scopes or scope assignments detected

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
REALM="${KC_REALM:-stoa}"
KC_URL="${KC_INTERNAL_URL:-http://localhost:8080}"
KC_HEALTH_URL="${KC_HEALTH_URL:-http://localhost:9000}"
KC_ADMIN="${KEYCLOAK_ADMIN:-admin}"
KC_ADMIN_PASS="${KEYCLOAK_ADMIN_PASSWORD:-admin}"

# Expected scopes that MUST exist in the realm
REQUIRED_SCOPES=(
  profile email roles web-origins acr basic
  offline_access address phone microprofile-jwt
  stoa-identity "stoa:read" "stoa:write" "stoa:admin"
)

# Default client scopes that MUST be assigned to OIDC clients
DEFAULT_SCOPES=(web-origins acr profile roles email)

# Clients to validate scope assignments on
CLIENTS=(control-plane-ui stoa-portal control-plane-api stoa-mcp-gateway)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

pass() { echo -e "  ${GREEN}[PASS]${NC} $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; ERRORS=$((ERRORS + 1)); }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; }

ERRORS=0

# ---------------------------------------------------------------------------
# Detect execution context (inside container vs host)
# ---------------------------------------------------------------------------
if [ -x /opt/keycloak/bin/kcadm.sh ]; then
  KCADM="/opt/keycloak/bin/kcadm.sh"
else
  # Running from host — use docker exec
  CONTAINER="${KC_CONTAINER:-stoa-keycloak}"
  KCADM="docker exec ${CONTAINER} /opt/keycloak/bin/kcadm.sh"
fi

# ---------------------------------------------------------------------------
# Wait for KC to be ready
# ---------------------------------------------------------------------------
echo "Waiting for Keycloak at ${KC_URL}..."
for i in $(seq 1 30); do
  # KC 26.x: health on management port 9000, fallback to main port
  if curl -sf "${KC_HEALTH_URL}/health/ready" > /dev/null 2>&1 \
     || curl -sf "${KC_URL}/health/ready" > /dev/null 2>&1 \
     || curl -sf "${KC_URL}/realms/master" > /dev/null 2>&1; then
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo -e "${RED}ERROR: Keycloak not ready after 30s${NC}"
    exit 1
  fi
  sleep 1
done
echo "Keycloak is ready."
echo ""

# ---------------------------------------------------------------------------
# Authenticate
# ---------------------------------------------------------------------------
$KCADM config credentials --server "$KC_URL" --realm master \
  --user "$KC_ADMIN" --password "$KC_ADMIN_PASS" 2>/dev/null

# ---------------------------------------------------------------------------
# Check 1: Required scopes exist
# ---------------------------------------------------------------------------
echo "=== Check 1: Required client scopes exist in realm '${REALM}' ==="

EXISTING_SCOPES=$($KCADM get client-scopes -r "$REALM" --fields name 2>/dev/null \
  | python3 -c "import sys,json; print('\n'.join(s['name'] for s in json.load(sys.stdin)))" 2>/dev/null)

for scope in "${REQUIRED_SCOPES[@]}"; do
  if echo "$EXISTING_SCOPES" | grep -qx "$scope"; then
    pass "$scope"
  else
    fail "$scope — MISSING (realm import did not create it)"
  fi
done
echo ""

# ---------------------------------------------------------------------------
# Check 2: Default scopes assigned to clients
# ---------------------------------------------------------------------------
echo "=== Check 2: Default scopes assigned to OIDC clients ==="

for client_id in "${CLIENTS[@]}"; do
  echo "  Client: $client_id"

  # Get client UUID
  CLIENT_UUID=$($KCADM get clients -r "$REALM" -q "clientId=$client_id" --fields id 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0]['id'] if d else '')" 2>/dev/null)

  if [ -z "$CLIENT_UUID" ]; then
    warn "    Client '$client_id' not found — skipping"
    continue
  fi

  # Get assigned default scopes
  ASSIGNED=$($KCADM get "clients/${CLIENT_UUID}/default-client-scopes" -r "$REALM" --fields name 2>/dev/null \
    | python3 -c "import sys,json; print('\n'.join(s['name'] for s in json.load(sys.stdin)))" 2>/dev/null)

  for scope in "${DEFAULT_SCOPES[@]}"; do
    if echo "$ASSIGNED" | grep -qx "$scope"; then
      pass "  $scope"
    else
      fail "  $scope — NOT ASSIGNED to $client_id"
    fi
  done
done
echo ""

# ---------------------------------------------------------------------------
# Check 3: Audience mappers have correct config
# KC 26.x --import-realm sometimes imports protocol mappers with empty config.
# This check detects and auto-fixes the issue.
# ---------------------------------------------------------------------------
echo "=== Check 3: Audience mapper config on OIDC clients ==="

AUDIENCE_CLIENTS=(control-plane-ui stoa-portal stoa-identity-governance)
FIXES_APPLIED=0

for client_id in "${AUDIENCE_CLIENTS[@]}"; do
  CLIENT_UUID=$($KCADM get clients -r "$REALM" -q "clientId=$client_id" --fields id 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0]['id'] if d else '')" 2>/dev/null)

  if [ -z "$CLIENT_UUID" ]; then
    warn "$client_id — client not found, skipping"
    continue
  fi

  # Check if audience mapper exists with correct config
  MAPPER_STATUS=$($KCADM get "clients/${CLIENT_UUID}/protocol-mappers/models" -r "$REALM" 2>/dev/null \
    | python3 -c "
import sys,json
found = False
for m in json.load(sys.stdin):
    if m.get('protocolMapper') == 'oidc-audience-mapper' and 'audience' in m.get('name','').lower():
        found = True
        cfg = m.get('config', {})
        if cfg.get('included.client.audience') == 'control-plane-api':
            print('OK')
        else:
            print(f'EMPTY:{m[\"id\"]}')
        break
if not found:
    print('MISSING')
" 2>/dev/null)

  case "$MAPPER_STATUS" in
    OK)
      pass "$client_id — audience mapper configured"
      ;;
    EMPTY:*)
      MAPPER_ID="${MAPPER_STATUS#EMPTY:}"
      warn "$client_id — audience mapper has empty config, auto-fixing..."
      # Delete and recreate (update doesn't work reliably with dotted keys)
      $KCADM delete "clients/${CLIENT_UUID}/protocol-mappers/models/${MAPPER_ID}" -r "$REALM" 2>/dev/null
      $KCADM create "clients/${CLIENT_UUID}/protocol-mappers/models" -r "$REALM" \
        -b '{"name":"control-plane-api-audience","protocol":"openid-connect","protocolMapper":"oidc-audience-mapper","consentRequired":false,"config":{"included.client.audience":"control-plane-api","id.token.claim":"false","access.token.claim":"true"}}' 2>/dev/null
      FIXES_APPLIED=$((FIXES_APPLIED + 1))
      pass "$client_id — audience mapper auto-fixed"
      ;;
    MISSING)
      warn "$client_id — audience mapper missing, creating..."
      $KCADM create "clients/${CLIENT_UUID}/protocol-mappers/models" -r "$REALM" \
        -b '{"name":"control-plane-api-audience","protocol":"openid-connect","protocolMapper":"oidc-audience-mapper","consentRequired":false,"config":{"included.client.audience":"control-plane-api","id.token.claim":"false","access.token.claim":"true"}}' 2>/dev/null
      FIXES_APPLIED=$((FIXES_APPLIED + 1))
      pass "$client_id — audience mapper created"
      ;;
  esac
done

if [ "$FIXES_APPLIED" -gt 0 ]; then
  echo ""
  echo -e "  ${YELLOW}Auto-fixed ${FIXES_APPLIED} audience mapper(s).${NC}"
fi
echo ""

# ---------------------------------------------------------------------------
# Check 4: Apply custom passwords from .env.keycloak (if exists)
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_KC="${SCRIPT_DIR}/../.env.keycloak"

if [ -f "$ENV_KC" ]; then
  echo "=== Check 4: Applying custom passwords from .env.keycloak ==="
  while IFS='=' read -r user pwd; do
    # Skip comments and empty lines
    [[ "$user" =~ ^#.*$ ]] && continue
    [[ -z "$user" ]] && continue

    USER_UUID=$($KCADM get users -r "$REALM" -q "username=$user" --fields id 2>/dev/null \
      | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0]['id'] if d else '')" 2>/dev/null)

    if [ -z "$USER_UUID" ]; then
      warn "$user — user not found, skipping"
      continue
    fi

    # Clear brute force locks first
    $KCADM delete "attack-detection/brute-force/users/${USER_UUID}" -r "$REALM" 2>/dev/null

    # Set password (may fail if same as history — that's OK, means it's already set)
    if $KCADM set-password -r "$REALM" --userid "$USER_UUID" --new-password "$pwd" --temporary=false 2>/dev/null; then
      pass "$user — password set"
    else
      warn "$user — password unchanged (already in history or same)"
    fi
  done < "$ENV_KC"
  echo ""
else
  echo "=== Check 4: No .env.keycloak found (custom passwords skipped) ==="
  echo "  To persist custom passwords across KC resets, create:"
  echo "  ${ENV_KC}"
  echo "  Format: username=password (one per line)"
  echo ""
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
if [ "$ERRORS" -gt 0 ]; then
  echo -e "${RED}FAILED: ${ERRORS} check(s) failed.${NC}"
  echo ""
  echo "Fix: ensure all scopes are defined in clientScopes[] of keycloak-realm.json"
  echo "Then: docker compose down keycloak && docker volume rm <kc_volume> && docker compose up -d keycloak"
  exit 1
else
  echo -e "${GREEN}ALL CHECKS PASSED${NC} — Keycloak realm '${REALM}' is correctly configured."
  exit 0
fi
