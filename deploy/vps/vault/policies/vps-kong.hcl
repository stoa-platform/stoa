# VPS Kong policy — read secrets for Kong gateway
# Used by: Vault Agent on Kong VPS (51.83.45.13)

path "stoa/data/vps/kong" {
  capabilities = ["read"]
}

path "stoa/data/vps/arena" {
  capabilities = ["read"]
}
