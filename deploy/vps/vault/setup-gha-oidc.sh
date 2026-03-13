#!/usr/bin/env bash
# Configure Vault JWT auth for GitHub Actions OIDC
# Run ON the Vault VPS (or locally with VAULT_ADDR + VAULT_TOKEN set)
#
# Prerequisites:
#   - Vault unsealed and root token available
#   - gha-deploy policy already written (via init-vault.sh)
#
# Usage:
#   VAULT_TOKEN=... ./setup-gha-oidc.sh
#   VAULT_TOKEN=... ./setup-gha-oidc.sh --store-keys  # Also store SSH keys from stdin
set -euo pipefail

VAULT_ADDR="${VAULT_ADDR:-http://127.0.0.1:8200}"
VAULT_TOKEN="${VAULT_TOKEN:?VAULT_TOKEN is required}"
REPO="stoa-platform/stoa"
STORE_KEYS=false

for arg in "$@"; do
  case $arg in
    --store-keys) STORE_KEYS=true ;;
  esac
done

vault_api() {
  local method="$1" path="$2" data="${3:-}"
  local args=(-sf -X "$method" "${VAULT_ADDR}/v1/${path}" -H "X-Vault-Token: ${VAULT_TOKEN}")
  [[ -n "$data" ]] && args+=(-H "Content-Type: application/json" -d "$data")
  curl "${args[@]}"
}

echo "=== GitHub Actions OIDC → Vault JWT Auth ==="
echo "Vault: ${VAULT_ADDR}"
echo "Repo:  ${REPO}"
echo ""

# Step 1: Enable JWT auth method
echo "[1/4] Enabling JWT auth method..."
vault_api POST "sys/auth/jwt" '{"type": "jwt"}' 2>/dev/null || echo "  (already enabled)"

# Step 2: Configure JWT auth with GitHub OIDC
echo "[2/4] Configuring GitHub OIDC provider..."
vault_api POST "auth/jwt/config" "$(cat <<CONF
{
  "oidc_discovery_url": "https://token.actions.githubusercontent.com",
  "bound_issuer": "https://token.actions.githubusercontent.com"
}
CONF
)"
echo "  GitHub OIDC configured."

# Step 3: Create role for stoa repo
echo "[3/4] Creating 'gha-stoa-deploy' role..."
vault_api POST "auth/jwt/role/gha-stoa-deploy" "$(cat <<ROLE
{
  "role_type": "jwt",
  "policies": ["gha-deploy"],
  "token_ttl": "600",
  "token_max_ttl": "1200",
  "bound_claims": {
    "repository": "${REPO}"
  },
  "user_claim": "actor",
  "claim_mappings": {
    "repository": "repository",
    "workflow": "workflow",
    "ref": "ref"
  },
  "bound_audiences": ["https://github.com/${REPO}"]
}
ROLE
)"
echo "  Role 'gha-stoa-deploy' created."

# Step 4: Write gha-deploy policy
echo "[4/4] Writing gha-deploy policy..."
POLICY_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/policies/gha-deploy.hcl"
if [[ -f "$POLICY_FILE" ]]; then
  vault_api PUT "sys/policies/acl/gha-deploy" \
    "$(python3 -c "import json; print(json.dumps({'policy': open('${POLICY_FILE}').read()}))")"
  echo "  Policy 'gha-deploy' written."
else
  echo "  WARNING: ${POLICY_FILE} not found. Write policy manually."
fi

echo ""
echo "=== OIDC Setup Complete ==="
echo ""
echo "GHA workflows can now authenticate via:"
echo "  - uses: hashicorp/vault-action@v3"
echo "    with:"
echo "      url: https://hcvault.gostoa.dev"
echo "      method: jwt"
echo "      role: gha-stoa-deploy"
echo "      jwtGithubAudience: https://github.com/${REPO}"
echo ""

# Optional: store SSH keys
if [[ "$STORE_KEYS" == "true" ]]; then
  echo "=== Storing SSH Keys ==="
  echo ""
  echo "Paste each private key when prompted (Ctrl+D to end)."
  echo ""

  for key_name in hegemon-workers ovh-prod vault-vps; do
    echo "  Key: stoa/ssh/${key_name}"
    echo "  Enter path to private key file (or 'skip'):"
    read -r key_path
    if [[ "$key_path" == "skip" ]]; then
      echo "  Skipped."
      continue
    fi
    if [[ ! -f "$key_path" ]]; then
      echo "  ERROR: File not found: ${key_path}"
      continue
    fi
    # Store as base64 to avoid JSON escaping issues with newlines
    key_b64=$(base64 < "$key_path" | tr -d '\n')
    vault_api POST "stoa/data/ssh/${key_name}" \
      "$(python3 -c "import json; print(json.dumps({'data': {'private_key_b64': '${key_b64}'}}))")"
    echo "  Stored."
  done
fi
