#!/usr/bin/env bash
# =============================================================================
# HEGEMON Workers — Keycloak Service Account Provisioning (CAB-1712)
# =============================================================================
# Creates 5 service accounts for HEGEMON Contabo workers with custom JWT claims.
# Idempotent — safe to re-run. Skips existing clients.
#
# Usage:
#   ./scripts/ops/setup-hegemon-workers.sh
#
# Prerequisites:
#   - KC_ADMIN_PASSWORD set (Keycloak admin password)
#   - INFISICAL_TOKEN set: eval $(infisical-token)
#   - curl, jq installed
#   - Keycloak reachable at KEYCLOAK_URL
#
# Options:
#   --dry-run       Show what would be created without making changes
#   --no-infisical  Skip Infisical storage (useful for testing)
# =============================================================================
set -euo pipefail

# --- Configuration ---
KEYCLOAK_URL="${KEYCLOAK_URL:-https://auth.gostoa.dev}"
KC_REALM="${KEYCLOAK_REALM:-stoa}"
KC_ADMIN_USER="${KC_ADMIN_USER:-admin}"
KC_ADMIN_PASSWORD="${KC_ADMIN_PASSWORD:-}"
INFISICAL_PROJECT_ID="${INFISICAL_PROJECT_ID:-97972ffc-990b-4d28-9c4d-0664d217f03b}"
INFISICAL_URL="${INFISICAL_URL:-https://vault.gostoa.dev}"
TOKEN_TTL_SECONDS=300  # 5 minutes

# Cloudflare Access headers (empty = no CF Access)
CF_ACCESS_CLIENT_ID="${CF_ACCESS_CLIENT_ID:-}"
CF_ACCESS_CLIENT_SECRET="${CF_ACCESS_CLIENT_SECRET:-}"

DRY_RUN=false
NO_INFISICAL=false

# Workers definition: client_id worker_name worker_roles
WORKERS=(
  "hegemon-worker-backend:backend:api,infra,docs"
  "hegemon-worker-frontend:frontend:ui,portal,shared"
  "hegemon-worker-auth:auth:keycloak,iam,oauth"
  "hegemon-worker-mcp:mcp:gateway,rust"
  "hegemon-worker-qa:qa:e2e,test"
)

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# --- Parse args ---
for arg in "$@"; do
  case $arg in
    --dry-run)      DRY_RUN=true ;;
    --no-infisical) NO_INFISICAL=true ;;
    --help|-h)
      sed -n '2,/^set -/p' "$0" | grep '^#' | sed 's/^# \?//'
      exit 0 ;;
    *) echo "Unknown arg: $arg"; exit 1 ;;
  esac
done

# --- Validation ---
if [ -z "$KC_ADMIN_PASSWORD" ]; then
  echo -e "${RED}ERROR: KC_ADMIN_PASSWORD is not set${NC}"
  echo "Get it from: kubectl get secret keycloak -n stoa-system -o jsonpath='{.data.admin-password}' | base64 -d"
  exit 1
fi

if [ "$NO_INFISICAL" = false ] && [ -z "${INFISICAL_TOKEN:-}" ]; then
  echo -e "${RED}ERROR: INFISICAL_TOKEN is not set (use --no-infisical to skip)${NC}"
  echo "Run: eval \$(infisical-token)"
  exit 1
fi

# --- Helpers ---
kc_curl() {
  if [ -n "$CF_ACCESS_CLIENT_ID" ] && [ -n "$CF_ACCESS_CLIENT_SECRET" ]; then
    curl -s -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
         -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" "$@"
  else
    curl -s "$@"
  fi
}

# Add a hardcoded claim mapper to a client (idempotent)
add_claim_mapper() {
  local client_uuid="$1" claim_name="$2" claim_value="$3"
  local mappers_url="${KEYCLOAK_URL}/admin/realms/${KC_REALM}/clients/${client_uuid}/protocol-mappers/models"
  local existing
  existing=$(kc_curl -H "Authorization: Bearer $ADMIN_TOKEN" "$mappers_url" \
    | jq -r ".[] | select(.name==\"${claim_name}\") | .id // empty")
  if [ -n "$existing" ]; then
    echo -e "    ${GREEN}Mapper ${claim_name} already exists${NC}"; return
  fi
  kc_curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
    "$mappers_url" -d "{
      \"name\": \"${claim_name}\", \"protocol\": \"openid-connect\",
      \"protocolMapper\": \"oidc-hardcoded-claim-mapper\",
      \"config\": {
        \"claim.name\": \"${claim_name}\", \"claim.value\": \"${claim_value}\",
        \"jsonType.label\": \"String\", \"id.token.claim\": \"true\",
        \"access.token.claim\": \"true\", \"userinfo.token.claim\": \"true\"
      }
    }" > /dev/null
  echo -e "    ${GREEN}Mapper: ${claim_name}=${claim_value}${NC}"
}

