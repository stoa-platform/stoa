#!/usr/bin/env bash
# Initialize and configure HashiCorp Vault
# Run ON the VPS after first docker compose up
#
# Usage:
#   ./init-vault.sh            # Full init + unseal + configure
#   ./init-vault.sh --unseal   # Unseal only (already initialized)
#   ./init-vault.sh --configure # Configure only (already unsealed)
set -euo pipefail

VAULT_ADDR="http://127.0.0.1:8200"
export VAULT_ADDR

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEYS_FILE="${SCRIPT_DIR}/init-keys.json"
POLICIES_DIR="${SCRIPT_DIR}/policies"
UNSEAL_ONLY=false
CONFIGURE_ONLY=false

for arg in "$@"; do
  case $arg in
    --unseal)    UNSEAL_ONLY=true ;;
    --configure) CONFIGURE_ONLY=true ;;
  esac
done

# All operations use curl against the Vault HTTP API (no vault CLI required)

# --- Step 1: Initialize ---
if [ "$UNSEAL_ONLY" = false ] && [ "$CONFIGURE_ONLY" = false ]; then
  echo "=== Step 1: Initialize Vault ==="

  # Check if already initialized
  HEALTH=$(curl -sf "${VAULT_ADDR}/v1/sys/health?standbyok=true&uninitcode=501&sealedcode=503" -o /dev/null -w '%{http_code}' 2>/dev/null || echo "000")
  if [ "$HEALTH" = "200" ]; then
    echo "  Vault already initialized and unsealed. Skipping to configure."
    CONFIGURE_ONLY=true
  elif [ "$HEALTH" = "503" ]; then
    echo "  Vault initialized but sealed. Skipping to unseal."
    UNSEAL_ONLY=true
  elif [ "$HEALTH" = "501" ]; then
    echo "  Initializing with 5 key shares, 3 threshold..."

    INIT_RESULT=$(curl -sf -X PUT "${VAULT_ADDR}/v1/sys/init" \
      -H "Content-Type: application/json" \
      -d '{"secret_shares": 5, "secret_threshold": 3}')

    echo "$INIT_RESULT" > "$KEYS_FILE"
    chmod 600 "$KEYS_FILE"
    echo "  Init keys saved to ${KEYS_FILE}"
    echo ""
    echo "  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo "  !! BACK UP init-keys.json TO A SECURE LOCATION !!"
    echo "  !! This file contains unseal keys + root token !!"
    echo "  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo ""
  else
    echo "  ERROR: Vault not responding (HTTP $HEALTH)"
    exit 1
  fi
fi

# --- Step 2: Unseal ---
if [ "$CONFIGURE_ONLY" = false ]; then
  echo "=== Step 2: Unseal Vault ==="

  if [ ! -f "$KEYS_FILE" ]; then
    echo "  ERROR: ${KEYS_FILE} not found. Cannot unseal."
    exit 1
  fi

  # Check if already unsealed
  SEALED=$(curl -sf "${VAULT_ADDR}/v1/sys/health?standbyok=true&uninitcode=501&sealedcode=503" -o /dev/null -w '%{http_code}' 2>/dev/null || echo "000")
  if [ "$SEALED" = "200" ]; then
    echo "  Already unsealed."
  else
    # Extract 3 unseal keys (threshold) and unseal
    for i in 0 1 2; do
      KEY=$(python3 -c "import json; print(json.load(open('${KEYS_FILE}'))['keys'][${i}])")
      RESULT=$(curl -sf -X PUT "${VAULT_ADDR}/v1/sys/unseal" \
        -H "Content-Type: application/json" \
        -d "{\"key\": \"${KEY}\"}")
      STILL_SEALED=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['sealed'])")
      echo "  Key $((i+1))/3 applied. Sealed: ${STILL_SEALED}"
    done

    # Verify
    SEALED_CHECK=$(curl -sf "${VAULT_ADDR}/v1/sys/health?standbyok=true&uninitcode=501&sealedcode=503" -o /dev/null -w '%{http_code}' 2>/dev/null || echo "000")
    if [ "$SEALED_CHECK" = "200" ]; then
      echo "  Vault unsealed successfully."
    else
      echo "  ERROR: Vault still sealed after 3 keys (HTTP $SEALED_CHECK)"
      exit 1
    fi
  fi

  if [ "$UNSEAL_ONLY" = true ]; then
    echo "Done (unseal only)."
    exit 0
  fi
fi

