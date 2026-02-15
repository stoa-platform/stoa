#!/usr/bin/env bash
# =============================================================================
# STOA Platform — Keycloak Password Policy Configuration
# =============================================================================
# Configures NIST 800-63B + DORA Art.9 compliant password policy on Keycloak.
# Applies to both 'stoa' and 'master' realms.
# Also hardens brute-force protection settings.
#
# Usage:
#   KC_ADMIN_PASSWORD=<password> ./scripts/ops/configure-keycloak-policy.sh
#   KC_ADMIN_PASSWORD=<password> ./scripts/ops/configure-keycloak-policy.sh --dry-run
#
# Or get password from Infisical:
#   eval $(infisical-token)
#   KC_ADMIN_PASSWORD=$(infisical secrets get ADMIN_PASSWORD --env=prod --path=/keycloak --plain 2>/dev/null)
#   ./scripts/ops/configure-keycloak-policy.sh
#
# Prerequisites:
#   - Keycloak accessible at KEYCLOAK_URL
#   - Admin credentials (KC_ADMIN_USER / KC_ADMIN_PASSWORD)
#   - curl + jq installed
# =============================================================================
set -euo pipefail

# --- Configuration ---
KEYCLOAK_URL="${KEYCLOAK_URL:-https://auth.gostoa.dev}"
ADMIN_USER="${KC_ADMIN_USER:-admin}"
ADMIN_PASSWORD="${KC_ADMIN_PASSWORD:-}"
DRY_RUN=false
REALMS=("stoa" "master")

# Password policy — NIST 800-63B + DORA Art.9
# length(12): NIST minimum for user-chosen passwords
# upperCase(1)/lowerCase(1)/digits(1)/specialChars(1): DORA "strong authentication"
# notUsername: prevent trivial passwords
# passwordHistory(5): DORA "credential rotation"
# maxLength(128): support passphrases
# No forceExpiredPasswordChange — NIST 800-63B discourages forced expiration
PASSWORD_POLICY="length(12) and lowerCase(1) and upperCase(1) and digits(1) and specialChars(1) and notUsername and passwordHistory(5) and maxLength(128)"

# Brute-force protection settings
BRUTE_FORCE_MAX_FAILURES=5
BRUTE_FORCE_WAIT_SECONDS=900       # 15 minutes lockout
BRUTE_FORCE_MAX_WAIT_SECONDS=3600  # 1 hour max lockout (progressive)
BRUTE_FORCE_FAILURE_RESET=43200    # 12 hours to reset counter

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# --- Parse args ---
for arg in "$@"; do
  case $arg in
    --dry-run)  DRY_RUN=true ;;
    --help|-h)
      echo "Usage: KC_ADMIN_PASSWORD=<pwd> $0 [--dry-run]"
      echo ""
      echo "Environment:"
      echo "  KEYCLOAK_URL       Keycloak base URL (default: https://auth.gostoa.dev)"
      echo "  KC_ADMIN_USER      Admin username (default: admin)"
      echo "  KC_ADMIN_PASSWORD  Admin password (required)"
      exit 0
      ;;
  esac
done

# --- Validation ---
if [ -z "$ADMIN_PASSWORD" ]; then
  echo -e "${RED}Error: KC_ADMIN_PASSWORD not set${NC}"
  echo "Set it with: export KC_ADMIN_PASSWORD=<password>"
  echo "Or from Infisical: KC_ADMIN_PASSWORD=\$(infisical secrets get ADMIN_PASSWORD --env=prod --path=/keycloak --plain)"
  exit 1
fi

if ! command -v jq &>/dev/null; then
  echo -e "${RED}Error: jq is not installed${NC}"
  exit 1
fi

echo "=============================================="
echo "  STOA — Keycloak Password Policy Setup"
echo "=============================================="
echo -e "  Keycloak: ${CYAN}${KEYCLOAK_URL}${NC}"
echo -e "  Realms:   ${CYAN}${REALMS[*]}${NC}"
echo -e "  Dry run:  ${CYAN}${DRY_RUN}${NC}"
echo ""

# --- Get admin token ---
echo -e "${CYAN}[1/3] Getting admin token...${NC}"
TOKEN_RESPONSE=$(curl -sf -X POST "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=admin-cli" \
  -d "username=${ADMIN_USER}" \
  -d "password=${ADMIN_PASSWORD}" \
  -d "grant_type=password" 2>/dev/null || echo '{"error":"failed"}')

TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.access_token // empty')
if [ -z "$TOKEN" ]; then
  echo -e "${RED}Failed to get admin token. Check credentials.${NC}"
  echo "Response: $(echo "$TOKEN_RESPONSE" | jq -r 'del(.access_token) | .error_description // .error // "unknown"')"
  exit 1
fi
echo -e "  ${GREEN}OK${NC} — admin token obtained"

