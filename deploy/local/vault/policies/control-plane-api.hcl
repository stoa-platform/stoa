# =============================================================================
# Policy: control-plane-api
# =============================================================================
# Grants the Control Plane API access to its own secrets, dynamic DB creds,
# and Transit encryption for PII fields. Denies access to gateway secrets
# and admin-only resources (separation of concern).
# =============================================================================

# KV v2 — own secrets
path "stoa/data/k8s/control-plane-api" {
  capabilities = ["read"]
}
path "stoa/metadata/k8s/control-plane-api" {
  capabilities = ["read", "list"]
}

# KV v2 — shared secrets (read-only)
path "stoa/data/shared/*" {
  capabilities = ["read"]
}

# KV v2 — MCP server credentials (CRUD)
path "secret/data/external-mcp-servers/*" {
  capabilities = ["create", "read", "update", "delete"]
}
path "secret/metadata/external-mcp-servers/*" {
  capabilities = ["read", "list", "delete"]
}

# Database — dynamic PostgreSQL credentials
path "database/creds/api-role" {
  capabilities = ["read"]
}

# Transit — PII field encryption/decryption
path "transit/encrypt/pii-fields" {
  capabilities = ["update"]
}
path "transit/decrypt/pii-fields" {
  capabilities = ["update"]
}

# Transit — consumer secrets encryption/decryption
path "transit/encrypt/consumer-secrets" {
  capabilities = ["update"]
}
path "transit/decrypt/consumer-secrets" {
  capabilities = ["update"]
}

# Transit — key info (read-only, no rotate)
path "transit/keys/pii-fields" {
  capabilities = ["read"]
}
path "transit/keys/consumer-secrets" {
  capabilities = ["read"]
}

# TOTP — validate codes (for step-up auth verification)
path "totp/code/dev-admin-totp" {
  capabilities = ["update"]
}

# Health check
path "sys/health" {
  capabilities = ["read"]
}
