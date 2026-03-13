# GitHub Actions deploy policy — read SSH keys for deployment workflows
# Auth method: JWT (GitHub OIDC)
# Used by: ops-scripts-deploy.yml, hegemon-deploy.yml

path "stoa/data/ssh/*" {
  capabilities = ["read"]
}
