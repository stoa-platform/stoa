# K8s ESO policy — read-only access to K8s secrets
# Used by: External Secrets Operator via Kubernetes auth

path "stoa/data/k8s/*" {
  capabilities = ["read"]
}

path "stoa/metadata/k8s/*" {
  capabilities = ["list", "read"]
}

# Also read shared secrets (e.g., Keycloak admin for init containers)
path "stoa/data/shared/*" {
  capabilities = ["read"]
}

path "stoa/metadata/shared/*" {
  capabilities = ["list", "read"]
}
