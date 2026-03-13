#!/bin/bash
# HEGEMON Vault Secrets Loader
# Fetches secrets dynamically from HashiCorp Vault at shell startup.
# Secrets are NEVER stored on disk — only in memory (env vars).
# Replaces infisical-loader.sh (Phase 3, CAB-1799).
#
# Usage: source ~/.local/bin/vault-loader.sh
#   Called automatically from ~/.bashrc
#
# Deploy: scp vault-loader.sh hegemon@<host>:~/.local/bin/vault-loader.sh
#
# Prerequisites:
#   - ~/.hegemon/vault-role-id     (AppRole role ID)
#   - ~/.hegemon/vault-secret-id   (AppRole secret ID)
#   - VAULT_ADDR env var or default https://hcvault.gostoa.dev

VAULT_ADDR="${VAULT_ADDR:-https://hcvault.gostoa.dev}"

_HEGEMON_ROLE_FILE="${HOME}/.hegemon/vault-role-id"
_HEGEMON_SECRET_FILE="${HOME}/.hegemon/vault-secret-id"

_vault_fetch() {
  local path="$1"
  local key="$2"

  local val
  val=$(curl -sf "${VAULT_ADDR}/v1/stoa/data/${path}" \
    -H "X-Vault-Token: ${_HEGEMON_VAULT_TOKEN}" 2>/dev/null \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['data']['${key}'])" 2>/dev/null)

  echo "$val"
}

_hegemon_load_secrets() {
  # Read AppRole credentials from protected files
  if [ ! -f "$_HEGEMON_ROLE_FILE" ] || [ ! -f "$_HEGEMON_SECRET_FILE" ]; then
    echo "[hegemon] Vault credentials not found — falling back to env vars" >&2
    return 0
  fi
  local role_id secret_id
  role_id=$(cat "$_HEGEMON_ROLE_FILE")
  secret_id=$(cat "$_HEGEMON_SECRET_FILE")

  # Authenticate via AppRole (short-lived token, 24h TTL)
  _HEGEMON_VAULT_TOKEN=$(curl -sf -X POST "${VAULT_ADDR}/v1/auth/approle/login" \
    -H "Content-Type: application/json" \
    -d "{\"role_id\": \"${role_id}\", \"secret_id\": \"${secret_id}\"}" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['auth']['client_token'])" 2>/dev/null)

  if [ -z "$_HEGEMON_VAULT_TOKEN" ]; then
    echo "[hegemon] Vault AppRole auth failed — falling back to env vars" >&2
    return 0
  fi

  # Fetch secrets into env vars (memory only, never disk).
  # Per-worker API key: try vps/hegemon/<hostname> first,
  # fallback to shared/anthropic if worker-specific path fails.
  local _hostname
  _hostname=$(hostname -s)
  local _worker_key
  _worker_key=$(_vault_fetch "vps/hegemon" "${_hostname}_ANTHROPIC_API_KEY" 2>/dev/null)
  if [ -n "$_worker_key" ] && [ "$_worker_key" != "None" ]; then
    export ANTHROPIC_API_KEY="$_worker_key"
    echo "[hegemon] API key loaded from worker-specific path"
  else
    local _shared_key
    _shared_key=$(_vault_fetch "shared/anthropic" "ANTHROPIC_API_KEY")
    if [ -n "$_shared_key" ] && [ "$_shared_key" != "None" ]; then
      export ANTHROPIC_API_KEY="$_shared_key"
      echo "[hegemon] API key loaded from shared/anthropic"
    else
      echo "[hegemon] API key: using pre-existing env (Vault paths not found)" >&2
    fi
  fi

  local _val
  _val=$(_vault_fetch "shared/slack" "SLACK_WEBHOOK_URL")
  [ -n "$_val" ] && [ "$_val" != "None" ] && export SLACK_WEBHOOK_URL="$_val"

  _val=$(_vault_fetch "vps/pocketbase" "PB_ADMIN_PASSWORD")
  [ -n "$_val" ] && [ "$_val" != "None" ] && export HEGEMON_REMOTE_PASSWORD="$_val"
  export HEGEMON_REMOTE_URL="${HEGEMON_REMOTE_URL:-https://state.gostoa.dev}"
  export HEGEMON_REMOTE_EMAIL="${HEGEMON_REMOTE_EMAIL:-admin@gostoa.dev}"

  _val=$(_vault_fetch "shared/github" "GITHUB_PAT")
  [ -n "$_val" ] && [ "$_val" != "None" ] && export GH_TOKEN="$_val"

  _val=$(_vault_fetch "shared/github" "LINEAR_API_KEY")
  [ -n "$_val" ] && [ "$_val" != "None" ] && export LINEAR_API_KEY="$_val"

  # Route Claude API calls through STOA Gateway
  export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-https://mcp.gostoa.dev}"

  # Clear token from memory
  unset _HEGEMON_VAULT_TOKEN

  # Validate
  if [ -n "${ANTHROPIC_API_KEY:-}" ] && [ -n "${SLACK_WEBHOOK_URL:-}" ] && [ -n "${LINEAR_API_KEY:-}" ]; then
    echo "[hegemon] Secrets loaded from Vault (5 vars)"
  else
    echo "[hegemon] WARNING: Some secrets failed to load from Vault" >&2
  fi
}

# Auto-load on source
if [ -f "$_HEGEMON_ROLE_FILE" ]; then
  _hegemon_load_secrets
fi
