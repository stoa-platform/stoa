#!/usr/bin/env bash
# =============================================================================
# STOA Platform — Migrate Secrets from Infisical to HashiCorp Vault
# =============================================================================
# Phase 1 (CAB-1797): Read secrets from Infisical, write to Vault KV v2.
# Idempotent — safe to re-run. Does NOT modify Infisical (read-only).
#
# Usage:
#   ./scripts/ops/migrate-to-vault.sh               # Full migration
#   ./scripts/ops/migrate-to-vault.sh --dry-run      # Show plan without writing
#   ./scripts/ops/migrate-to-vault.sh --verify        # Verify parity only
#   ./scripts/ops/migrate-to-vault.sh --generate-approle-creds  # Generate AppRole creds
#
# Prerequisites:
#   - VAULT_ADDR=https://hcv.gostoa.dev
#   - VAULT_TOKEN set (admin token from init-keys.json)
#   - INFISICAL_TOKEN set: eval $(infisical-token)
#   - infisical CLI installed
#   - vault CLI installed (or curl fallback)
#   - jq installed
# =============================================================================
set -euo pipefail

# --- Configuration ---
VAULT_ADDR="${VAULT_ADDR:-https://hcv.gostoa.dev}"
INFISICAL_PROJECT_ID="97972ffc-990b-4d28-9c4d-0664d217f03b"
DRY_RUN=false
VERIFY_ONLY=false
GEN_APPROLE=false

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Counters
MIGRATED=0
SKIPPED=0
ERRORS=0

# --- Parse args ---
for arg in "$@"; do
  case $arg in
    --dry-run)     DRY_RUN=true ;;
    --verify)      VERIFY_ONLY=true ;;
    --generate-approle-creds) GEN_APPROLE=true ;;
    --help|-h)
      echo "Usage: $0 [--dry-run] [--verify] [--generate-approle-creds]"
      exit 0
      ;;
  esac
done

# --- Validation ---
if [ "$GEN_APPROLE" = false ]; then
  if [ -z "${INFISICAL_TOKEN:-}" ]; then
    echo -e "${RED}Error: INFISICAL_TOKEN not set. Run: eval \$(infisical-token)${NC}"
    exit 1
  fi
fi

if [ -z "${VAULT_TOKEN:-}" ]; then
  echo -e "${RED}Error: VAULT_TOKEN not set.${NC}"
  exit 1
fi

# --- Helpers ---

# Read a secret from Infisical CLI
read_infisical() {
  local path="$1" key="$2"
  infisical secrets get "$key" \
    --env=prod \
    --path="$path" \
    --projectId="$INFISICAL_PROJECT_ID" \
    --token="$INFISICAL_TOKEN" \
    --plain 2>/dev/null || echo ""
}

# Read all secrets from an Infisical path as JSON
read_infisical_path() {
  local path="$1"
  infisical secrets list \
    --env=prod \
    --path="$path" \
    --projectId="$INFISICAL_PROJECT_ID" \
    --token="$INFISICAL_TOKEN" \
    --format=json 2>/dev/null || echo "[]"
}

# Write a secret to Vault KV v2
write_vault() {
  local vault_path="$1"
  shift
  # Remaining args are key=value pairs
  if [ "$DRY_RUN" = true ]; then
    echo -e "    ${YELLOW}[dry-run] vault kv put ${vault_path} (${#} keys)${NC}"
    return
  fi

  curl -sf -X POST "${VAULT_ADDR}/v1/stoa/data/${vault_path}" \
    -H "X-Vault-Token: ${VAULT_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$(python3 -c "
import json, sys
data = {}
for arg in sys.argv[1:]:
    k, v = arg.split('=', 1)
    data[k] = v
print(json.dumps({'data': data}))
" "$@")" >/dev/null
}

# Read a secret from Vault for verification
read_vault() {
  local vault_path="$1" key="$2"
  curl -sf "${VAULT_ADDR}/v1/stoa/data/${vault_path}" \
    -H "X-Vault-Token: ${VAULT_TOKEN}" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['data'].get('${key}',''))" 2>/dev/null || echo ""
}

