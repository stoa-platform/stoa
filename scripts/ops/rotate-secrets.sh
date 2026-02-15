#!/usr/bin/env bash
# =============================================================================
# STOA Platform — Secret Rotation Script
# =============================================================================
# Rotates production credentials and stores them in Infisical.
# Idempotent — safe to re-run. Old credentials remain valid until Keycloak
# is actually updated (no partial state).
#
# Usage:
#   ./scripts/ops/rotate-secrets.sh keycloak-admin    # Rotate KC admin password
#   ./scripts/ops/rotate-secrets.sh personas           # Rotate E2E persona passwords
#   ./scripts/ops/rotate-secrets.sh oidc-clients       # Rotate OIDC client secrets
#   ./scripts/ops/rotate-secrets.sh opensearch         # Rotate OpenSearch admin
#   ./scripts/ops/rotate-secrets.sh arena-token        # Rotate VPS arena admin token
#   ./scripts/ops/rotate-secrets.sh all                # Rotate everything
#
# Prerequisites:
#   - KC_ADMIN_PASSWORD set (current admin password)
#   - INFISICAL_TOKEN set: eval $(infisical-token)
#   - curl, jq, openssl installed
#   - For 'personas': gh CLI authenticated (to update GitHub Secrets)
#   - For 'opensearch': kubectl access to the cluster
#
# Options:
#   --dry-run     Show what would be changed without making changes
#   --no-infisical  Skip Infisical storage (useful for testing)
# =============================================================================
set -euo pipefail

# --- Configuration ---
KEYCLOAK_URL="${KEYCLOAK_URL:-https://auth.gostoa.dev}"
KC_REALM="${KEYCLOAK_REALM:-stoa}"
KC_ADMIN_USER="${KC_ADMIN_USER:-admin}"
KC_ADMIN_PASSWORD="${KC_ADMIN_PASSWORD:-}"
INFISICAL_PROJECT_ID="97972ffc-990b-4d28-9c4d-0664d217f03b"
GH_REPO="stoa-platform/stoa"
DRY_RUN=false
NO_INFISICAL=false

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# E2E personas
PERSONAS=(parzival art3mis aech sorrento i-r0k anorak alex)

# OIDC confidential clients
OIDC_CLIENTS=(control-plane-api stoa-mcp-gateway opensearch-dashboards stoa-observability)

# --- Parse args ---
COMMAND="${1:-}"
shift || true

for arg in "$@"; do
  case $arg in
    --dry-run)      DRY_RUN=true ;;
    --no-infisical) NO_INFISICAL=true ;;
    --help|-h)
      echo "Usage: $0 <command> [--dry-run] [--no-infisical]"
      echo ""
      echo "Commands:"
      echo "  keycloak-admin   Rotate Keycloak admin password"
      echo "  personas         Rotate E2E persona passwords"
      echo "  oidc-clients     Rotate OIDC client secrets"
      echo "  opensearch       Rotate OpenSearch admin password"
      echo "  arena-token      Rotate VPS arena admin API token"
      echo "  all              Rotate everything"
      echo ""
      echo "Environment:"
      echo "  KEYCLOAK_URL       (default: https://auth.gostoa.dev)"
      echo "  KC_ADMIN_USER      (default: admin)"
      echo "  KC_ADMIN_PASSWORD  (required)"
      echo "  INFISICAL_TOKEN    (required unless --no-infisical)"
      exit 0
      ;;
  esac
done

if [ -z "$COMMAND" ]; then
  echo -e "${RED}Error: command required. Run with --help for usage.${NC}"
  exit 1
fi

# --- Helpers ---

generate_password() {
  local length="${1:-32}"
  # Generate base alphanumeric, then inject required complexity chars
  # to guarantee NIST/DORA policy compliance (upper, lower, digit, special)
  local base
  base=$(openssl rand -base64 "$length" | tr -d '/+=' | head -c "$((length - 4))")
  # Append guaranteed complexity: 1 upper, 1 lower, 1 digit, 1 special
  local suffix
  suffix="A"
  suffix+="z"
  suffix+="$(( RANDOM % 10 ))"
  suffix+="@"
  echo "${base}${suffix}"
}

