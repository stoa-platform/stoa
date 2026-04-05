# =============================================================================
# Vault Agent — Docker Sidecar Configuration
# =============================================================================
# Runs alongside Docker Compose services (simulating VPS Vault Agent).
# Auto-authenticates via AppRole, renders secret templates to shared volume.
#
# Prerequisites:
#   - Vault running on K3s (kubectl port-forward -n vault svc/vault 8200:8200)
#   - AppRole credentials at /vault/creds/role-id and /vault/creds/secret-id
#
# Architecture:
#   Docker Compose → vault-agent → Vault (K3s via host.docker.internal:8200)
#                  → renders api-secrets.env → shared volume → CP API
# =============================================================================

vault {
  address = "http://host.docker.internal:8200"
  retry {
    num_retries = 5
  }
}

auto_auth {
  method "approle" {
    config = {
      role_id_file_path   = "/vault/creds/role-id"
      secret_id_file_path = "/vault/creds/secret-id"
      remove_secret_id_file_after_reading = false
    }
  }

  sink "file" {
    config = {
      path = "/vault/token/agent-token"
      mode = 0600
    }
  }
}

# Template: Control Plane API secrets
template {
  source      = "/vault/templates/api-secrets.env.ctmpl"
  destination = "/vault/rendered/api-secrets.env"
  perms       = 0600
  # Re-render when secrets change (poll interval)
  command     = "echo '[vault-agent] api-secrets.env rendered'"
}

# Template: Gateway VPS-like secrets
template {
  source      = "/vault/templates/gateway-vps-secrets.env.ctmpl"
  destination = "/vault/rendered/gateway-vps-secrets.env"
  perms       = 0600
  command     = "echo '[vault-agent] gateway-vps-secrets.env rendered'"
}

# Logging
log_level = "info"

# Telemetry (optional — useful for debugging)
telemetry {
  disable_hostname = true
}
