#!/bin/bash
# HEGEMON Infisical Secrets Loader
# Fetches secrets dynamically from Infisical at shell startup.
# Secrets are NEVER stored on disk — only in memory (env vars).
#
# Usage: source ~/.local/bin/infisical-loader.sh
#   Called automatically from ~/.bashrc
#
# Deploy: scp infisical-loader.sh hegemon@<host>:~/.local/bin/infisical-loader.sh

INFISICAL_URL="https://vault.gostoa.dev"
INFISICAL_CLIENT_ID="6e36fb1e-423f-4240-84d8-81d4945a2e8c"
INFISICAL_WORKSPACE="97972ffc-990b-4d28-9c4d-0664d217f03b"
INFISICAL_ENV="prod"

# Force IPv4: Cloudflare proxy forwards client IPv6 to Infisical backend,
# but Infisical Machine Identity IP allowlist only has IPv4 entries.
_CURL="curl -4"

# Client secret is the ONLY credential stored on disk (in ~/.hegemon/infisical-secret)
_HEGEMON_CS_FILE="${HOME}/.hegemon/infisical-secret"

# Cloudflare Access headers (vault.gostoa.dev is behind CF Access).
# CF_ACCESS_CLIENT_ID and CF_ACCESS_CLIENT_SECRET must be set in the environment
# (typically sourced from ~/.env.hegemon before this script).
_cf_access_headers() {
  if [ -n "${CF_ACCESS_CLIENT_ID:-}" ] && [ -n "${CF_ACCESS_CLIENT_SECRET:-}" ]; then
    echo "-H CF-Access-Client-Id:${CF_ACCESS_CLIENT_ID} -H CF-Access-Client-Secret:${CF_ACCESS_CLIENT_SECRET}"
  fi
}

_infisical_fetch() {
  local path="$1" key="$2"
  local encoded_path
  encoded_path=$(python3 -c "import urllib.parse; print(urllib.parse.quote('${path}', safe=''))" 2>/dev/null)

  local val
  # shellcheck disable=SC2046
  val=$($_CURL -sf $(_cf_access_headers) \
    "${INFISICAL_URL}/api/v3/secrets/raw/${key}?workspaceId=${INFISICAL_WORKSPACE}&environment=${INFISICAL_ENV}&secretPath=${encoded_path}" \
    -H "Authorization: Bearer ${_HEGEMON_TOKEN}" 2>/dev/null \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['secret']['secretValue'])" 2>/dev/null)

  echo "$val"
}

_hegemon_load_secrets() {
  # Read client secret from protected file
  if [ ! -f "$_HEGEMON_CS_FILE" ]; then
    return 1
  fi
  local client_secret
  client_secret=$(cat "$_HEGEMON_CS_FILE")

  # Authenticate (get short-lived token, 24h TTL)
  # shellcheck disable=SC2046
  _HEGEMON_TOKEN=$($_CURL -sf -X POST $(_cf_access_headers) \
    "${INFISICAL_URL}/api/v1/auth/universal-auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"clientId\": \"${INFISICAL_CLIENT_ID}\", \"clientSecret\": \"${client_secret}\"}" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['accessToken'])" 2>/dev/null)

  if [ -z "$_HEGEMON_TOKEN" ]; then
    echo "[hegemon] Infisical auth failed — falling back to env vars" >&2
    return 0
  fi

  # Fetch secrets into env vars (memory only, never disk).
  # Only overwrite if Infisical returns a value — preserves ~/.env.hegemon fallbacks.
  #
  # Per-worker API key: try /hegemon/<hostname>/ANTHROPIC_API_KEY first,
  # fallback to shared /anthropic/ANTHROPIC_API_KEY if worker-specific path fails.
  # This allows 1 API key per worker to avoid single-key quota exhaustion.
  local _worker_path="/hegemon/$(hostname -s)"
  local _worker_key
  _worker_key=$(_infisical_fetch "$_worker_path" "ANTHROPIC_API_KEY")
  if [ -n "$_worker_key" ]; then
    export ANTHROPIC_API_KEY="$_worker_key"
    echo "[hegemon] API key loaded from worker path: $_worker_path"
  else
    local _shared_key
    _shared_key=$(_infisical_fetch "/anthropic" "ANTHROPIC_API_KEY")
    if [ -n "$_shared_key" ]; then
      export ANTHROPIC_API_KEY="$_shared_key"
      echo "[hegemon] API key loaded from shared path: /anthropic"
    else
      echo "[hegemon] API key: using pre-existing env (Infisical paths not found)"
    fi
  fi

  local _val
  _val=$(_infisical_fetch "/n8n" "SLACK_WEBHOOK_URL")
  [ -n "$_val" ] && export SLACK_WEBHOOK_URL="$_val"
  _val=$(_infisical_fetch "/pocketbase" "PB_ADMIN_PASSWORD")
  [ -n "$_val" ] && export HEGEMON_REMOTE_PASSWORD="$_val"
  export HEGEMON_REMOTE_URL="https://state.gostoa.dev"
  export HEGEMON_REMOTE_EMAIL="admin@gostoa.dev"
  _val=$(_infisical_fetch "/n8n" "LINEAR_API_KEY")
  [ -n "$_val" ] && export LINEAR_API_KEY="$_val"
  _val=$(_infisical_fetch "/n8n" "GITHUB_PAT")
  [ -n "$_val" ] && export GH_TOKEN="$_val"

  # Clear token from memory
  unset _HEGEMON_TOKEN

  # Validate
  if [ -n "$ANTHROPIC_API_KEY" ] && [ -n "$SLACK_WEBHOOK_URL" ] && [ -n "$LINEAR_API_KEY" ]; then
    echo "[hegemon] Secrets loaded from Infisical (5 vars)"
  else
    echo "[hegemon] WARNING: Some secrets failed to load" >&2
  fi
}

# Auto-load on source (only in interactive shells or explicit calls)
if [ -f "$_HEGEMON_CS_FILE" ]; then
  _hegemon_load_secrets
fi
