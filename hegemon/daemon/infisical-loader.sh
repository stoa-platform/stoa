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

# Client secret is the ONLY credential stored on disk (in ~/.hegemon/infisical-secret)
_HEGEMON_CS_FILE="${HOME}/.hegemon/infisical-secret"

_infisical_fetch() {
  local path="$1" key="$2"
  local encoded_path
  encoded_path=$(python3 -c "import urllib.parse; print(urllib.parse.quote('${path}', safe=''))" 2>/dev/null)

  local val
  val=$(curl -sf "${INFISICAL_URL}/api/v3/secrets/raw/${key}?workspaceId=${INFISICAL_WORKSPACE}&environment=${INFISICAL_ENV}&secretPath=${encoded_path}" \
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
  _HEGEMON_TOKEN=$(curl -sf -X POST "${INFISICAL_URL}/api/v1/auth/universal-auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"clientId\": \"${INFISICAL_CLIENT_ID}\", \"clientSecret\": \"${client_secret}\"}" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['accessToken'])" 2>/dev/null)

  if [ -z "$_HEGEMON_TOKEN" ]; then
    echo "[hegemon] Infisical auth failed — secrets not loaded" >&2
    return 1
  fi

  # Fetch secrets into env vars (memory only, never disk)
  export ANTHROPIC_API_KEY=$(_infisical_fetch "/anthropic" "ANTHROPIC_API_KEY")
  export SLACK_WEBHOOK_URL=$(_infisical_fetch "/n8n" "SLACK_WEBHOOK_URL")
  export HEGEMON_REMOTE_PASSWORD=$(_infisical_fetch "/pocketbase" "PB_ADMIN_PASSWORD")
  export HEGEMON_REMOTE_URL="https://state.gostoa.dev"
  export HEGEMON_REMOTE_EMAIL="admin@gostoa.dev"
  export LINEAR_API_KEY=$(_infisical_fetch "/n8n" "LINEAR_API_KEY")
  export GH_TOKEN=$(_infisical_fetch "/n8n" "GITHUB_PAT")

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
