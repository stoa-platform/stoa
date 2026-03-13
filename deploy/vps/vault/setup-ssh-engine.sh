#!/usr/bin/env bash
# =============================================================================
# Setup Vault SSH Secrets Engine (CA-based signing)
# =============================================================================
# Replaces static SSH key distribution with Vault-signed certificates.
# Users request a signed certificate from Vault (TTL 24h), VPS trusts the CA.
#
# Usage:
#   ./setup-ssh-engine.sh                    # Full setup (CA + roles)
#   ./setup-ssh-engine.sh --export-ca        # Export CA public key only
#   ./setup-ssh-engine.sh --sign <pubkey>    # Sign a public key (for testing)
#
# Prerequisites:
#   - VAULT_ADDR set (default: https://hcvault.gostoa.dev)
#   - VAULT_TOKEN set (admin token)
#
# Phase 5 — CAB-1802
# =============================================================================
set -euo pipefail

VAULT_ADDR="${VAULT_ADDR:-https://hcvault.gostoa.dev}"
VAULT_TOKEN="${VAULT_TOKEN:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CA_PUBKEY_FILE="${SCRIPT_DIR}/ssh-ca-pubkey.pem"

EXPORT_CA_ONLY=false
SIGN_KEY=""

for arg in "$@"; do
  case $arg in
    --export-ca) EXPORT_CA_ONLY=true ;;
    --sign)      shift; SIGN_KEY="${2:-}"; shift ;;
  esac
done

if [ -z "$VAULT_TOKEN" ]; then
  echo "ERROR: VAULT_TOKEN not set."
  echo "  export VAULT_TOKEN=\$(cat init-keys.json | python3 -c 'import sys,json; print(json.load(sys.stdin)[\"root_token\"])')"
  exit 1
fi

vault_api() {
  local method="$1" path="$2"
  shift 2
  curl -sf -X "$method" "${VAULT_ADDR}/v1${path}" \
    -H "X-Vault-Token: ${VAULT_TOKEN}" \
    -H "Content-Type: application/json" \
    "$@"
}

# --- Export CA public key ---
export_ca() {
  echo "Fetching SSH CA public key..."
  local ca_key
  ca_key=$(curl -sf "${VAULT_ADDR}/v1/ssh-client-signer/public_key" 2>/dev/null || echo "")
  if [ -z "$ca_key" ]; then
    echo "ERROR: SSH engine not configured yet. Run without --export-ca first."
    exit 1
  fi
  echo "$ca_key" > "$CA_PUBKEY_FILE"
  echo "CA public key saved to: ${CA_PUBKEY_FILE}"
  echo ""
  echo "Deploy to VPS sshd_config:"
  echo "  TrustedUserCAKeys /etc/ssh/vault-ca.pub"
}

if [ "$EXPORT_CA_ONLY" = true ]; then
  export_ca
  exit 0
fi

# --- Sign a key (for testing) ---
if [ -n "$SIGN_KEY" ]; then
  if [ ! -f "$SIGN_KEY" ]; then
    echo "ERROR: Public key file not found: $SIGN_KEY"
    exit 1
  fi
  echo "Signing key: $SIGN_KEY"
  PUBKEY_CONTENT=$(cat "$SIGN_KEY")
  RESULT=$(vault_api POST "/ssh-client-signer/sign/admin" \
    -d "$(python3 -c "
import json
print(json.dumps({
    'public_key': '''${PUBKEY_CONTENT}''',
    'valid_principals': 'debian,root',
    'ttl': '24h'
}))
")")
  SIGNED_KEY=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['signed_key'])")
  CERT_FILE="${SIGN_KEY%.pub}-cert.pub"
  echo "$SIGNED_KEY" > "$CERT_FILE"
  echo "Signed certificate saved to: $CERT_FILE"
  echo "Valid for 24h. Use: ssh -i ${SIGN_KEY%.pub} -o CertificateFile=$CERT_FILE user@host"
  exit 0
fi

# =============================================================================
# Full Setup
# =============================================================================
echo "=== Vault SSH Secrets Engine Setup ==="
echo "Vault: ${VAULT_ADDR}"
echo ""

