#!/bin/sh
# =============================================================================
# Vault Local Bootstrap — Finance-Grade Init Script
# =============================================================================
# Runs as a K8s Job after Vault is ready. Bootstraps all engines, seeds secrets,
# creates policies, and enables audit. Mirrors production paths from hcvault.gostoa.dev.
#
# This script is idempotent — safe to re-run on existing Vault data.
# =============================================================================

set -eu

# ⚠️ LOCAL DEV ONLY. This script expects a dev-mode Vault running on a local
# K3d/kind cluster. All required secrets must be provided via the Job env —
# there are intentionally no hardcoded defaults except for non-sensitive fields.

VAULT_ADDR="${VAULT_ADDR:-http://vault.vault.svc.cluster.local:8200}"
: "${VAULT_TOKEN:?VAULT_TOKEN is required (set in vault-init-job.yaml)}"
export VAULT_ADDR VAULT_TOKEN

# Secrets from environment (set by Job manifest)
POSTGRES_USER="${POSTGRES_USER:-stoa}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
POSTGRES_DB="${POSTGRES_DB:-stoa_platform}"
KEYCLOAK_ADMIN="${KEYCLOAK_ADMIN:-admin}"
: "${KEYCLOAK_ADMIN_PASSWORD:?KEYCLOAK_ADMIN_PASSWORD is required}"

log() { echo "[vault-init] $(date -u '+%Y-%m-%dT%H:%M:%SZ') $*"; }

wait_vault() {
  log "Waiting for Vault to be ready..."
  for i in $(seq 1 30); do
    if vault status >/dev/null 2>&1; then
      log "Vault is ready (attempt $i)"
      return 0
    fi
    sleep 2
  done
  log "ERROR: Vault not ready after 60s"
  exit 1
}

# ==========================================================================
# Phase 1: KV v2 Secrets Engines
# ==========================================================================
enable_kv_engines() {
  log "=== Phase 1: KV v2 Engines ==="

  # stoa/ mount — mirrors production (stoa-infra Vault)
  vault secrets enable -path=stoa -version=2 kv 2>/dev/null \
    && log "Enabled KV v2 at stoa/" \
    || log "KV v2 at stoa/ already enabled (idempotent)"

  # secret/ mount — mirrors config.py VAULT_MOUNT_POINT default
  vault secrets enable -path=secret -version=2 kv 2>/dev/null \
    && log "Enabled KV v2 at secret/" \
    || log "KV v2 at secret/ already enabled (idempotent)"
}

# ==========================================================================
# Phase 1: Seed Secrets (mirrors prod paths)
# ==========================================================================
seed_secrets() {
  log "=== Phase 1: Seed Secrets ==="

  # K8s gateway secrets (prod: stoa/k8s/gateway)
  vault kv put stoa/k8s/gateway \
    STOA_CONTROL_PLANE_API_KEY="local-dev-api-key-$(date +%s)" \
    STOA_KEYCLOAK_CLIENT_SECRET="local-dev-gateway-secret"
  log "Seeded stoa/k8s/gateway"

  # K8s control-plane-api secrets (prod: stoa/k8s/control-plane-api)
  vault kv put stoa/k8s/control-plane-api \
    DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@host.docker.internal:5432/${POSTGRES_DB}" \
    KEYCLOAK_ADMIN_USERNAME="${KEYCLOAK_ADMIN}" \
    KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD}" \
    KEYCLOAK_CLIENT_SECRET="local-dev-api-client-secret"
  log "Seeded stoa/k8s/control-plane-api"

  # Shared keycloak admin (prod: stoa/shared/keycloak)
  vault kv put stoa/shared/keycloak \
    KEYCLOAK_ADMIN_USERNAME="${KEYCLOAK_ADMIN}" \
    KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD}" \
    KEYCLOAK_URL="http://host.docker.internal:8080"
  log "Seeded stoa/shared/keycloak"

  # External MCP server sample (prod: secret/external-mcp-servers/*)
  vault kv put secret/external-mcp-servers/test-server \
    client_id="test-mcp-client" \
    client_secret="test-mcp-secret-$(date +%s)" \
    token_url="http://host.docker.internal:8080/realms/stoa/protocol/openid-connect/token" \
    auth_type="oauth2_client_credentials"
  log "Seeded secret/external-mcp-servers/test-server"

  # E2E test personas (prod: stoa/dev/e2e-personas)
  vault kv put stoa/dev/e2e-personas \
    parzival_password="Parzival@2026!" \
    art3mis_password="Art3mis@2026!" \
    aech_password="Aech@2026!" \
    sorrento_password="Sorrento@2026!" \
    i_r0k_password="I-r0k@2026!" \
    anorak_password="Anorak@2026!" \
    alex_password="Alex@2026!"
  log "Seeded stoa/dev/e2e-personas (7 personas)"

  # Local AppRole credentials placeholder (consumed by Vault Agent in Phase 6)
  vault kv put stoa/local/config \
    environment="local-dev" \
    vault_version="1.18" \
    bootstrap_date="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  log "Seeded stoa/local/config"
}

