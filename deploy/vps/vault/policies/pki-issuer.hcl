# PKI issuer policy — issue mTLS certificates via Vault CA
# Used by: stoa-gateway (gateway-mtls role), K8s cert-manager (service-mesh role)

# Issue certificates (gateway mTLS — 30d TTL)
path "pki_int/issue/gateway-mtls" {
  capabilities = ["create", "update"]
}

# Issue certificates (service mesh — 7d TTL)
path "pki_int/issue/service-mesh" {
  capabilities = ["create", "update"]
}

# Read CA chain (needed for trust bundle distribution)
path "pki_int/ca/pem" {
  capabilities = ["read"]
}
path "pki_int/ca_chain" {
  capabilities = ["read"]
}
path "pki/ca/pem" {
  capabilities = ["read"]
}

# List certificates (informational)
path "pki_int/certs" {
  capabilities = ["list"]
}

# Revoke certificates
path "pki_int/revoke" {
  capabilities = ["create", "update"]
}