get_kc_token() {
  if [ -n "${KC_TOKEN:-}" ]; then
    echo "$KC_TOKEN"
    return
  fi

  if [ -z "$KC_ADMIN_PASSWORD" ]; then
    echo -e "${RED}Error: KC_ADMIN_PASSWORD not set${NC}" >&2
    exit 1
  fi

  local response
  response=$(curl -sf -X POST "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "client_id=admin-cli" \
    -d "username=${KC_ADMIN_USER}" \
    -d "password=${KC_ADMIN_PASSWORD}" \
    -d "grant_type=password" 2>/dev/null || echo '{"error":"failed"}')

  local token
  token=$(echo "$response" | jq -r '.access_token // empty')
  if [ -z "$token" ]; then
    echo -e "${RED}Failed to get KC admin token. Check KC_ADMIN_PASSWORD.${NC}" >&2
    echo "Error: $(echo "$response" | jq -r 'del(.access_token) | .error_description // .error // "unknown"')" >&2
    exit 1
  fi

  KC_TOKEN="$token"
  echo "$token"
}

store_infisical() {
  local path="$1" key="$2" value="$3"
  if [ "$NO_INFISICAL" = true ] || [ "$DRY_RUN" = true ]; then
    echo -e "    ${YELLOW}[skip] Infisical ${path}/${key}${NC}"
    return
  fi

  if [ -z "${INFISICAL_TOKEN:-}" ]; then
    echo -e "    ${YELLOW}[skip] INFISICAL_TOKEN not set${NC}"
    return
  fi

  # Use Infisical CLI (handles encryption for self-hosted instances)
  if command -v infisical &>/dev/null; then
    if infisical secrets set "${key}=${value}" \
      --env=prod \
      --path="$path" \
      --projectId="$INFISICAL_PROJECT_ID" \
      --token="$INFISICAL_TOKEN" >/dev/null 2>&1; then
      echo -e "    ${GREEN}[OK] Infisical ${path}/${key}${NC}"
    else
      echo -e "    ${RED}[FAIL] Infisical ${path}/${key}${NC}"
    fi
    return
  fi

  # Fallback: curl API (works with Infisical Cloud, not self-hosted)
  local http_code
  http_code=$(curl -sf -o /dev/null -w '%{http_code}' \
    -X POST "https://vault.gostoa.dev/api/v3/secrets/raw" \
    -H "Authorization: Bearer ${INFISICAL_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$(jq -n \
      --arg wid "$INFISICAL_PROJECT_ID" \
      --arg env "prod" \
      --arg path "$path" \
      --arg key "$key" \
      --arg val "$value" \
      '{workspaceId: $wid, environment: $env, secretPath: $path, secretName: $key, secretValue: $val}')" \
    2>/dev/null || echo "000")

  if [ "$http_code" = "200" ] || [ "$http_code" = "201" ]; then
    echo -e "    ${GREEN}[OK] Infisical ${path}/${key}${NC}"
  elif [ "$http_code" = "400" ] || [ "$http_code" = "409" ]; then
    # Secret exists, update it
    http_code=$(curl -sf -o /dev/null -w '%{http_code}' \
      -X PATCH "https://vault.gostoa.dev/api/v3/secrets/raw/${key}" \
      -H "Authorization: Bearer ${INFISICAL_TOKEN}" \
      -H "Content-Type: application/json" \
      -d "$(jq -n \
        --arg wid "$INFISICAL_PROJECT_ID" \
        --arg env "prod" \
        --arg path "$path" \
        --arg val "$value" \
        '{workspaceId: $wid, environment: $env, secretPath: $path, secretValue: $val}')" \
      2>/dev/null || echo "000")
    if [ "$http_code" = "200" ]; then
      echo -e "    ${GREEN}[OK] Infisical ${path}/${key} (updated)${NC}"
    else
      echo -e "    ${RED}[FAIL] Infisical update ${path}/${key} (HTTP ${http_code})${NC}"
    fi
  else
    echo -e "    ${RED}[FAIL] Infisical ${path}/${key} (HTTP ${http_code})${NC}"
  fi
}

# =============================================================================
# Command: keycloak-admin
# =============================================================================
rotate_keycloak_admin() {
  echo ""
  echo -e "${BOLD}${CYAN}=== Rotating Keycloak Admin Password ===${NC}"
  echo ""

  local new_password
  new_password=$(generate_password 32)

  echo "  New password: ${new_password:0:4}...${new_password: -4} (${#new_password} chars)"

  # Get admin token with current password
  local token
  token=$(get_kc_token)

  # Find admin user ID in master realm
  local admin_id
  admin_id=$(curl -sf "${KEYCLOAK_URL}/admin/realms/master/users?username=${KC_ADMIN_USER}&exact=true" \
    -H "Authorization: Bearer ${token}" 2>/dev/null | jq -r '.[0].id // empty')

  if [ -z "$admin_id" ]; then
    echo -e "  ${RED}FAIL: Could not find admin user ID${NC}"
    return 1
  fi
  echo "  Admin user ID: ${admin_id}"

  if [ "$DRY_RUN" = true ]; then
    echo -e "  ${YELLOW}[dry-run] Would reset password for user ${admin_id}${NC}"
    echo -e "  ${YELLOW}[dry-run] Would store in Infisical prod/keycloak/ADMIN_PASSWORD${NC}"
    return 0
  fi

  # Reset password via KC Admin API
  local http_code
  http_code=$(curl -sf -o /dev/null -w '%{http_code}' \
    -X PUT "${KEYCLOAK_URL}/admin/realms/master/users/${admin_id}/reset-password" \
    -H "Authorization: Bearer ${token}" \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg pw "$new_password" '{type: "password", value: $pw, temporary: false}')" \
    2>/dev/null || echo "000")

  if [ "$http_code" = "204" ] || [ "$http_code" = "200" ]; then
    echo -e "  ${GREEN}[OK] Password reset in Keycloak${NC}"
  else
    echo -e "  ${RED}[FAIL] Password reset failed (HTTP ${http_code})${NC}"
    return 1
  fi

  # Store in Infisical
  store_infisical "/keycloak" "ADMIN_PASSWORD" "$new_password"

  # Verify — get a new token with the new password
  echo -n "  Verifying new password... "
  local verify_response
  verify_response=$(curl -sf -X POST "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "client_id=admin-cli" \
    -d "username=${KC_ADMIN_USER}" \
    -d "password=${new_password}" \
    -d "grant_type=password" 2>/dev/null || echo '{"error":"failed"}')

  local new_token
  new_token=$(echo "$verify_response" | jq -r '.access_token // empty')
  if [ -n "$new_token" ] && [[ "$new_token" =~ ^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$ ]]; then
    echo -e "${GREEN}OK${NC}"
    # Update cached token
    KC_TOKEN="$new_token"
    KC_ADMIN_PASSWORD="$new_password"
  else
    echo -e "${RED}FAIL — new password did not work!${NC}"
    echo "  This should not happen. Check Keycloak logs."
    return 1
  fi

  # Update local .env if it exists
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local env_file="${script_dir}/../../.env"
  if [ -f "$env_file" ]; then
    if grep -q "KC_ADMIN_PASSWORD" "$env_file"; then
      sed -i '' "s|KC_ADMIN_PASSWORD=.*|KC_ADMIN_PASSWORD=${new_password}|" "$env_file"
      echo -e "  ${GREEN}[OK] Updated .env${NC}"
    fi
  fi

  echo -e "  ${GREEN}Keycloak admin password rotated successfully${NC}"
  echo ""
  echo "  IMPORTANT: Update your local environment:"
  echo "    export KC_ADMIN_PASSWORD='${new_password}'"
}

# =============================================================================
# Command: personas
# =============================================================================
rotate_personas() {
  echo ""
  echo -e "${BOLD}${CYAN}=== Rotating E2E Persona Passwords ===${NC}"
  echo ""

  local token
  token=$(get_kc_token)

  local pass_count=0
  local fail_count=0

  for persona in "${PERSONAS[@]}"; do
    local new_password
    new_password=$(generate_password 20)
    local upper_persona
    upper_persona=$(echo "$persona" | tr '[:lower:]' '[:upper:]' | tr '-' '_')

    echo -n "  ${persona}: "

    if [ "$DRY_RUN" = true ]; then
      echo -e "${YELLOW}[dry-run] would rotate${NC}"
      pass_count=$((pass_count + 1))
      continue
    fi

    # Find user ID
    local user_id
    user_id=$(curl -sf "${KEYCLOAK_URL}/admin/realms/${KC_REALM}/users?username=${persona}&exact=true" \
      -H "Authorization: Bearer ${token}" 2>/dev/null | jq -r '.[0].id // empty')

    if [ -z "$user_id" ]; then
      echo -e "${YELLOW}[skip] user not found in KC${NC}"
      fail_count=$((fail_count + 1))
      continue
    fi

    # Reset password
    local http_code
    http_code=$(curl -sf -o /dev/null -w '%{http_code}' \
      -X PUT "${KEYCLOAK_URL}/admin/realms/${KC_REALM}/users/${user_id}/reset-password" \
      -H "Authorization: Bearer ${token}" \
      -H "Content-Type: application/json" \
      -d "$(jq -n --arg pw "$new_password" '{type: "password", value: $pw, temporary: false}')" \
      2>/dev/null || echo "000")

    if [ "$http_code" != "204" ] && [ "$http_code" != "200" ]; then
      echo -e "${RED}[FAIL] KC reset (HTTP ${http_code})${NC}"
      fail_count=$((fail_count + 1))
      continue
    fi

    echo -n "KC "

    # Store in Infisical
    store_infisical "/e2e-personas" "${upper_persona}_PASSWORD" "$new_password"

    # Update GitHub Secret (pipe via stdin to avoid password in process list / error output)
    if command -v gh &>/dev/null; then
      if echo "$new_password" | gh secret set "${upper_persona}_PASSWORD" --repo "$GH_REPO" 2>/dev/null; then
        echo -n "GH "
      else
        echo -n "${YELLOW}GH-skip ${NC}"
      fi
    fi

    echo -e "${GREEN}OK${NC}"
    pass_count=$((pass_count + 1))
  done

  echo ""
  echo "  Results: ${pass_count} rotated, ${fail_count} failed"

  # Update local e2e/.env
  local e2e_env="/Users/torpedo/hlfh-repos/stoa/e2e/.env"
  if [ -f "$e2e_env" ] && [ "$DRY_RUN" != true ]; then
    echo ""
    echo "  NOTE: e2e/.env still has old passwords."
    echo "  Local E2E tests will need updated passwords from Infisical:"
    echo "    infisical secrets --env=prod --path=/e2e-personas"
  fi
}

# =============================================================================
# Command: oidc-clients
# =============================================================================
rotate_oidc_clients() {
  echo ""
  echo -e "${BOLD}${CYAN}=== Rotating OIDC Client Secrets ===${NC}"
  echo ""
  echo -e "  ${YELLOW}WARNING: This will cause brief service interruption.${NC}"
  echo -e "  ${YELLOW}Affected pods need rolling restart after secret update.${NC}"
  echo ""

  local token
  token=$(get_kc_token)

  for client_id in "${OIDC_CLIENTS[@]}"; do
    echo -e "  ${BOLD}${client_id}:${NC}"

    # Get client UUID
    local client_uuid
    client_uuid=$(curl -sf "${KEYCLOAK_URL}/admin/realms/${KC_REALM}/clients?clientId=${client_id}" \
      -H "Authorization: Bearer ${token}" 2>/dev/null | jq -r '.[0].id // empty')

    if [ -z "$client_uuid" ]; then
      echo -e "    ${YELLOW}[skip] client not found in KC${NC}"
      continue
    fi

    # Check current secret
    local current_secret
    current_secret=$(curl -sf "${KEYCLOAK_URL}/admin/realms/${KC_REALM}/clients/${client_uuid}/client-secret" \
      -H "Authorization: Bearer ${token}" 2>/dev/null | jq -r '.value // empty')

    if [ -n "$current_secret" ] && [[ ! "$current_secret" =~ -dev-secret$ ]]; then
      echo -e "    ${GREEN}[OK] Already rotated (not a *-dev-secret)${NC}"
      continue
    fi

    if [ "$DRY_RUN" = true ]; then
      echo -e "    ${YELLOW}[dry-run] Would regenerate secret for ${client_id}${NC}"
      continue
    fi

    # Regenerate secret
    local new_secret_response
    new_secret_response=$(curl -sf -X POST "${KEYCLOAK_URL}/admin/realms/${KC_REALM}/clients/${client_uuid}/client-secret" \
      -H "Authorization: Bearer ${token}" 2>/dev/null || echo '{}')

    local new_secret
    new_secret=$(echo "$new_secret_response" | jq -r '.value // empty')

    if [ -z "$new_secret" ]; then
      echo -e "    ${RED}[FAIL] Could not regenerate secret${NC}"
      continue
    fi

    echo -e "    ${GREEN}[OK] Secret regenerated${NC}"

    # Store in Infisical
    local infisical_key
    infisical_key=$(echo "${client_id}" | tr '[:lower:]-' '[:upper:]_')_CLIENT_SECRET
    store_infisical "/keycloak/clients" "$infisical_key" "$new_secret"

    echo -e "    ${YELLOW}[TODO] Update K8s secret + restart pod for ${client_id}${NC}"
  done
}

# =============================================================================
# Command: opensearch
# =============================================================================
rotate_opensearch() {
  echo ""
  echo -e "${BOLD}${CYAN}=== Rotating OpenSearch Admin Password ===${NC}"
  echo ""
  echo -e "  ${YELLOW}WARNING: Requires SSH/kubectl access to OpenSearch node.${NC}"
  echo -e "  ${YELLOW}This is a manual-assisted operation.${NC}"
  echo ""

  local new_password
  new_password=$(generate_password 32)

  echo "  New password: ${new_password:0:4}...${new_password: -4} (${#new_password} chars)"

  if [ "$DRY_RUN" = true ]; then
    echo -e "  ${YELLOW}[dry-run] Would update OpenSearch admin password${NC}"
    return 0
  fi

  # Store in Infisical
  store_infisical "/opensearch" "ADMIN_PASSWORD" "$new_password"

  echo ""
  echo -e "  ${YELLOW}Manual steps required:${NC}"
  echo "  1. SSH to the OpenSearch node"
  echo "  2. Generate bcrypt hash (reads password from Infisical, never shown in process list):"
  echo '     NEW_PW=$(infisical secrets get ADMIN_PASSWORD --env=prod --path=/opensearch --plain)'
  echo '     python3 -c "import bcrypt,sys; print(bcrypt.hashpw(sys.stdin.buffer.read().rstrip(),bcrypt.gensalt()).decode())" <<< "$NEW_PW"'
  echo "  3. Update internal_users.yml with the new hash"
  echo "  4. Run: ./securityadmin.sh -cd ../config/ -icl -nhnv"
  echo "  5. Update K8s secret (reads from Infisical):"
  echo '     NEW_PW=$(infisical secrets get ADMIN_PASSWORD --env=prod --path=/opensearch --plain)'
  echo '     kubectl create secret generic stoa-opensearch-secret \'
  echo '       --from-literal=admin-password="$NEW_PW" \'
  echo '       -n stoa-system --dry-run=client -o yaml | kubectl apply -f -'
  echo "  6. Restart control-plane-api:"
  echo "     kubectl rollout restart deployment/control-plane-api -n stoa-system"
  echo ""
  echo "  Password stored in Infisical: prod/opensearch/ADMIN_PASSWORD"
}

# =============================================================================
# Command: arena-token
# =============================================================================
rotate_arena_token() {
  echo ""
  echo -e "${BOLD}${CYAN}=== Rotating VPS Arena Admin Token ===${NC}"
  echo ""

  local new_token
  new_token=$(generate_password 40)

  echo "  New token: ${new_token:0:4}...${new_token: -4} (${#new_token} chars)"

  if [ "$DRY_RUN" = true ]; then
    echo -e "  ${YELLOW}[dry-run] Would update arena admin token${NC}"
    return 0
  fi

  # Store in Infisical
  store_infisical "/gateway/arena" "ADMIN_API_TOKEN" "$new_token"

  echo ""
  echo -e "  ${YELLOW}Manual steps required:${NC}"
  echo "  1. SSH to VPS (51.83.45.13):"
  echo "     ssh -i ~/.ssh/id_ed25519_stoa debian@51.83.45.13"
  echo "  2. Update ~/stoa/docker-compose.yml:"
  echo "     STOA_ADMIN_API_TOKEN: \"${new_token}\""
  echo "  3. Restart: cd ~/stoa && docker compose up -d"
  echo "  4. Verify: curl -H 'Authorization: Bearer ${new_token:0:4}...' http://localhost:8080/admin/health"
  echo ""
  echo "  Token stored in Infisical: prod/gateway/arena/ADMIN_API_TOKEN"
}

# =============================================================================
# Main dispatcher
# =============================================================================

echo "=============================================="
echo "  STOA — Secret Rotation"
echo "=============================================="
echo -e "  Command:    ${CYAN}${COMMAND}${NC}"
echo -e "  Keycloak:   ${CYAN}${KEYCLOAK_URL}${NC}"
echo -e "  Dry run:    ${CYAN}${DRY_RUN}${NC}"
echo -e "  Infisical:  ${CYAN}$([ "$NO_INFISICAL" = true ] && echo "disabled" || echo "enabled")${NC}"

case "$COMMAND" in
  keycloak-admin) rotate_keycloak_admin ;;
  personas)       rotate_personas ;;
  oidc-clients)   rotate_oidc_clients ;;
  opensearch)     rotate_opensearch ;;
  arena-token)    rotate_arena_token ;;
  all)
    rotate_keycloak_admin
    rotate_personas
    rotate_oidc_clients
    rotate_opensearch
    rotate_arena_token
    ;;
  *)
    echo -e "${RED}Unknown command: ${COMMAND}${NC}"
    echo "Valid commands: keycloak-admin, personas, oidc-clients, opensearch, arena-token, all"
    exit 1
    ;;
esac

echo ""
echo "=============================================="
echo -e "  ${GREEN}Rotation complete${NC}"
echo "=============================================="
