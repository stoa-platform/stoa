# Admin policy — full access to all STOA secrets
# Used by: rotate-secrets.sh (human-only), migrate-to-vault.sh

# Full access to all secrets
path "stoa/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

# Manage auth methods
path "auth/*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}

# Manage policies
path "sys/policies/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

# Manage audit backends
path "sys/audit*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}

# View system health
path "sys/health" {
  capabilities = ["read", "sudo"]
}

# Manage mounts (engines)
path "sys/mounts/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

# Transit engine for backup encryption
path "transit/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}