# --- Apply password policy ---
echo ""
echo -e "${CYAN}[2/3] Applying password policy...${NC}"
echo -e "  Policy: ${YELLOW}${PASSWORD_POLICY}${NC}"
echo ""

PASS=0
FAIL=0

for REALM in "${REALMS[@]}"; do
  echo -n "  Realm '${REALM}': "

  # Read current policy
  CURRENT=$(curl -sf "${KEYCLOAK_URL}/admin/realms/${REALM}" \
    -H "Authorization: Bearer ${TOKEN}" 2>/dev/null | jq -r '.passwordPolicy // "none"')
  echo -n "(current: ${CURRENT}) "

  if [ "$CURRENT" = "$PASSWORD_POLICY" ]; then
    echo -e "${GREEN}already configured${NC}"
    PASS=$((PASS + 1))
    continue
  fi

  if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}would update${NC}"
    PASS=$((PASS + 1))
    continue
  fi

  # Apply password policy
  HTTP_CODE=$(curl -sf -o /dev/null -w '%{http_code}' \
    -X PUT "${KEYCLOAK_URL}/admin/realms/${REALM}" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg policy "$PASSWORD_POLICY" '{passwordPolicy: $policy}')" 2>/dev/null || echo "000")

  if [ "$HTTP_CODE" = "204" ] || [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}updated${NC}"
    PASS=$((PASS + 1))
  else
    echo -e "${RED}FAILED (HTTP ${HTTP_CODE})${NC}"
    FAIL=$((FAIL + 1))
  fi
done

# --- Harden brute-force protection ---
echo ""
echo -e "${CYAN}[3/3] Hardening brute-force protection...${NC}"
echo "  Max failures:       ${BRUTE_FORCE_MAX_FAILURES}"
echo "  Wait (initial):     ${BRUTE_FORCE_WAIT_SECONDS}s (15 min)"
echo "  Wait (max):         ${BRUTE_FORCE_MAX_WAIT_SECONDS}s (1 hour)"
echo "  Failure reset:      ${BRUTE_FORCE_FAILURE_RESET}s (12 hours)"
echo ""

for REALM in "${REALMS[@]}"; do
  echo -n "  Realm '${REALM}': "

  if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}would update brute-force settings${NC}"
    PASS=$((PASS + 1))
    continue
  fi

  HTTP_CODE=$(curl -sf -o /dev/null -w '%{http_code}' \
    -X PUT "${KEYCLOAK_URL}/admin/realms/${REALM}" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$(jq -n \
      --argjson maxFailures "$BRUTE_FORCE_MAX_FAILURES" \
      --argjson waitSeconds "$BRUTE_FORCE_WAIT_SECONDS" \
      --argjson maxWaitSeconds "$BRUTE_FORCE_MAX_WAIT_SECONDS" \
      --argjson failureReset "$BRUTE_FORCE_FAILURE_RESET" \
      '{
        bruteForceProtected: true,
        permanentLockout: false,
        maxFailureWaitSeconds: $maxWaitSeconds,
        minimumQuickLoginWaitSeconds: 60,
        waitIncrementSeconds: $waitSeconds,
        maxDeltaTimeSeconds: $failureReset,
        failureFactor: $maxFailures
      }')" 2>/dev/null || echo "000")

  if [ "$HTTP_CODE" = "204" ] || [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}updated${NC}"
    PASS=$((PASS + 1))
  else
    echo -e "${RED}FAILED (HTTP ${HTTP_CODE})${NC}"
    FAIL=$((FAIL + 1))
  fi
done

# --- Verify ---
echo ""
echo "=============================================="
echo "  Verification"
echo "=============================================="
for REALM in "${REALMS[@]}"; do
  POLICY=$(curl -sf "${KEYCLOAK_URL}/admin/realms/${REALM}" \
    -H "Authorization: Bearer ${TOKEN}" 2>/dev/null | jq -r '.passwordPolicy // "none"')
  BF=$(curl -sf "${KEYCLOAK_URL}/admin/realms/${REALM}" \
    -H "Authorization: Bearer ${TOKEN}" 2>/dev/null | jq -r '.bruteForceProtected // false')
  FAILURES=$(curl -sf "${KEYCLOAK_URL}/admin/realms/${REALM}" \
    -H "Authorization: Bearer ${TOKEN}" 2>/dev/null | jq -r '.failureFactor // "?"')
  echo "  ${REALM}:"
  echo "    passwordPolicy:     ${POLICY}"
  echo "    bruteForceProtected: ${BF}"
  echo "    failureFactor:      ${FAILURES}"
done

# --- Summary ---
echo ""
echo "=============================================="
if [ "$FAIL" -eq 0 ]; then
  echo -e "  ${GREEN}All ${PASS} operations succeeded${NC}"
else
  echo -e "  ${RED}${FAIL} operation(s) failed${NC}"
fi
echo "=============================================="

exit "$FAIL"
