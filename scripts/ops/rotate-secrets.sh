#!/usr/bin/env bash
# =============================================================================
# STOA Platform — Secret Rotation Script
# =============================================================================
# Rotates production credentials and stores them in Vault (primary) and
# Infisical (legacy, during transition). Idempotent — safe to re-run.
# Old credentials remain valid until the service is actually updated.
#
# Usage:
#   ./scripts/ops/rotate-secrets.sh keycloak-admin    # Rotate KC admin password
#   ./scripts/ops/rotate-secrets.sh personas           # Rotate E2E persona passwords
#   ./scripts/ops/rotate-secrets.sh oidc-clients       # Rotate OIDC client secrets
#   ./scripts/ops/rotate-secrets.sh opensearch         # Rotate OpenSearch admin
#   ./scripts/ops/rotate-secrets.sh arena-token        # Rotate VPS arena admin token
#   ./scripts/ops/rotate-secrets.sh webmethods-admin   # Rotate webMethods admin via KC
#   ./scripts/ops/rotate-secrets.sh kong-admin         # Rotate Kong admin token
#   ./scripts/ops/rotate-secrets.sh gravitee-admin     # Rotate Gravitee admin password
#   ./scripts/ops/rotate-secrets.sh n8n-db             # Rotate n8n PostgreSQL password
#   ./scripts/ops/rotate-secrets.sh all-vps            # Rotate all VPS service secrets
#   ./scripts/ops/rotate-secrets.sh all                # Rotate everything (KC + VPS)
#
# Prerequisites:
#   - KC_ADMIN_PASSWORD set (current admin password)
#   - VAULT_TOKEN set (Vault admin token) — or VAULT_ADDR + auto-auth
#   - INFISICAL_TOKEN set: eval $(infisical-token) — optional, for dual-write
#   - curl, jq, openssl installed
#   - For 'personas': gh CLI authenticated (to update GitHub Secrets)
#   - For 'opensearch': kubectl access to the cluster
#
# Options:
#   --dry-run       Show what would be changed without making changes
#   --no-infisical  Skip Infisical storage
#   --no-vault      Skip Vault storage
# =============================================================================
set -euo pipefail

# --- Configuration ---
KEYCLOAK_URL="${KEYCLOAK_URL:-https://auth.gostoa.dev}"
KC_REALM="${KEYCLOAK_REALM:-stoa}"
KC_ADMIN_USER="${KC_ADMIN_USER:-admin}"
KC_ADMIN_PASSWORD="${KC_ADMIN_PASSWORD:-}"
INFISICAL_PROJECT_ID="97972ffc-990b-4d28-9c4d-0664d217f03b"
INFISICAL_URL="${INFISICAL_URL:-https://vault.gostoa.dev}"
GH_REPO="stoa-platform/stoa"

# Vault configuration (primary secrets backend)
VAULT_ADDR="${VAULT_ADDR:-https://hcvault.gostoa.dev}"
VAULT_TOKEN="${VAULT_TOKEN:-}"

# VPS SSH configuration
VPS_SSH_KEY="${VPS_SSH_KEY:-$HOME/.ssh/id_ed25519_stoa}"
VPS_SSH_USER="${VPS_SSH_USER:-debian}"

# VPS hosts
VPS_N8N="51.254.139.205"
VPS_KONG="51.83.45.13"
VPS_GRAVITEE="54.36.209.237"
VPS_WEBMETHODS="51.255.201.17"

# Cloudflare Access headers (empty = no CF Access, backward compatible)
CF_ACCESS_CLIENT_ID="${CF_ACCESS_CLIENT_ID:-}"
CF_ACCESS_CLIENT_SECRET="${CF_ACCESS_CLIENT_SECRET:-}"
DRY_RUN=false
NO_INFISICAL=false
NO_VAULT=false

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
OIDC_CLIENTS=(control-plane-api stoa-gateway opensearch-dashboards stoa-observability)

# --- Parse args ---
COMMAND="${1:-}"
shift || true

