# =============================================================================
# Policy: stoa-gateway
# =============================================================================
# Grants the STOA Gateway (Rust) access to its own secrets, PKI cert issuance,
# and Transit encryption for consumer secrets. Denies access to API secrets
# and admin resources (separation of concern).
# =============================================================================

# KV v2 — own secrets
path "stoa/data/k8s/gateway" {
  capabilities = ["read"]
}
path "stoa/metadata/k8s/gateway" {
  capabilities = ["read", "list"]
}

# PKI — issue mTLS certificates
path "pki_int/issue/gateway-mtls" {
  capabilities = ["create", "update"]
}
path "pki_int/ca/pem" {
  capabilities = ["read"]
}
path "pki/ca/pem" {
  capabilities = ["read"]
}

# Transit — consumer secrets encryption
path "transit/encrypt/consumer-secrets" {
  capabilities = ["update"]
}
path "transit/decrypt/consumer-secrets" {
  capabilities = ["update"]
}
path "transit/keys/consumer-secrets" {
  capabilities = ["read"]
}

# Health check
path "sys/health" {
  capabilities = ["read"]
}
