#!/usr/bin/env bash
# =============================================================================
# STOA Platform — Cloudflare Access Setup for Infisical
# =============================================================================
# Puts vault.gostoa.dev behind Cloudflare Access (Zero Trust).
# Creates an Access Application + Service Token for CLI/API access.
#
# Prerequisites:
#   - Cloudflare API token with: Zone:DNS:Edit + Access:Edit
#     (current DNS-only token needs upgrading — see runbook)
#   - Zone: gostoa.dev (748bf095e4882ca8e46f21837067ced8)
#   - CF_API_TOKEN or CLOUDFLARE_API_TOKEN env var set
#
# Usage:
#   ./scripts/ops/setup-cloudflare-access.sh              # Full setup
#   ./scripts/ops/setup-cloudflare-access.sh --dry-run     # Preview only
#   ./scripts/ops/setup-cloudflare-access.sh --status      # Check current state
#
# What this script does:
#   1. Enables proxy (orange cloud) on vault.gostoa.dev DNS record
#   2. Creates a Cloudflare Access Application for vault.gostoa.dev
#   3. Creates a Service Token for CLI/API access (scripts, VPS)
#   4. Creates an Access Policy: Service Token + email-based auth
#   5. Outputs the CF-Access-Client-Id and CF-Access-Client-Secret
#
# After running:
#   - Store Service Token credentials in Infisical: /cloudflare/CF_ACCESS_*
#   - Add to ~/.zprofile: export CF_ACCESS_CLIENT_ID=xxx CF_ACCESS_CLIENT_SECRET=xxx
#   - VPS: add to ~/.env.hegemon
# =============================================================================
set -euo pipefail

# --- Configuration ---
CF_API_TOKEN="${CF_API_TOKEN:-${CLOUDFLARE_API_TOKEN:-}}"
CF_ZONE_ID="748bf095e4882ca8e46f21837067ced8"
CF_ACCOUNT_ID=""  # Will be auto-detected
DOMAIN="vault.gostoa.dev"
APP_NAME="Infisical (vault.gostoa.dev)"
SERVICE_TOKEN_NAME="stoa-infisical-cli"
ADMIN_EMAIL="admin@gostoa.dev"

DRY_RUN=false
STATUS_ONLY=false

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

usage() {
  echo "Usage: $0 [--dry-run|--status]"
  echo ""
  echo "Environment:"
  echo "  CF_API_TOKEN   Cloudflare API token (Zone:DNS:Edit + Access:Edit)"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=true; shift ;;
    --status)  STATUS_ONLY=true; shift ;;
    -h|--help) usage ;;
    *) echo "Unknown: $1"; usage ;;
  esac
done

[ -z "$CF_API_TOKEN" ] && {
  echo -e "${RED}CF_API_TOKEN or CLOUDFLARE_API_TOKEN must be set${NC}"
  echo "Create token at: https://dash.cloudflare.com/profile/api-tokens"
  echo "Required permissions: Zone:DNS:Edit, Access:Organizations/Identity Providers/Groups:Edit"
  exit 1
}

cf_api() {
  local method="$1" path="$2"
  shift 2
  curl -sf -X "$method" "https://api.cloudflare.com/client/v4${path}" \
    -H "Authorization: Bearer ${CF_API_TOKEN}" \
    -H "Content-Type: application/json" \
    "$@"
}

# --- Step 0: Detect Account ID ---
echo -e "${CYAN}=== Cloudflare Access Setup for ${DOMAIN} ===${NC}"
echo ""

echo -n "[0/5] Detecting account ID... "
CF_ACCOUNT_ID=$(cf_api GET "/zones/${CF_ZONE_ID}" | jq -r '.result.account.id')
echo -e "${GREEN}${CF_ACCOUNT_ID}${NC}"

