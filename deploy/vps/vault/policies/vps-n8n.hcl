# VPS n8n policy — read secrets for n8n, Netbox, PocketBase
# Used by: Vault Agent on n8n VPS (51.254.139.205)

path "stoa/data/vps/n8n" {
  capabilities = ["read"]
}

path "stoa/data/vps/netbox" {
  capabilities = ["read"]
}

path "stoa/data/vps/pocketbase" {
  capabilities = ["read"]
}

path "stoa/data/shared/slack" {
  capabilities = ["read"]
}

path "stoa/data/shared/github" {
  capabilities = ["read"]
}
