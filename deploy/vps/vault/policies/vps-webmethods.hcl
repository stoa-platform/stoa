# VPS webMethods policy — read secrets for webMethods API Gateway
# Used by: Vault Agent on webMethods VPS (51.255.201.17)

path "stoa/data/vps/webmethods" {
  capabilities = ["read"]
}

path "stoa/data/shared/keycloak" {
  capabilities = ["read"]
}
