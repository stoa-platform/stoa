#!/usr/bin/env bash
# Run control-plane-api locally with secrets resolved from Vault.
# Replaces plaintext control-plane-api/.env — secrets stay in Vault, never on disk.
#
# Usage:
#   scripts/dev/run-api-local.sh           # uvicorn --reload (default dev)
#   scripts/dev/run-api-local.sh --prod    # no reload
#
# Prereqs:
#   - VAULT_ADDR + VAULT_TOKEN exported (or `vault login` done)
#   - Vault path stoa/dev/control-plane-api populated (see README below)
#   - stoa-postgres container running (docker ps | grep stoa-postgres)

set -euo pipefail

VAULT_PATH="${VAULT_PATH:-stoa/dev/control-plane-api}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
API_DIR="$REPO_ROOT/control-plane-api"

if ! command -v vault >/dev/null 2>&1; then
  echo "ERROR: vault CLI not found. Install with: brew install vault" >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "ERROR: jq not found. Install with: brew install jq" >&2
  exit 1
fi

if [[ -z "${VAULT_ADDR:-}" ]]; then
  export VAULT_ADDR="https://hcvault.gostoa.dev"
fi

if ! vault token lookup >/dev/null 2>&1; then
  echo "ERROR: no valid Vault token. Run 'vault login' first." >&2
  exit 1
fi

echo "→ Fetching secrets from Vault: $VAULT_PATH"
if ! secrets_json="$(vault kv get -format=json "$VAULT_PATH" 2>/dev/null)"; then
  cat >&2 <<EOF
ERROR: Vault path '$VAULT_PATH' not found or inaccessible.

To seed it the first time (human-only, per secrets-management.md):

  vault kv put $VAULT_PATH \\
    DATABASE_URL='postgresql+asyncpg://stoa:<PG_PASSWORD>@localhost:5432/stoa_platform' \\
    KEYCLOAK_URL='https://auth.gostoa.dev' \\
    KEYCLOAK_REALM='stoa' \\
    KEYCLOAK_ADMIN_URL='https://auth.gostoa.dev' \\
    KEYCLOAK_ADMIN_USER='admin' \\
    KEYCLOAK_ADMIN_PASSWORD='<KC_ADMIN_PASS>' \\
    KEYCLOAK_ADMIN_CLIENT_SECRET='<KC_CLIENT_SECRET>' \\
    KAFKA_BOOTSTRAP_SERVERS='localhost:9092' \\
    OPENSEARCH_HOST='localhost' \\
    OPENSEARCH_ADMIN_PASSWORD='<OS_PASS>' \\
    OPENSEARCH_PASSWORD='<OS_PASS>' \\
    OPENSEARCH_VERIFY_CERTS='false' \\
    PROMETHEUS_INTERNAL_URL='http://localhost:9090' \\
    LOKI_INTERNAL_URL='http://localhost:3100' \\
    TEMPO_INTERNAL_URL='http://localhost:3200' \\
    STOA_API_URL='http://localhost:8000' \\
    CHAT_ENABLED='false' \\
    CHAT_PROVIDER_API_KEY=''
EOF
  exit 1
fi

while IFS='=' read -r key value; do
  [[ -z "$key" ]] && continue
  export "$key=$value"
done < <(echo "$secrets_json" | jq -r '.data.data | to_entries[] | "\(.key)=\(.value)"')

echo "→ Secrets loaded (keys: $(echo "$secrets_json" | jq -r '.data.data | keys | join(", ")'))"

cd "$API_DIR"
RELOAD_FLAG="--reload"
if [[ "${1:-}" == "--prod" ]]; then
  RELOAD_FLAG=""
fi

exec uvicorn src.main:app $RELOAD_FLAG --host 0.0.0.0 --port 8000