# --- Step 3: Configure ---
echo "=== Step 3: Configure Vault ==="

# Extract root token
ROOT_TOKEN=$(python3 -c "import json; print(json.load(open('${KEYS_FILE}'))['root_token'])")
export VAULT_TOKEN="$ROOT_TOKEN"

# 3a: Enable KV v2 at stoa/
echo "  [3a] Enabling KV v2 engine at stoa/..."
curl -sf -X POST "${VAULT_ADDR}/v1/sys/mounts/stoa" \
  -H "X-Vault-Token: ${ROOT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"type": "kv", "options": {"version": "2"}}' 2>/dev/null || echo "  (already enabled)"

# 3b: Enable Transit engine
echo "  [3b] Enabling Transit engine..."
curl -sf -X POST "${VAULT_ADDR}/v1/sys/mounts/transit" \
  -H "X-Vault-Token: ${ROOT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"type": "transit"}' 2>/dev/null || echo "  (already enabled)"

# Create a transit key for backup encryption
curl -sf -X POST "${VAULT_ADDR}/v1/transit/keys/backup-encryption" \
  -H "X-Vault-Token: ${ROOT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"type": "aes256-gcm96"}' 2>/dev/null || echo "  (key already exists)"

# 3c: Enable audit logging
echo "  [3c] Enabling audit log..."
curl -sf -X PUT "${VAULT_ADDR}/v1/sys/audit/file" \
  -H "X-Vault-Token: ${ROOT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"type": "file", "options": {"file_path": "/vault/logs/audit.log"}}' 2>/dev/null || echo "  (already enabled)"

# 3d: Write policies
echo "  [3d] Writing RBAC policies..."
for policy_file in "${POLICIES_DIR}"/*.hcl; do
  policy_name=$(basename "$policy_file" .hcl)
  curl -sf -X PUT "${VAULT_ADDR}/v1/sys/policies/acl/${policy_name}" \
    -H "X-Vault-Token: ${ROOT_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$(python3 -c "import json; print(json.dumps({'policy': open('${policy_file}').read()}))")"
  echo "    Policy '${policy_name}' written."
done

# 3e: Enable AppRole auth
echo "  [3e] Enabling AppRole auth..."
curl -sf -X POST "${VAULT_ADDR}/v1/sys/auth/approle" \
  -H "X-Vault-Token: ${ROOT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"type": "approle"}' 2>/dev/null || echo "  (already enabled)"

# Create AppRoles for each VPS service
APPROLES=("vps-n8n" "vps-kong" "vps-gravitee" "vps-webmethods" "vps-hegemon")
for role in "${APPROLES[@]}"; do
  echo "    Creating AppRole '${role}'..."
  curl -sf -X POST "${VAULT_ADDR}/v1/auth/approle/role/${role}" \
    -H "X-Vault-Token: ${ROOT_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$(python3 -c "import json; print(json.dumps({
      'token_policies': ['${role}'],
      'token_ttl': '24h',
      'token_max_ttl': '768h',
      'secret_id_ttl': '0',
      'secret_id_num_uses': 0
    }))")"
done

# 3f: Enable Kubernetes auth (for ESO — configured later in Phase 2)
echo "  [3f] Enabling Kubernetes auth..."
curl -sf -X POST "${VAULT_ADDR}/v1/sys/auth/kubernetes" \
  -H "X-Vault-Token: ${ROOT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"type": "kubernetes"}' 2>/dev/null || echo "  (already enabled)"

echo ""
echo "=== Configuration Complete ==="
echo ""
echo "Engines:  kv-v2 at stoa/, transit at transit/"
echo "Policies: $(find "${POLICIES_DIR}" -name '*.hcl' | wc -l | tr -d ' ') policies written"
echo "Auth:     AppRole (${#APPROLES[@]} roles), Kubernetes (pending Phase 2 config)"
echo "Audit:    file backend at /vault/logs/audit.log"
echo ""
echo "Verify:"
echo "  export VAULT_ADDR=${VAULT_ADDR}"
echo "  export VAULT_TOKEN=${ROOT_TOKEN}"
echo "  vault status"
echo "  vault kv list stoa/"
echo "  vault policy list"
echo "  vault auth list"
echo ""
echo "Generate AppRole credentials (for Phase 1):"
for role in "${APPROLES[@]}"; do
  echo "  vault read auth/approle/role/${role}/role-id"
  echo "  vault write -f auth/approle/role/${role}/secret-id"
done
