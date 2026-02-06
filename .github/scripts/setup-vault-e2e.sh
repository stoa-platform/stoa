#!/bin/bash
# Setup Vault for GitHub Actions E2E tests
# Run this script with proper Vault authentication

set -e

export VAULT_ADDR="${VAULT_ADDR:-https://vault.gostoa.dev}"

echo "=== STOA Vault E2E Setup ==="
echo "Vault Address: $VAULT_ADDR"
echo ""

# Check if logged in
if ! vault token lookup &>/dev/null; then
    echo "ERROR: Not logged in to Vault. Run 'vault login' first."
    exit 1
fi

echo "✓ Authenticated to Vault"
echo ""

# ============================================
# 1. Check/Enable JWT Auth Method
# ============================================
echo "--- Checking JWT Auth Method ---"

if vault auth list | grep -q "jwt/"; then
    echo "✓ JWT auth method already enabled"
else
    echo "Enabling JWT auth method..."
    vault auth enable jwt
    echo "✓ JWT auth method enabled"
fi

# ============================================
# 2. Configure GitHub OIDC Provider
# ============================================
echo ""
echo "--- Configuring GitHub OIDC Provider ---"

vault write auth/jwt/config \
    bound_issuer="https://token.actions.githubusercontent.com" \
    oidc_discovery_url="https://token.actions.githubusercontent.com"

echo "✓ GitHub OIDC provider configured"

# ============================================
# 3. Create/Update Policy
# ============================================
echo ""
echo "--- Creating github-actions Policy ---"

vault policy write github-actions - <<'EOF'
# Read E2E test secrets
path "secret/data/e2e/*" {
  capabilities = ["read"]
}

# List E2E secrets (for debugging)
path "secret/metadata/e2e/*" {
  capabilities = ["list"]
}
EOF

echo "✓ Policy 'github-actions' created/updated"

# ============================================
# 4. Create/Update JWT Role
# ============================================
echo ""
echo "--- Creating github-actions Role ---"

vault write auth/jwt/role/github-actions \
    role_type="jwt" \
    bound_audiences="sigstore" \
    bound_claims_type="glob" \
    bound_claims='{"repository":"stoa-platform/stoa","ref":"refs/heads/*"}' \
    user_claim="repository" \
    token_policies="github-actions" \
    token_ttl="10m" \
    token_max_ttl="15m"

echo "✓ Role 'github-actions' created/updated"

# ============================================
# 5. Enable KV v2 Secrets Engine (if needed)
# ============================================
echo ""
echo "--- Checking Secrets Engine ---"

if vault secrets list | grep -q "secret/"; then
    echo "✓ KV secrets engine already enabled at secret/"
else
    echo "Enabling KV v2 secrets engine..."
    vault secrets enable -path=secret kv-v2
    echo "✓ KV v2 secrets engine enabled"
fi

# ============================================
# 6. Create E2E Secrets
# ============================================
echo ""
echo "--- Creating E2E Secrets ---"

# URLs
echo "Creating secret/e2e/urls..."
vault kv put secret/e2e/urls \
    PORTAL_URL="https://portal.gostoa.dev" \
    CONSOLE_URL="https://console.gostoa.dev" \
    GATEWAY_URL="https://api.gostoa.dev" \
    KEYCLOAK_URL="https://auth.gostoa.dev"

# Default password for demo environment
DEFAULT_PASSWORD="demo"

# High-Five Team
echo "Creating secret/e2e/personas/parzival..."
vault kv put secret/e2e/personas/parzival \
    username="parzival" \
    password="$DEFAULT_PASSWORD"

echo "Creating secret/e2e/personas/art3mis..."
vault kv put secret/e2e/personas/art3mis \
    username="art3mis" \
    password="$DEFAULT_PASSWORD"

echo "Creating secret/e2e/personas/aech..."
vault kv put secret/e2e/personas/aech \
    username="aech" \
    password="$DEFAULT_PASSWORD"

# IOI Team
echo "Creating secret/e2e/personas/sorrento..."
vault kv put secret/e2e/personas/sorrento \
    username="sorrento" \
    password="$DEFAULT_PASSWORD"

echo "Creating secret/e2e/personas/i-r0k..."
vault kv put secret/e2e/personas/i-r0k \
    username="i-r0k" \
    password="$DEFAULT_PASSWORD"

# Admin
echo "Creating secret/e2e/personas/anorak..."
vault kv put secret/e2e/personas/anorak \
    username="anorak" \
    password="$DEFAULT_PASSWORD"

# Freelance
echo "Creating secret/e2e/personas/alex..."
vault kv put secret/e2e/personas/alex \
    username="alex" \
    password="$DEFAULT_PASSWORD"

# API Keys
echo "Creating secret/e2e/api-keys..."
vault kv put secret/e2e/api-keys \
    test="test-api-key-for-e2e"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Verify by listing secrets:"
echo "  vault kv list secret/e2e/"
echo "  vault kv list secret/e2e/personas/"
echo ""
echo "Test reading a secret:"
echo "  vault kv get secret/e2e/personas/parzival"
echo ""
echo "GitHub Actions can now authenticate using OIDC!"
