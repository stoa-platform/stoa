# Vault Setup for GitHub Actions

This document describes how to configure HashiCorp Vault for GitHub Actions OIDC authentication.

## Prerequisites

- Vault instance running at `https://vault.gostoa.dev`
- Vault admin access
- GitHub repository: `stoa-platform/stoa`

## 1. Enable JWT Auth Method

```bash
# Login to Vault
export VAULT_ADDR="https://vault.gostoa.dev"
vault login

# Enable JWT auth method
vault auth enable jwt
```

## 2. Configure GitHub OIDC Provider

```bash
vault write auth/jwt/config \
  bound_issuer="https://token.actions.githubusercontent.com" \
  oidc_discovery_url="https://token.actions.githubusercontent.com"
```

## 3. Create Policy for GitHub Actions

```bash
# Create policy file
cat <<EOF > /tmp/github-actions-policy.hcl
# Read E2E test secrets
path "secret/data/e2e/*" {
  capabilities = ["read"]
}

# Read deployment secrets (if needed)
path "secret/data/deploy/*" {
  capabilities = ["read"]
}
EOF

# Write policy to Vault
vault policy write github-actions /tmp/github-actions-policy.hcl
```

## 4. Create JWT Role for GitHub Actions

```bash
vault write auth/jwt/role/github-actions \
  role_type="jwt" \
  bound_audiences="sigstore" \
  bound_claims_type="glob" \
  bound_claims='{"repository":"stoa-platform/stoa","ref":"refs/heads/*"}' \
  user_claim="repository" \
  token_policies="github-actions" \
  token_ttl="10m" \
  token_max_ttl="15m"
```

### Role Configuration Explained

| Parameter | Value | Description |
|-----------|-------|-------------|
| `bound_audiences` | `sigstore` | Must match `jwtGithubAudience` in workflow |
| `bound_claims.repository` | `stoa-platform/stoa` | Only this repo can authenticate |
| `bound_claims.ref` | `refs/heads/*` | Allow all branches |
| `user_claim` | `repository` | Use repo name as identity |
| `token_ttl` | `10m` | Short-lived tokens for security |

## 5. Create E2E Test Secrets

### URLs

```bash
vault kv put secret/e2e/urls \
  PORTAL_URL="https://portal.gostoa.dev" \
  CONSOLE_URL="https://console.gostoa.dev" \
  GATEWAY_URL="https://api.gostoa.dev" \
  KEYCLOAK_URL="https://auth.gostoa.dev"
```

### Personas - High-Five Team

```bash
# Parzival (Wade Watts) - Developer
vault kv put secret/e2e/personas/parzival \
  username="parzival" \
  password="<secure-password>"

# Art3mis (Samantha Cook) - Developer
vault kv put secret/e2e/personas/art3mis \
  username="art3mis" \
  password="<secure-password>"

# Aech (Helen Harris) - Developer
vault kv put secret/e2e/personas/aech \
  username="aech" \
  password="<secure-password>"
```

### Personas - IOI Team

```bash
# Sorrento (Nolan Sorrento) - Tenant Admin
vault kv put secret/e2e/personas/sorrento \
  username="sorrento" \
  password="<secure-password>"

# i-R0k - DevOps
vault kv put secret/e2e/personas/i-r0k \
  username="i-r0k" \
  password="<secure-password>"
```

### Personas - Admin

```bash
# Anorak (James Halliday) - Platform Admin
vault kv put secret/e2e/personas/anorak \
  username="anorak" \
  password="<secure-password>"
```

### Personas - Freelance

```bash
# Alex - External Developer
vault kv put secret/e2e/personas/alex \
  username="alex" \
  password="<secure-password>"
```

### API Keys

```bash
vault kv put secret/e2e/api-keys \
  test="<test-api-key>"
```

## 6. Verify Configuration

### Test JWT Authentication Locally

```bash
# This simulates what GitHub Actions does
# (You need a valid GitHub OIDC token for this)
vault write auth/jwt/login \
  role=github-actions \
  jwt="<github-oidc-token>"
```

### List Secrets

```bash
vault kv list secret/e2e/
vault kv list secret/e2e/personas/
```

### Read a Secret

```bash
vault kv get secret/e2e/personas/parzival
```

## 7. Workflow Integration

The workflows are configured to use Vault automatically. The key components:

### Workflow Permissions

```yaml
permissions:
  contents: read
  id-token: write  # Required for OIDC
```

### Vault Action Step

```yaml
- name: Fetch secrets from Vault
  uses: hashicorp/vault-action@v3
  with:
    url: https://vault.gostoa.dev
    method: jwt
    role: github-actions
    jwtGithubAudience: sigstore
    exportEnv: true
    secrets: |
      secret/data/e2e/personas/parzival username | PARZIVAL_USER ;
      secret/data/e2e/personas/parzival password | PARZIVAL_PASSWORD
```

## Troubleshooting

### "permission denied" Error

1. Check policy is attached to role:
   ```bash
   vault read auth/jwt/role/github-actions
   ```

2. Verify policy has correct paths:
   ```bash
   vault policy read github-actions
   ```

### "invalid audience" Error

Ensure `jwtGithubAudience` in workflow matches `bound_audiences` in role:
```bash
vault read auth/jwt/role/github-actions | grep bound_audiences
```

### "invalid claims" Error

Check the repository and ref claims:
```bash
vault read auth/jwt/role/github-actions | grep bound_claims
```

### View Vault Audit Logs

```bash
vault audit list
# If audit logging is enabled, check logs for detailed errors
```

## Security Considerations

1. **Short TTLs**: Tokens are valid for only 10-15 minutes
2. **Repository binding**: Only `stoa-platform/stoa` can authenticate
3. **Branch restrictions**: Can be tightened to specific branches if needed
4. **No wildcard policies**: Explicit paths only
5. **Secrets rotation**: Rotate passwords periodically

## Migration from GitHub Secrets

The workflows support both Vault and GitHub Secrets with fallback:

```yaml
env:
  PARZIVAL_USER: ${{ env.PARZIVAL_USER || secrets.PARZIVAL_USER }}
```

This allows gradual migration:
1. Configure Vault with secrets
2. Deploy updated workflows
3. Test that Vault secrets work
4. Remove GitHub Secrets (optional, can keep as backup)