# --- Step 1: Get admin token ---
echo -e "${CYAN}=== HEGEMON Worker Service Accounts ===${NC}"
echo "Keycloak: $KEYCLOAK_URL | Realm: $KC_REALM | TTL: ${TOKEN_TTL_SECONDS}s"
echo ""

echo -e "${CYAN}[1/4] Authenticating to Keycloak...${NC}"
ADMIN_TOKEN=$(kc_curl -X POST "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
  -d "client_id=admin-cli" \
  -d "username=${KC_ADMIN_USER}" \
  -d "password=${KC_ADMIN_PASSWORD}" \
  -d "grant_type=password" | jq -r '.access_token')

if [ -z "$ADMIN_TOKEN" ] || [ "$ADMIN_TOKEN" = "null" ]; then
  echo -e "${RED}ERROR: Failed to authenticate to Keycloak${NC}"
  exit 1
fi
echo -e "${GREEN}  Authenticated${NC}"

# --- Step 2: Create service accounts ---
echo ""
echo -e "${CYAN}[2/4] Creating service accounts...${NC}"

declare -A CLIENT_SECRETS

for entry in "${WORKERS[@]}"; do
  IFS=: read -r client_id worker_name worker_roles <<< "$entry"

  echo -e "  ${YELLOW}${client_id}${NC} (name=${worker_name}, roles=${worker_roles})"

  if [ "$DRY_RUN" = true ]; then
    echo -e "    ${CYAN}[dry-run] Would create client${NC}"
    continue
  fi

  # Check if client already exists
  existing=$(kc_curl -H "Authorization: Bearer $ADMIN_TOKEN" \
    "${KEYCLOAK_URL}/admin/realms/${KC_REALM}/clients?clientId=${client_id}" | jq -r '.[0].id // empty')

  if [ -n "$existing" ]; then
    echo -e "    ${GREEN}Already exists (uuid=${existing})${NC}"
    CLIENT_UUID="$existing"
  else
    # Create the client with service account + short TTL
    CLIENT_UUID=$(kc_curl -X POST \
      -H "Authorization: Bearer $ADMIN_TOKEN" \
      -H "Content-Type: application/json" \
      "${KEYCLOAK_URL}/admin/realms/${KC_REALM}/clients" \
      -d "{
        \"clientId\": \"${client_id}\",
        \"name\": \"HEGEMON Worker: ${worker_name}\",
        \"description\": \"Service account for hegemon-worker-${worker_name} (CAB-1712)\",
        \"enabled\": true,
        \"protocol\": \"openid-connect\",
        \"publicClient\": false,
        \"standardFlowEnabled\": false,
        \"implicitFlowEnabled\": false,
        \"directAccessGrantsEnabled\": false,
        \"serviceAccountsEnabled\": true,
        \"attributes\": {
          \"access.token.lifespan\": \"${TOKEN_TTL_SECONDS}\"
        }
      }" -w '%{header_json}' | jq -r '.location[0] // empty' | grep -oP '[^/]+$')

    # Fallback: fetch by clientId if Location header wasn't captured
    if [ -z "$CLIENT_UUID" ] || [ "$CLIENT_UUID" = "empty" ]; then
      CLIENT_UUID=$(kc_curl -H "Authorization: Bearer $ADMIN_TOKEN" \
        "${KEYCLOAK_URL}/admin/realms/${KC_REALM}/clients?clientId=${client_id}" | jq -r '.[0].id')
    fi
    echo -e "    ${GREEN}Created (uuid=${CLIENT_UUID})${NC}"
  fi

  # Get client secret
  secret=$(kc_curl -H "Authorization: Bearer $ADMIN_TOKEN" \
    "${KEYCLOAK_URL}/admin/realms/${KC_REALM}/clients/${CLIENT_UUID}/client-secret" | jq -r '.value')
  CLIENT_SECRETS["$client_id"]="$secret"

  # Add protocol mappers for custom JWT claims
  add_claim_mapper "$CLIENT_UUID" "worker_name" "$worker_name"
  add_claim_mapper "$CLIENT_UUID" "worker_roles" "$worker_roles"
done

# --- Step 3: Store secrets in Infisical ---
echo ""
echo -e "${CYAN}[3/4] Storing secrets in Infisical...${NC}"

if [ "$DRY_RUN" = true ]; then
  echo -e "  ${CYAN}[dry-run] Would store 5 secrets under /hegemon/workers/${NC}"