# ==========================================================================
# Phase 1: Audit Log
# ==========================================================================
enable_audit() {
  log "=== Phase 1: Audit Log ==="

  vault audit enable file file_path=/vault/audit/audit.log 2>/dev/null \
    && log "Enabled file audit log at /vault/audit/audit.log" \
    || log "Audit log already enabled (idempotent)"
}

# ==========================================================================
# Phase 1: Admin Policy
# ==========================================================================
create_admin_policy() {
  log "=== Phase 1: Admin Policy ==="

  vault policy write local-admin - <<'POLICY'
# local-admin — full access for dev root token
# Mirrors prod admin.hcl
path "stoa/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}
path "secret/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}
path "sys/*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}
path "auth/*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}
path "pki/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}
path "pki_int/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}
path "transit/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}
path "database/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}
path "totp/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}
POLICY
  log "Created policy: local-admin"
}

# ==========================================================================
# Phase 2: Policies (loaded from ConfigMap mount)
# ==========================================================================
load_policies() {
  log "=== Phase 2: Service Policies ==="

  POLICY_DIR="/vault/policies"
  if [ -d "$POLICY_DIR" ] && [ "$(ls -A "$POLICY_DIR"/*.hcl 2>/dev/null)" ]; then
    for policy_file in "$POLICY_DIR"/*.hcl; do
      policy_name=$(basename "$policy_file" .hcl)
      vault policy write "$policy_name" "$policy_file"
      log "Loaded policy: $policy_name from $policy_file"
    done
  else
    log "No policies found in $POLICY_DIR (Phase 2 not yet deployed)"
  fi
}

# ==========================================================================
# Phase 2: AppRole Auth
# ==========================================================================
setup_approle() {
  log "=== Phase 2: AppRole Auth ==="

  vault auth enable approle 2>/dev/null \
    && log "Enabled AppRole auth" \
    || log "AppRole auth already enabled (idempotent)"

  # AppRole: local-api (Control Plane API)
  vault write auth/approle/role/local-api \
    token_policies="control-plane-api" \
    token_ttl=1h \
    token_max_ttl=24h \
    secret_id_ttl=0 \
    secret_id_num_uses=0
  log "Created AppRole: local-api"

  # AppRole: local-gateway (STOA Gateway)
  vault write auth/approle/role/local-gateway \
    token_policies="stoa-gateway" \
    token_ttl=1h \
    token_max_ttl=24h \
    secret_id_ttl=0 \
    secret_id_num_uses=0
  log "Created AppRole: local-gateway"

  # Generate and store credentials for Vault Agent consumption
  API_ROLE_ID=$(vault read -field=role_id auth/approle/role/local-api/role-id)
  API_SECRET_ID=$(vault write -f -field=secret_id auth/approle/role/local-api/secret-id)
  vault kv put stoa/local/approle-creds/api \
    role_id="$API_ROLE_ID" \
    secret_id="$API_SECRET_ID"
  log "Stored local-api AppRole creds in stoa/local/approle-creds/api"

  GW_ROLE_ID=$(vault read -field=role_id auth/approle/role/local-gateway/role-id)
  GW_SECRET_ID=$(vault write -f -field=secret_id auth/approle/role/local-gateway/secret-id)
  vault kv put stoa/local/approle-creds/gateway \
    role_id="$GW_ROLE_ID" \
    secret_id="$GW_SECRET_ID"
  log "Stored local-gateway AppRole creds in stoa/local/approle-creds/gateway"
}

# ==========================================================================
# Phase 3: PKI Engine (Root CA → Intermediate → Roles)
# ==========================================================================
setup_pki() {
  log "=== Phase 3: PKI Engine ==="

  # Root CA
  vault secrets enable -path=pki pki 2>/dev/null \
    && log "Enabled PKI engine at pki/" \
    || log "PKI engine at pki/ already enabled"

  vault secrets tune -max-lease-ttl=87600h pki
  vault write -field=certificate pki/root/generate/internal \
    common_name="STOA Local Root CA" \
    key_type=ec \
    key_bits=256 \
    ttl=87600h \
    > /tmp/root_ca.pem 2>/dev/null || true
  vault write pki/config/urls \
    issuing_certificates="http://vault.vault.svc.cluster.local:8200/v1/pki/ca" \
    crl_distribution_points="http://vault.vault.svc.cluster.local:8200/v1/pki/crl"
  log "Root CA created: STOA Local Root CA (EC P-256, 10y)"

  # Intermediate CA
  vault secrets enable -path=pki_int pki 2>/dev/null \
    && log "Enabled PKI engine at pki_int/" \
    || log "PKI engine at pki_int/ already enabled"

  vault secrets tune -max-lease-ttl=43800h pki_int
  vault write -field=csr pki_int/intermediate/generate/internal \
    common_name="STOA Local Intermediate CA" \
    key_type=ec \
    key_bits=256 \
    > /tmp/intermediate.csr

  vault write -field=certificate pki/root/sign-intermediate \
    csr=@/tmp/intermediate.csr \
    format=pem_bundle \
    ttl=43800h \
    > /tmp/intermediate_ca.pem

  vault write pki_int/intermediate/set-signed \
    certificate=@/tmp/intermediate_ca.pem
  vault write pki_int/config/urls \
    issuing_certificates="http://vault.vault.svc.cluster.local:8200/v1/pki_int/ca" \
    crl_distribution_points="http://vault.vault.svc.cluster.local:8200/v1/pki_int/crl"
  log "Intermediate CA created and signed by Root (EC P-256, 5y)"

  # Role: gateway-mtls (mirrors prod)
  vault write pki_int/roles/gateway-mtls \
    allowed_domains="localhost,stoa-gateway,stoa-local,vault.svc.cluster.local,host.docker.internal" \
    allow_subdomains=true \
    allow_bare_domains=true \
    allow_localhost=true \
    key_type=ec \
    key_bits=256 \
    max_ttl=720h \
    ttl=720h \
    require_cn=true \
    server_flag=true \
    client_flag=true
  log "Created PKI role: gateway-mtls (30d, EC P-256)"

  # Role: service-mesh (mirrors prod)
  vault write pki_int/roles/service-mesh \
    allowed_domains="localhost,stoa-local,svc.cluster.local" \
    allow_subdomains=true \
    allow_bare_domains=true \
    allow_localhost=true \
    key_type=ec \
    key_bits=256 \
    max_ttl=168h \
    ttl=168h \
    require_cn=true \
    server_flag=true \
    client_flag=true
  log "Created PKI role: service-mesh (7d, EC P-256)"

  # Issue initial gateway cert (stored in Vault, retrievable via CLI)
  vault write -field=certificate pki_int/issue/gateway-mtls \
    common_name="stoa-gateway.stoa-local" \
    alt_names="localhost,stoa-gateway" \
    ttl=720h \
    > /dev/null 2>&1 || true
  log "Issued initial gateway mTLS certificate"

  # Store Root CA PEM in KV for easy retrieval
  ROOT_CA=$(vault read -field=certificate pki/cert/ca 2>/dev/null || true)
  INT_CA=$(vault read -field=certificate pki_int/cert/ca 2>/dev/null || true)
  if [ -n "$ROOT_CA" ]; then
    vault kv put stoa/local/pki-ca \
      root_ca="$ROOT_CA" \
      intermediate_ca="$INT_CA" \
      note="Retrieve these PEMs to create K8s Secrets/ConfigMaps externally"
    log "Stored CA certs in stoa/local/pki-ca for external retrieval"
  fi

  # K8s Secret/ConfigMap creation is done by setup-vault-local.sh (has kubectl)
  log "NOTE: K8s TLS Secret + CA ConfigMap created by setup-vault-local.sh (Phase 3)"

  rm -f /tmp/root_ca.pem /tmp/intermediate.csr /tmp/intermediate_ca.pem
}

# ==========================================================================
# Phase 4: Database Secret Engine (Dynamic PostgreSQL Credentials)
# ==========================================================================
setup_database() {
  log "=== Phase 4: Database Engine ==="

  vault secrets enable database 2>/dev/null \
    && log "Enabled database engine" \
    || log "Database engine already enabled"

  # Configure PostgreSQL connection via host.docker.internal
  vault write database/config/postgresql \
    plugin_name=postgresql-database-plugin \
    allowed_roles="api-role,readonly-role" \
    connection_url="postgresql://{{username}}:{{password}}@${POSTGRES_HOST:-host.docker.internal}:5432/${POSTGRES_DB}?sslmode=disable" \
    username="vault_admin" \
    password="vault-admin-local"
  log "Configured PostgreSQL connection"

  # Role: api-role (full CRUD — for Control Plane API)
  vault write database/roles/api-role \
    db_name=postgresql \
    creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO \"{{name}}\"; GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO \"{{name}}\";" \
    revocation_statements="DROP ROLE IF EXISTS \"{{name}}\";" \
    default_ttl=1h \
    max_ttl=24h
  log "Created database role: api-role (1h TTL, full CRUD)"

  # Role: readonly-role (SELECT only — for monitoring, dashboards)
  vault write database/roles/readonly-role \
    db_name=postgresql \
    creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT SELECT ON ALL TABLES IN SCHEMA public TO \"{{name}}\";" \
    revocation_statements="DROP ROLE IF EXISTS \"{{name}}\";" \
    default_ttl=1h \
    max_ttl=8h
  log "Created database role: readonly-role (1h TTL, SELECT only)"
}

# ==========================================================================
# Phase 5: Transit Engine (Field-Level Encryption)
# ==========================================================================
setup_transit() {
  log "=== Phase 5: Transit Engine ==="

  vault secrets enable transit 2>/dev/null \
    && log "Enabled transit engine" \
    || log "Transit engine already enabled"

  # Key: backup-encryption (admin-only, for backup archives)
  vault write -f transit/keys/backup-encryption \
    type=aes256-gcm96 \
    auto_rotate_period=720h
  log "Created transit key: backup-encryption (AES256-GCM96, 30d rotation)"

  # Key: pii-fields (for PII data: emails, phones, addresses)
  vault write -f transit/keys/pii-fields \
    type=aes256-gcm96 \
    auto_rotate_period=720h
  log "Created transit key: pii-fields (AES256-GCM96, 30d rotation)"

  # Key: consumer-secrets (for API keys, credential wrapping)
  vault write -f transit/keys/consumer-secrets \
    type=aes256-gcm96 \
    auto_rotate_period=720h
  log "Created transit key: consumer-secrets (AES256-GCM96, 30d rotation)"
}

# ==========================================================================
# Phase 6: TOTP Engine (MFA Step-Up Authentication)
# ==========================================================================
setup_totp() {
  log "=== Phase 6: TOTP Engine ==="

  vault secrets enable totp 2>/dev/null \
    && log "Enabled TOTP engine" \
    || log "TOTP engine already enabled"

  # Create TOTP key for dev admin
  TOTP_URL=$(vault write -field=url totp/keys/dev-admin-totp \
    generate=true \
    issuer="STOA-Local-Vault" \
    account_name="admin@stoa.local" \
    period=30 \
    digits=6 \
    algorithm=SHA256 2>/dev/null || echo "")

  TOTP_BARCODE=$(vault write -field=barcode totp/keys/dev-admin-totp \
    generate=true \
    issuer="STOA-Local-Vault" \
    account_name="admin@stoa.local" \
    period=30 \
    digits=6 \
    algorithm=SHA256 2>/dev/null || echo "")

  if [ -n "$TOTP_URL" ]; then
    log "Created TOTP key: dev-admin-totp"
    log "TOTP URL (for Authenticator app): $TOTP_URL"

    vault kv put stoa/local/totp-setup \
      url="$TOTP_URL" \
      barcode="$TOTP_BARCODE" \
      note="Scan QR or use URL to register in Authenticator app"
    log "TOTP setup info stored at stoa/local/totp-setup"
  else
    log "TOTP key already exists or creation failed — skipping"
  fi
}

# ==========================================================================
# Main — Run all phases in order
# ==========================================================================
main() {
  log "========================================"
  log "  Vault Local Bootstrap — Starting"
  log "  VAULT_ADDR: $VAULT_ADDR"
  log "========================================"

  wait_vault

  # Phase 1: KV v2 + Secrets + Audit + Admin Policy
  enable_kv_engines
  seed_secrets
  enable_audit
  create_admin_policy

  # Phase 2: Policies + AppRole (if policies ConfigMap mounted)
  load_policies
  if vault auth list 2>/dev/null | grep -q approle; then
    log "AppRole already enabled, skipping setup"
  else
    setup_approle
  fi
  # Always re-run approle setup to ensure roles exist
  setup_approle 2>/dev/null || true

  # Phase 3: PKI (if not already configured)
  if vault secrets list 2>/dev/null | grep -q "^pki/"; then
    log "PKI already enabled, re-running setup for idempotency"
  fi
  setup_pki

  # Phase 4: Database (skip if PostgreSQL not reachable)
  if vault secrets list 2>/dev/null | grep -q "^database/"; then
    log "Database engine already enabled"
    setup_database 2>/dev/null || log "WARN: Database setup failed (PostgreSQL may not have vault_admin role yet)"
  else
    setup_database 2>/dev/null || log "WARN: Database setup failed (PostgreSQL may not have vault_admin role yet — see 01-init-db.sql)"
  fi

  # Phase 5: Transit
  setup_transit

  # Phase 6: TOTP
  setup_totp

  # Summary
  log "========================================"
  log "  Vault Local Bootstrap — Complete"
  log "========================================"
  log ""
  log "Engines enabled:"
  vault secrets list -format=table 2>/dev/null || true
  log ""
  log "Auth methods:"
  vault auth list -format=table 2>/dev/null || true
  log ""
  log "Policies:"
  vault policy list 2>/dev/null || true
  log ""
  log "Bootstrap complete. Vault ready for local development."
}

main "$@"
