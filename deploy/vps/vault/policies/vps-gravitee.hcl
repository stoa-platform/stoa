# VPS Gravitee policy — read secrets for Gravitee APIM
# Used by: Vault Agent on Gravitee VPS (54.36.209.237)

path "stoa/data/vps/gravitee" {
  capabilities = ["read"]
}