# Step 1: Enable SSH secrets engine
echo "[1/5] Enabling SSH secrets engine at ssh-client-signer/..."
vault_api POST "/sys/mounts/ssh-client-signer" \
  -d '{"type": "ssh"}' 2>/dev/null && echo "  Enabled" || echo "  Already enabled"

# Step 2: Generate CA keypair
echo "[2/5] Configuring CA keypair..."
vault_api POST "/ssh-client-signer/config/ca" \
  -d '{"generate_signing_key": true, "key_type": "ed25519"}' 2>/dev/null \
  && echo "  CA keypair generated (Ed25519)" \
  || echo "  CA already configured"

# Step 3: Export CA public key
echo "[3/5] Exporting CA public key..."
CA_KEY=$(curl -sf "${VAULT_ADDR}/v1/ssh-client-signer/public_key")
echo "$CA_KEY" > "$CA_PUBKEY_FILE"
echo "  Saved to: ${CA_PUBKEY_FILE}"

# Step 4: Create signing roles
echo "[4/5] Creating signing roles..."

# Admin role — can sign for debian + root, 24h TTL
vault_api POST "/ssh-client-signer/roles/admin" \
  -d '{
    "key_type": "ca",
    "algorithm_signer": "default",
    "allow_user_certificates": true,
    "allowed_users": "debian,root",
    "allowed_extensions": "permit-pty,permit-port-forwarding,permit-agent-forwarding",
    "default_extensions": {"permit-pty": ""},
    "default_user": "debian",
    "ttl": "24h",
    "max_ttl": "72h"
  }' && echo "  Role 'admin' created (TTL 24h, max 72h)"

# CI/CD role — shorter TTL, debian only, no port forwarding
vault_api POST "/ssh-client-signer/roles/ci-deploy" \
  -d '{
    "key_type": "ca",
    "algorithm_signer": "default",
    "allow_user_certificates": true,
    "allowed_users": "debian",
    "allowed_extensions": "permit-pty",
    "default_extensions": {"permit-pty": ""},
    "default_user": "debian",
    "ttl": "30m",
    "max_ttl": "2h"
  }' && echo "  Role 'ci-deploy' created (TTL 30m, max 2h)"

# Step 5: Write SSH signer policy
echo "[5/5] Writing ssh-signer policy..."
POLICY_FILE="${SCRIPT_DIR}/policies/ssh-signer.hcl"
cat > "$POLICY_FILE" << 'POLICY'
# SSH signer policy — sign SSH certificates via Vault CA
# Used by: humans (admin role), CI/CD (ci-deploy role)

# Sign SSH certificates (admin role — 24h TTL)
path "ssh-client-signer/sign/admin" {
  capabilities = ["create", "update"]
}

# Sign SSH certificates (CI/CD role — 30m TTL)
path "ssh-client-signer/sign/ci-deploy" {
  capabilities = ["create", "update"]
}

# Read CA public key (needed for trust deployment)
path "ssh-client-signer/public_key" {
  capabilities = ["read"]
}

# List roles (informational)
path "ssh-client-signer/roles/*" {
  capabilities = ["read", "list"]
}
POLICY
echo "  Policy written to: ${POLICY_FILE}"

# Apply the policy to Vault
vault_api PUT "/sys/policies/acl/ssh-signer" \
  -d "$(python3 -c "import json; print(json.dumps({'policy': open('${POLICY_FILE}').read()}))")"
echo "  Policy 'ssh-signer' applied"

echo ""
echo "=== SSH Engine Setup Complete ==="
echo ""
echo "CA public key: ${CA_PUBKEY_FILE}"
echo "Roles:         admin (24h), ci-deploy (30m)"
echo "Policy:        ssh-signer"
echo ""
echo "Next steps:"
echo "  1. Deploy CA to VPS:  ./deploy-ssh-trust.sh"
echo "  2. Sign a key:        $0 --sign ~/.ssh/id_ed25519.pub"
echo "  3. Connect:           ssh -o CertificateFile=~/.ssh/id_ed25519-cert.pub debian@<vps>"
echo ""
echo "Future: replace distribute-ssh-key.sh with:"
echo "  vault write ssh-client-signer/sign/admin public_key=@~/.ssh/id_ed25519.pub"