# --- Status mode ---
if [ "$STATUS_ONLY" = true ]; then
  echo ""
  echo -e "${BOLD}DNS Record:${NC}"
  cf_api GET "/zones/${CF_ZONE_ID}/dns_records?name=${DOMAIN}" | \
    jq -r '.result[] | "  Type: \(.type) | IP: \(.content) | Proxied: \(.proxied)"'

  echo ""
  echo -e "${BOLD}Access Applications:${NC}"
  cf_api GET "/accounts/${CF_ACCOUNT_ID}/access/apps" | \
    jq -r '.result[]? | select(.domain == "'"$DOMAIN"'") | "  \(.name) | ID: \(.id) | Type: \(.type)"'

  echo ""
  echo -e "${BOLD}Service Tokens:${NC}"
  cf_api GET "/accounts/${CF_ACCOUNT_ID}/access/service_tokens" | \
    jq -r '.result[]? | select(.name == "'"$SERVICE_TOKEN_NAME"'") | "  \(.name) | ID: \(.id) | Expires: \(.expires_at // "never")"'

  exit 0
fi

# --- Step 1: Enable proxy (orange cloud) ---
echo -n "[1/5] Enabling proxy on ${DOMAIN}... "
DNS_RECORD=$(cf_api GET "/zones/${CF_ZONE_ID}/dns_records?name=${DOMAIN}" | jq -r '.result[0]')
DNS_ID=$(echo "$DNS_RECORD" | jq -r '.id')
IS_PROXIED=$(echo "$DNS_RECORD" | jq -r '.proxied')

if [ "$IS_PROXIED" = "true" ]; then
  echo -e "${GREEN}already proxied${NC}"
elif [ "$DRY_RUN" = true ]; then
  echo -e "${YELLOW}[dry-run] would enable proxy${NC}"
else
  cf_api PATCH "/zones/${CF_ZONE_ID}/dns_records/${DNS_ID}" \
    -d '{"proxied": true}' > /dev/null
  echo -e "${GREEN}done${NC}"
fi

# --- Step 2: Create Access Application ---
echo -n "[2/5] Creating Access Application... "
EXISTING_APP=$(cf_api GET "/accounts/${CF_ACCOUNT_ID}/access/apps" | \
  jq -r '.result[]? | select(.domain == "'"$DOMAIN"'") | .id')

if [ -n "$EXISTING_APP" ]; then
  echo -e "${GREEN}exists (${EXISTING_APP})${NC}"
  APP_ID="$EXISTING_APP"
elif [ "$DRY_RUN" = true ]; then
  echo -e "${YELLOW}[dry-run] would create app${NC}"
  APP_ID="dry-run-id"
else
  APP_RESULT=$(cf_api POST "/accounts/${CF_ACCOUNT_ID}/access/apps" \
    -d "$(jq -n \
      --arg name "$APP_NAME" \
      --arg domain "$DOMAIN" \
      '{
        name: $name,
        domain: $domain,
        type: "self_hosted",
        session_duration: "24h",
        auto_redirect_to_identity: false,
        http_only_cookie_attribute: true,
        same_site_cookie_attribute: "lax"
      }')")
  APP_ID=$(echo "$APP_RESULT" | jq -r '.result.id')
  echo -e "${GREEN}created (${APP_ID})${NC}"
fi

# --- Step 3: Create Service Token ---
echo -n "[3/5] Creating Service Token... "
EXISTING_TOKEN=$(cf_api GET "/accounts/${CF_ACCOUNT_ID}/access/service_tokens" | \
  jq -r '.result[]? | select(.name == "'"$SERVICE_TOKEN_NAME"'") | .id')

if [ -n "$EXISTING_TOKEN" ]; then
  echo -e "${GREEN}exists (use --status to see details)${NC}"
  TOKEN_CLIENT_ID=""
  TOKEN_CLIENT_SECRET=""
elif [ "$DRY_RUN" = true ]; then
  echo -e "${YELLOW}[dry-run] would create service token${NC}"
  TOKEN_CLIENT_ID="dry-run-client-id"
  TOKEN_CLIENT_SECRET="dry-run-client-secret"
