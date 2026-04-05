# =============================================================================
# Policy: pki-issuer
# =============================================================================
# Issue certificates from the intermediate CA. Used by services that need
# to request their own mTLS certs (e.g., Vault Agent cert renewal).
# =============================================================================

# Issue certs from intermediate CA
path "pki_int/issue/*" {
  capabilities = ["create", "update"]
}

# Read CA chain
path "pki_int/ca/pem" {
  capabilities = ["read"]
}
path "pki_int/ca_chain" {
  capabilities = ["read"]
}
path "pki/ca/pem" {
  capabilities = ["read"]
}

# CRL
path "pki_int/crl" {
  capabilities = ["read"]
}
