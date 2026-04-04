# =============================================================================
# Policy: readonly
# =============================================================================
# Read-only access to all stoa KV secrets. Used by monitoring services
# (Grafana, Prometheus) and readonly database roles.
# =============================================================================

# KV v2 — read all stoa secrets
path "stoa/data/*" {
  capabilities = ["read"]
}
path "stoa/metadata/*" {
  capabilities = ["read", "list"]
}

# Database — readonly credentials
path "database/creds/readonly-role" {
  capabilities = ["read"]
}

# Health check
path "sys/health" {
  capabilities = ["read"]
}