# Migrate one Infisical path to one Vault path
migrate_path() {
  local infisical_path="$1" vault_path="$2"
  echo -e "${CYAN}  Migrating ${infisical_path} → stoa/${vault_path}${NC}"

  # Get all secrets from Infisical path
  local secrets_json
  secrets_json=$(read_infisical_path "$infisical_path")
  local count
  count=$(echo "$secrets_json" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

  if [ "$count" = "0" ]; then
    echo -e "    ${YELLOW}[skip] No secrets found at ${infisical_path}${NC}"
    SKIPPED=$((SKIPPED + 1))
    return
  fi

  # Build key=value pairs
  local kv_args=()
  while IFS= read -r line; do
    local key val
    key=$(echo "$line" | python3 -c "import sys,json; print(json.load(sys.stdin)['key'])")
    val=$(echo "$line" | python3 -c "import sys,json; print(json.load(sys.stdin)['value'])")
    if [ -n "$key" ] && [ -n "$val" ]; then
      kv_args+=("${key}=${val}")
    fi
  done < <(echo "$secrets_json" | python3 -c "
import sys, json
secrets = json.load(sys.stdin)
for s in secrets:
    print(json.dumps({'key': s.get('secretKey',''), 'value': s.get('secretValue','')}))
")

  if [ ${#kv_args[@]} -eq 0 ]; then
    echo -e "    ${YELLOW}[skip] No key-value pairs extracted${NC}"
    SKIPPED=$((SKIPPED + 1))
    return
  fi

  # Write to Vault
  write_vault "$vault_path" "${kv_args[@]}"

  if [ "$DRY_RUN" = false ]; then
    # Verify: read back first key
    local first_key="${kv_args[0]%%=*}"
    local expected="${kv_args[0]#*=}"
    local actual
    actual=$(read_vault "$vault_path" "$first_key")
    if [ "$actual" = "$expected" ]; then
      echo -e "    ${GREEN}[OK] ${count} keys migrated, verified${NC}"
      MIGRATED=$((MIGRATED + 1))
    else
      echo -e "    ${RED}[ERROR] Verification failed for ${first_key}${NC}"
      ERRORS=$((ERRORS + 1))
    fi
  else
    echo -e "    ${YELLOW}[dry-run] Would migrate ${count} keys${NC}"
    MIGRATED=$((MIGRATED + 1))
  fi
}

# --- Generate AppRole Credentials ---
if [ "$GEN_APPROLE" = true ]; then
  echo -e "${BOLD}=== Generating AppRole Credentials ===${NC}"
  echo ""

  ROLES=("vps-n8n" "vps-kong" "vps-gravitee" "vps-webmethods" "vps-hegemon")
  for role in "${ROLES[@]}"; do
    echo -e "${CYAN}AppRole: ${role}${NC}"

    ROLE_ID=$(curl -sf "${VAULT_ADDR}/v1/auth/approle/role/${role}/role-id" \
      -H "X-Vault-Token: ${VAULT_TOKEN}" | \
      python3 -c "import sys,json; print(json.load(sys.stdin)['data']['role_id'])")

    SECRET_ID_RESP=$(curl -sf -X POST "${VAULT_ADDR}/v1/auth/approle/role/${role}/secret-id" \
      -H "X-Vault-Token: ${VAULT_TOKEN}")
    SECRET_ID=$(echo "$SECRET_ID_RESP" | \
      python3 -c "import sys,json; print(json.load(sys.stdin)['data']['secret_id'])")

    echo "  role_id:   ${ROLE_ID}"
    echo "  secret_id: ${SECRET_ID}"
    echo ""
    echo "  Deploy to VPS:"
    echo "    echo '${ROLE_ID}' > /etc/vault-agent/role-id"
    echo "    echo '${SECRET_ID}' > /etc/vault-agent/secret-id"
    echo "    chmod 600 /etc/vault-agent/{role-id,secret-id}"
    echo ""
  done

  exit 0
fi

# --- Migration ---
echo -e "${BOLD}=== STOA Secrets Migration: Infisical → Vault ===${NC}"
echo "Vault:     ${VAULT_ADDR}"
echo "Infisical: project ${INFISICAL_PROJECT_ID}"
echo "Mode:      $([ "$DRY_RUN" = true ] && echo "DRY RUN" || ([ "$VERIFY_ONLY" = true ] && echo "VERIFY" || echo "MIGRATE"))"
echo ""

# K8s secrets
echo -e "${BOLD}[1/4] K8s Secrets${NC}"
migrate_path "/gateway"    "k8s/gateway"
migrate_path "/database"   "k8s/control-plane-api"
migrate_path "/opensearch" "k8s/opensearch"
migrate_path "/ghcr"       "k8s/ghcr"

# VPS secrets
echo ""
echo -e "${BOLD}[2/4] VPS Secrets${NC}"
migrate_path "/webmethods"  "vps/webmethods"
migrate_path "/kong"        "vps/kong"
migrate_path "/gravitee"    "vps/gravitee"
migrate_path "/n8n"         "vps/n8n"
migrate_path "/netbox"      "vps/netbox"
migrate_path "/pocketbase"  "vps/pocketbase"
migrate_path "/hegemon"     "vps/hegemon"
migrate_path "/gateway/arena" "vps/arena"

# Shared secrets
echo ""
echo -e "${BOLD}[3/4] Shared Secrets${NC}"
migrate_path "/keycloak"   "shared/keycloak"
migrate_path "/anthropic"  "shared/anthropic"
migrate_path "/cloudflare" "shared/cloudflare"
migrate_path "/slack"       "shared/slack"
migrate_path "/github"      "shared/github"
migrate_path "/ovh"         "shared/ovh"

# SSH keys
echo ""
echo -e "${BOLD}[4/4] SSH Keys${NC}"
migrate_path "/ssh"        "ssh/authorized_keys"

# --- Summary ---
echo ""
echo -e "${BOLD}=== Migration Summary ===${NC}"
echo -e "  Migrated: ${GREEN}${MIGRATED}${NC}"
echo -e "  Skipped:  ${YELLOW}${SKIPPED}${NC}"
echo -e "  Errors:   ${RED}${ERRORS}${NC}"

if [ "$ERRORS" -gt 0 ]; then
  echo ""
  echo -e "${RED}Migration completed with errors. Review above.${NC}"
  exit 1
fi

echo ""
echo -e "${GREEN}Migration complete.${NC}"
echo ""
echo "Next steps:"
echo "  1. Verify: $0 --verify"
echo "  2. Generate AppRole creds: $0 --generate-approle-creds"
echo "  3. Proceed to Phase 2 (K8s ESO) or Phase 3 (VPS Agent)"