elif [ "$NO_INFISICAL" = true ]; then
  echo -e "  ${YELLOW}Skipped (--no-infisical)${NC}"
else
  # Upsert a secret in Infisical (POST, fallback to PATCH for existing)
  infisical_upsert() {
    local secret_name="$1" secret_path="$2" secret_value="$3"
    local body="{\"workspaceId\":\"${INFISICAL_PROJECT_ID}\",\"environment\":\"prod\",\"secretPath\":\"${secret_path}\",\"secretValue\":\"${secret_value}\",\"type\":\"shared\"}"
    kc_curl -X POST -H "Authorization: Bearer $INFISICAL_TOKEN" -H "Content-Type: application/json" \
      "${INFISICAL_URL}/api/v3/secrets/raw/${secret_name}" -d "$body" > /dev/null 2>&1 || \
    kc_curl -X PATCH -H "Authorization: Bearer $INFISICAL_TOKEN" -H "Content-Type: application/json" \
      "${INFISICAL_URL}/api/v3/secrets/raw/${secret_name}" -d "$body" > /dev/null 2>&1 || true
  }

  worker_num=0
  for entry in "${WORKERS[@]}"; do
    IFS=: read -r client_id _ _ <<< "$entry"
    worker_num=$((worker_num + 1))
    secret_path="/hegemon/worker-${worker_num}"
    infisical_upsert "KC_CLIENT_SECRET" "$secret_path" "${CLIENT_SECRETS[$client_id]}"
    infisical_upsert "KC_CLIENT_ID" "$secret_path" "$client_id"
    echo -e "  ${GREEN}${secret_path}/KC_CLIENT_SECRET + KC_CLIENT_ID${NC}"
  done
fi

# --- Step 4: Verification ---
echo ""
echo -e "${CYAN}[4/4] Verification...${NC}"

if [ "$DRY_RUN" = true ]; then
  echo -e "  ${CYAN}[dry-run] Would verify token exchange + JWT claims${NC}"
else
  errors=0
  for entry in "${WORKERS[@]}"; do
    IFS=: read -r client_id worker_name worker_roles <<< "$entry"
    secret="${CLIENT_SECRETS[$client_id]}"

    # Get a token via client_credentials
    token_response=$(kc_curl -X POST \
      "${KEYCLOAK_URL}/realms/${KC_REALM}/protocol/openid-connect/token" \
      -d "client_id=${client_id}" \
      -d "client_secret=${secret}" \
      -d "grant_type=client_credentials")

    access_token=$(echo "$token_response" | jq -r '.access_token // empty')
    if [ -z "$access_token" ]; then
      echo -e "  ${RED}FAIL: ${client_id} — no token returned${NC}"
      errors=$((errors + 1))
      continue
    fi

    # Decode JWT payload (base64url → base64 → json)
    payload=$(echo "$access_token" | cut -d. -f2 | tr '_-' '/+' | base64 -d 2>/dev/null || true)

    jwt_worker_name=$(echo "$payload" | jq -r '.worker_name // empty')
    jwt_worker_roles=$(echo "$payload" | jq -r '.worker_roles // empty')
    jwt_exp=$(echo "$payload" | jq -r '.exp // 0')
    jwt_iat=$(echo "$payload" | jq -r '.iat // 0')
    ttl=$((jwt_exp - jwt_iat))

    if [ "$jwt_worker_name" = "$worker_name" ] && [ "$jwt_worker_roles" = "$worker_roles" ] && [ "$ttl" -le "$TOKEN_TTL_SECONDS" ]; then
      echo -e "  ${GREEN}OK: ${client_id} — worker_name=${jwt_worker_name}, worker_roles=${jwt_worker_roles}, ttl=${ttl}s${NC}"
    else
      echo -e "  ${RED}FAIL: ${client_id} — name=${jwt_worker_name} (expect ${worker_name}), roles=${jwt_worker_roles} (expect ${worker_roles}), ttl=${ttl}s (expect ${TOKEN_TTL_SECONDS})${NC}"
      errors=$((errors + 1))
    fi
  done

  echo ""
  if [ "$errors" -eq 0 ]; then
    echo -e "${GREEN}=== All 5 workers verified successfully ===${NC}"
  else
    echo -e "${RED}=== ${errors} worker(s) failed verification ===${NC}"
    exit 1
  fi
fi

echo ""
echo -e "${CYAN}Summary:${NC}"
echo "  Workers: ${#WORKERS[@]}"
echo "  Token TTL: ${TOKEN_TTL_SECONDS}s (5 min)"
echo "  Claims: worker_name, worker_roles"
echo "  Secrets: Infisical /hegemon/worker-{1-5}/KC_CLIENT_SECRET"