else
  TOKEN_RESULT=$(cf_api POST "/accounts/${CF_ACCOUNT_ID}/access/service_tokens" \
    -d "$(jq -n --arg name "$SERVICE_TOKEN_NAME" '{name: $name, duration: "8760h"}')")
  TOKEN_CLIENT_ID=$(echo "$TOKEN_RESULT" | jq -r '.result.client_id')
  TOKEN_CLIENT_SECRET=$(echo "$TOKEN_RESULT" | jq -r '.result.client_secret')
  echo -e "${GREEN}created${NC}"
fi

# --- Step 4: Create Access Policy ---
echo -n "[4/5] Creating Access Policy... "
if [ -n "$EXISTING_APP" ]; then
  EXISTING_POLICY=$(cf_api GET "/accounts/${CF_ACCOUNT_ID}/access/apps/${APP_ID}/policies" | \
    jq -r '.result[]? | .id' | head -1)
  if [ -n "$EXISTING_POLICY" ]; then
    echo -e "${GREEN}exists${NC}"
  fi
elif [ "$DRY_RUN" = true ]; then
  echo -e "${YELLOW}[dry-run] would create policy${NC}"
else
  cf_api POST "/accounts/${CF_ACCOUNT_ID}/access/apps/${APP_ID}/policies" \
    -d "$(jq -n \
      --arg email "$ADMIN_EMAIL" \
      '{
        name: "STOA Admin + Service Token",
        decision: "non_identity",
        include: [
          { "service_token": {} }
        ],
        precedence: 1
      }')" > /dev/null

  # Add email-based policy for browser access
  cf_api POST "/accounts/${CF_ACCOUNT_ID}/access/apps/${APP_ID}/policies" \
    -d "$(jq -n \
      --arg email "$ADMIN_EMAIL" \
      '{
        name: "Admin Email",
        decision: "allow",
        include: [
          { "email": { "email": $email } }
        ],
        precedence: 2
      }')" > /dev/null
  echo -e "${GREEN}created (service token + email)${NC}"
fi

# --- Step 5: Output ---
echo -n "[5/5] Generating configuration... "
echo -e "${GREEN}done${NC}"

echo ""
echo -e "${BOLD}${CYAN}=== Setup Complete ===${NC}"
echo ""

if [ -n "$TOKEN_CLIENT_ID" ] && [ -n "$TOKEN_CLIENT_SECRET" ]; then
  echo -e "${BOLD}Service Token Credentials:${NC}"
  echo -e "  ${YELLOW}CF_ACCESS_CLIENT_ID${NC}=${TOKEN_CLIENT_ID}"
  echo -e "  ${YELLOW}CF_ACCESS_CLIENT_SECRET${NC}=${TOKEN_CLIENT_SECRET}"
  echo ""
  echo -e "${RED}SAVE THESE NOW — the secret cannot be retrieved later.${NC}"
  echo ""
  echo -e "${BOLD}Next steps:${NC}"
  echo "  1. Store in Infisical:  infisical secrets set CF_ACCESS_CLIENT_ID=${TOKEN_CLIENT_ID} --env=prod --path=/cloudflare"
  echo "  2. Store in Infisical:  infisical secrets set CF_ACCESS_CLIENT_SECRET=<secret> --env=prod --path=/cloudflare"
  echo "  3. Add to ~/.zprofile:"
  echo "     export CF_ACCESS_CLIENT_ID=${TOKEN_CLIENT_ID}"
  echo "     export CF_ACCESS_CLIENT_SECRET=<secret>"
  echo "  4. Add to VPS ~/.env.hegemon (same vars)"
  echo "  5. Test: curl -H 'CF-Access-Client-Id: ${TOKEN_CLIENT_ID}' -H 'CF-Access-Client-Secret: <secret>' https://vault.gostoa.dev/api/status"
else
  echo -e "${YELLOW}Service token already exists. Use --status to check.${NC}"
  echo -e "To rotate: delete the token in Cloudflare dashboard, then re-run this script."
fi

echo ""
echo -e "${BOLD}Verification:${NC}"
echo "  $0 --status"
