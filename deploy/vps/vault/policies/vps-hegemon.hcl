# VPS HEGEMON policy — read secrets for HEGEMON workers
# Used by: Vault Agent on 5x Contabo VPS

path "stoa/data/vps/hegemon" {
  capabilities = ["read"]
}

path "stoa/data/shared/anthropic" {
  capabilities = ["read"]
}

path "stoa/data/shared/slack" {
  capabilities = ["read"]
}

path "stoa/data/shared/github" {
  capabilities = ["read"]
}
