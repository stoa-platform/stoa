# HashiCorp Vault — Server Configuration
# Backend: file (simple, no external deps)
# Listener: TCP on 0.0.0.0:8200 (TLS terminated by Caddy)

storage "file" {
  path = "/vault/data"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = true  # TLS handled by Caddy reverse proxy
}

# API address — used by Vault to construct redirect URLs
api_addr = "https://hcv.gostoa.dev"

# Cluster address — single node, not clustered
cluster_addr = "https://127.0.0.1:8201"

# UI enabled for admin access
ui = true

# Audit log — file backend
# Enabled via CLI after init: vault audit enable file file_path=/vault/logs/audit.log

# Telemetry — Prometheus metrics (optional, for Grafana)
telemetry {
  prometheus_retention_time = "24h"
  disable_hostname          = true
}

# Max lease TTL — 768h (32 days)
max_lease_ttl = "768h"

# Default lease TTL — 24h
default_lease_ttl = "24h"