for arg in "$@"; do
  case $arg in
    --dry-run)      DRY_RUN=true ;;
    --no-infisical) NO_INFISICAL=true ;;
    --no-vault)     NO_VAULT=true ;;
  esac
done

if [ -z "$COMMAND" ] || [ "$COMMAND" = "--help" ] || [ "$COMMAND" = "-h" ]; then
  echo "Usage: $0 <command> [--dry-run] [--no-infisical] [--no-vault]"
  echo ""
  echo "Commands (Keycloak + K8s):"
  echo "  keycloak-admin     Rotate Keycloak admin password"
  echo "  personas           Rotate E2E persona passwords"
  echo "  oidc-clients       Rotate OIDC client secrets"
  echo "  opensearch         Rotate OpenSearch admin password"
  echo "  arena-token        Rotate VPS arena admin API token"
  echo "  all                Rotate everything (KC + VPS)"
  echo ""
  echo "Commands (VPS services):"
  echo "  webmethods-admin   Rotate webMethods admin password via Keycloak"
  echo "  kong-admin         Rotate Kong admin API token"
  echo "  gravitee-admin     Rotate Gravitee admin password"
  echo "  n8n-db             Rotate n8n PostgreSQL password"
  echo "  all-vps            Rotate all VPS service secrets"
  echo ""
  echo "Environment:"
  echo "  VAULT_ADDR         (default: https://hcvault.gostoa.dev)"
  echo "  VAULT_TOKEN        (required unless --no-vault)"
  echo "  KEYCLOAK_URL       (default: https://auth.gostoa.dev)"
  echo "  KC_ADMIN_PASSWORD  (required for KC commands)"
  echo "  INFISICAL_TOKEN    (optional, for dual-write to Infisical)"
  exit 0
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

  # Fallback: curl API (works with Infisical Cloud and self-hosted)
  # Build CF Access headers if configured
  local -a cf_headers=()
  if [ -n "$CF_ACCESS_CLIENT_ID" ] && [ -n "$CF_ACCESS_CLIENT_SECRET" ]; then
    cf_headers+=(-H "CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}")
    cf_headers+=(-H "CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}")
  fi

  local http_code
  http_code=$(curl -sf -o /dev/null -w '%{http_code}' \
    -X POST "${INFISICAL_URL}/api/v3/secrets/raw" \
    -H "Authorization: Bearer ${INFISICAL_TOKEN}" \
    -H "Content-Type: application/json" \
    "${cf_headers[@]}" \
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
      -X PATCH "${INFISICAL_URL}/api/v3/secrets/raw/${key}" \
      -H "Authorization: Bearer ${INFISICAL_TOKEN}" \
      -H "Content-Type: application/json" \
      "${cf_headers[@]}" \
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

store_vault() {
  local vault_path="$1" key="$2" value="$3"
  if [ "$NO_VAULT" = true ] || [ "$DRY_RUN" = true ]; then
    echo -e "    ${YELLOW}[skip] Vault stoa/${vault_path} → ${key}${NC}"
    return
  fi

  if [ -z "${VAULT_TOKEN:-}" ]; then
    echo -e "    ${YELLOW}[skip] VAULT_TOKEN not set${NC}"
    return
  fi

  # Read existing secret data (Vault KV v2 is a single JSON object per path)
  local existing
  existing=$(curl -sf "${VAULT_ADDR}/v1/stoa/data/${vault_path}" \
    -H "X-Vault-Token: ${VAULT_TOKEN}" 2>/dev/null \
    | jq -r '.data.data // {}' 2>/dev/null || echo '{}')

  # Merge new key into existing data
  local merged
  merged=$(echo "$existing" | jq --arg k "$key" --arg v "$value" '. + {($k): $v}')

  # Write merged data back
  local http_code
  http_code=$(curl -sf -o /dev/null -w '%{http_code}' \
    -X POST "${VAULT_ADDR}/v1/stoa/data/${vault_path}" \
    -H "X-Vault-Token: ${VAULT_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$(jq -n --argjson data "$merged" '{data: $data}')" \
    2>/dev/null || echo "000")

  if [ "$http_code" = "200" ] || [ "$http_code" = "204" ]; then
    echo -e "    ${GREEN}[OK] Vault stoa/${vault_path}/${key}${NC}"
  else
    echo -e "    ${RED}[FAIL] Vault stoa/${vault_path}/${key} (HTTP ${http_code})${NC}"
  fi
}

store_secret() {
  # Convenience wrapper: writes to both Vault (primary) and Infisical (legacy)
  local vault_path="$1" infisical_path="$2" key="$3" value="$4"
  store_vault "$vault_path" "$key" "$value"
  store_infisical "$infisical_path" "$key" "$value"
}

vps_ssh() {
  # Execute a command on a VPS via SSH
  local host="$1"
  shift
  ssh -i "$VPS_SSH_KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 \
    "${VPS_SSH_USER}@${host}" "$@"
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

  # Store in Vault (primary) + Infisical (legacy)
  store_secret "shared/keycloak" "/keycloak" "ADMIN_PASSWORD" "$new_password"

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

    # Store in Vault (primary) + Infisical (legacy)
    store_secret "k8s/e2e-personas" "/e2e-personas" "${upper_persona}_PASSWORD" "$new_password"

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

    # Store in Vault (primary) + Infisical (legacy)
    local infisical_key
    infisical_key=$(echo "${client_id}" | tr '[:lower:]-' '[:upper:]_')_CLIENT_SECRET
    store_secret "shared/keycloak/clients" "/keycloak/clients" "$infisical_key" "$new_secret"

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

  # Store in Vault (primary) + Infisical (legacy)
  store_secret "k8s/opensearch" "/opensearch" "ADMIN_PASSWORD" "$new_password"

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

  # Store in Vault (primary) + Infisical (legacy)
  store_secret "vps/arena" "/gateway/arena" "ADMIN_API_TOKEN" "$new_token"

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
# Command: webmethods-admin
# =============================================================================
rotate_webmethods_admin() {
  echo ""
  echo -e "${BOLD}${CYAN}=== Rotating webMethods Admin Password ===${NC}"
  echo ""

  local new_password
  new_password=$(generate_password 32)

  echo "  New password: ${new_password:0:4}...${new_password: -4} (${#new_password} chars)"
  echo "  VPS: ${VPS_WEBMETHODS}"

  if [ "$DRY_RUN" = true ]; then
    echo -e "  ${YELLOW}[dry-run] Would update webMethods admin password${NC}"
    echo -e "  ${YELLOW}[dry-run] Would store in Vault vps/webmethods/ADMIN_PASSWORD${NC}"
    return 0
  fi

  # Store in Vault + Infisical
  store_secret "vps/webmethods" "/vps/webmethods" "ADMIN_PASSWORD" "$new_password"

  echo ""
  echo -e "  ${YELLOW}Vault Agent will auto-update /opt/secrets/webmethods.env within 5 min.${NC}"
  echo -e "  ${YELLOW}If Vault Agent is not yet deployed, manual steps:${NC}"
  echo "  1. SSH: ssh -i ${VPS_SSH_KEY} ${VPS_SSH_USER}@${VPS_WEBMETHODS}"
  echo "  2. Update .env: sed -i 's/ADMIN_PASSWORD=.*/ADMIN_PASSWORD=${new_password}/' /opt/webmethods/.env"
  echo "  3. Restart: cd /opt/webmethods && docker compose restart"
  echo ""
  echo -n "  Verifying webMethods is reachable... "
  if curl -sf -o /dev/null -w '' "http://${VPS_WEBMETHODS}:5555/rest/apigateway/health" 2>/dev/null; then
    echo -e "${GREEN}OK${NC}"
  else
    echo -e "${YELLOW}unreachable (may need VPN or port is firewalled)${NC}"
  fi
}

# =============================================================================
# Command: kong-admin
# =============================================================================
rotate_kong_admin() {
  echo ""
  echo -e "${BOLD}${CYAN}=== Rotating Kong Admin Token ===${NC}"
  echo ""

  local new_token
  new_token=$(generate_password 40)

  echo "  New token: ${new_token:0:4}...${new_token: -4} (${#new_token} chars)"
  echo "  VPS: ${VPS_KONG}"

  if [ "$DRY_RUN" = true ]; then
    echo -e "  ${YELLOW}[dry-run] Would update Kong admin token${NC}"
    echo -e "  ${YELLOW}[dry-run] Would store in Vault vps/kong/KONG_ADMIN_TOKEN${NC}"
    return 0
  fi

  # Store in Vault + Infisical
  store_secret "vps/kong" "/vps/kong" "KONG_ADMIN_TOKEN" "$new_token"

  echo ""
  echo -e "  ${YELLOW}Vault Agent will auto-update /opt/secrets/kong.env within 5 min.${NC}"
  echo -e "  ${YELLOW}If Vault Agent is not yet deployed, manual steps:${NC}"
  echo "  1. SSH: ssh -i ${VPS_SSH_KEY} ${VPS_SSH_USER}@${VPS_KONG}"
  echo "  2. Update: sed -i 's/KONG_ADMIN_TOKEN=.*/KONG_ADMIN_TOKEN=${new_token}/' ~/kong/.env"
  echo "  3. Restart: cd ~/kong && docker compose restart"
  echo ""
  echo -n "  Verifying Kong admin API... "
  if curl -sf -o /dev/null "http://${VPS_KONG}:8001/status" 2>/dev/null; then
    echo -e "${GREEN}OK${NC}"
  else
    echo -e "${YELLOW}unreachable${NC}"
  fi
}

# =============================================================================
# Command: gravitee-admin
# =============================================================================
rotate_gravitee_admin() {
  echo ""
  echo -e "${BOLD}${CYAN}=== Rotating Gravitee Admin Password ===${NC}"
  echo ""

  local new_password
  new_password=$(generate_password 32)

  echo "  New password: ${new_password:0:4}...${new_password: -4} (${#new_password} chars)"
  echo "  VPS: ${VPS_GRAVITEE}"

  if [ "$DRY_RUN" = true ]; then
    echo -e "  ${YELLOW}[dry-run] Would update Gravitee admin password${NC}"
    echo -e "  ${YELLOW}[dry-run] Would store in Vault vps/gravitee/ADMIN_PASSWORD${NC}"
    return 0
  fi

  # Store in Vault + Infisical
  store_secret "vps/gravitee" "/vps/gravitee" "ADMIN_PASSWORD" "$new_password"

  echo ""
  echo -e "  ${YELLOW}Vault Agent will auto-update /opt/secrets/gravitee.env within 5 min.${NC}"
  echo -e "  ${YELLOW}If Vault Agent is not yet deployed, manual steps:${NC}"
  echo "  1. SSH: ssh -i ${VPS_SSH_KEY} ${VPS_SSH_USER}@${VPS_GRAVITEE}"
  echo "  2. Update .env with new ADMIN_PASSWORD"
  echo "  3. Restart: cd ~/gravitee && docker compose restart"
  echo ""
  echo -n "  Verifying Gravitee management API... "
  if curl -sf -o /dev/null "http://${VPS_GRAVITEE}:8083/management/organizations/DEFAULT/environments/DEFAULT" 2>/dev/null; then
    echo -e "${GREEN}OK${NC}"
  else
    echo -e "${YELLOW}unreachable${NC}"
  fi
}

# =============================================================================
# Command: n8n-db
# =============================================================================
rotate_n8n_db() {
  echo ""
  echo -e "${BOLD}${CYAN}=== Rotating n8n PostgreSQL Password ===${NC}"
  echo ""
  echo -e "  ${YELLOW}WARNING: This will cause brief n8n downtime during Docker restart.${NC}"
  echo ""

  local new_password
  new_password=$(generate_password 32)

  echo "  New password: ${new_password:0:4}...${new_password: -4} (${#new_password} chars)"
  echo "  VPS: ${VPS_N8N}"

  if [ "$DRY_RUN" = true ]; then
    echo -e "  ${YELLOW}[dry-run] Would update n8n PostgreSQL password${NC}"
    echo -e "  ${YELLOW}[dry-run] Would store in Vault vps/n8n/POSTGRES_PASSWORD${NC}"
    return 0
  fi

  # Store in Vault + Infisical
  store_secret "vps/n8n" "/vps/n8n" "POSTGRES_PASSWORD" "$new_password"

  echo ""
  echo -e "  ${YELLOW}Vault Agent will auto-update /opt/secrets/n8n.env within 5 min.${NC}"
  echo -e "  ${YELLOW}If Vault Agent is not yet deployed, manual steps:${NC}"
  echo "  1. SSH: ssh -i ${VPS_SSH_KEY} ${VPS_SSH_USER}@${VPS_N8N}"
  echo "  2. Change PostgreSQL password inside container:"
  echo "     docker exec n8n-postgres psql -U n8n -c \"ALTER USER n8n PASSWORD '${new_password}';\""
  echo "  3. Update .env: sed -i 's/POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=${new_password}/' /opt/n8n/.env"
  echo "  4. Restart: cd /opt/n8n && docker compose down && docker compose up -d"
  echo ""
  echo -n "  Verifying n8n is reachable... "
  if curl -sf -o /dev/null "https://n8n.gostoa.dev/healthz" 2>/dev/null; then
    echo -e "${GREEN}OK${NC}"
  else
    echo -e "${YELLOW}unreachable${NC}"
  fi
}

# =============================================================================
# Command: all-vps
# =============================================================================
rotate_all_vps() {
  echo ""
  echo -e "${BOLD}${CYAN}=== Rotating All VPS Service Secrets ===${NC}"
  echo ""
  rotate_webmethods_admin
  rotate_kong_admin
  rotate_gravitee_admin
  rotate_n8n_db
  rotate_arena_token
}

# =============================================================================
# Main dispatcher
# =============================================================================

echo "=============================================="
echo "  STOA — Secret Rotation"
echo "=============================================="
echo -e "  Command:    ${CYAN}${COMMAND}${NC}"
echo -e "  Keycloak:   ${CYAN}${KEYCLOAK_URL}${NC}"
echo -e "  Vault:      ${CYAN}$([ "$NO_VAULT" = true ] && echo "disabled" || echo "${VAULT_ADDR}")${NC}"
echo -e "  Infisical:  ${CYAN}$([ "$NO_INFISICAL" = true ] && echo "disabled" || echo "enabled (legacy)")${NC}"
echo -e "  Dry run:    ${CYAN}${DRY_RUN}${NC}"

case "$COMMAND" in
  keycloak-admin)   rotate_keycloak_admin ;;
  personas)         rotate_personas ;;
  oidc-clients)     rotate_oidc_clients ;;
  opensearch)       rotate_opensearch ;;
  arena-token)      rotate_arena_token ;;
  webmethods-admin) rotate_webmethods_admin ;;
  kong-admin)       rotate_kong_admin ;;
  gravitee-admin)   rotate_gravitee_admin ;;
  n8n-db)           rotate_n8n_db ;;
  all-vps)          rotate_all_vps ;;
  all)
    rotate_keycloak_admin
    rotate_personas
    rotate_oidc_clients
    rotate_opensearch
    rotate_all_vps
    ;;
  *)
    echo -e "${RED}Unknown command: ${COMMAND}${NC}"
    echo "Valid commands: keycloak-admin, personas, oidc-clients, opensearch, arena-token,"
    echo "               webmethods-admin, kong-admin, gravitee-admin, n8n-db, all-vps, all"
    exit 1
    ;;
esac

echo ""
echo "=============================================="
echo -e "  ${GREEN}Rotation complete${NC}"
echo "=============================================="
