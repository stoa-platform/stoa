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
