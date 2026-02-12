#!/usr/bin/env bash
# =============================================================================
# Setup GitHub Secrets for E2E nightly tests
# =============================================================================
# Configures the 17 secrets required by reusable-smoke-test.yml (Tier 2).
# Run once, then update when Keycloak passwords change.
#
# Prerequisites:
#   - gh CLI authenticated (gh auth status)
#   - Access to Keycloak admin (auth.gostoa.dev) for persona passwords
#
# Usage:
#   ./scripts/dev/setup-e2e-secrets.sh
# =============================================================================
set -euo pipefail

REPO="stoa-platform/stoa"

echo "Setting up E2E GitHub Secrets for $REPO"
echo "==========================================="
echo ""
echo "This script requires Keycloak persona passwords."
echo "Get them from: https://auth.gostoa.dev/admin/master/console/#/stoa/users"
echo ""

# --- URLs (with defaults — optional, but explicit is better) ---
gh secret set E2E_PORTAL_URL  --repo "$REPO" --body "https://portal.gostoa.dev"
gh secret set E2E_CONSOLE_URL --repo "$REPO" --body "https://console.gostoa.dev"
gh secret set E2E_GATEWAY_URL --repo "$REPO" --body "https://api.gostoa.dev"
gh secret set E2E_KEYCLOAK_URL --repo "$REPO" --body "https://auth.gostoa.dev"
echo "  URLs configured"

# --- Personas (REQUIRED — prompt for passwords) ---
personas=("PARZIVAL" "ART3MIS" "AECH" "SORRENTO" "ANORAK" "ALEX")
usernames=("parzival" "art3mis" "aech" "sorrento" "anorak" "alex")

for i in "${!personas[@]}"; do
  name="${personas[$i]}"
  user="${usernames[$i]}"
  gh secret set "${name}_USER" --repo "$REPO" --body "$user"

  read -rsp "  Enter password for $user: " password
  echo ""
  gh secret set "${name}_PASSWORD" --repo "$REPO" --body "$password"
done
echo "  Personas configured"

# --- API Key ---
read -rsp "  Enter TEST_API_KEY (gateway API key): " apikey
echo ""
gh secret set TEST_API_KEY --repo "$REPO" --body "$apikey"
echo "  API key configured"

echo ""
echo "Done! 17 secrets configured for $REPO."
echo "Verify with: gh secret list --repo $REPO"
