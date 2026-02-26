#!/usr/bin/env bash
# =============================================================================
# STOA Platform — VPS Inventory
# =============================================================================
# Source of truth for VPS fleet. All deploy scripts MUST source this file
# instead of hardcoding IPs and SSH keys.
#
# Usage:
#   source "$(dirname "$0")/vps-inventory.sh"
#   ssh_to kong-vps "docker ps"
#   for_each_vps "uptime"
# =============================================================================

# --- SSH Key (per-device, overridable via env) ---
STOA_SSH_KEY="${STOA_SSH_KEY:-$HOME/.ssh/id_ed25519_stoa}"

# --- VPS Fleet ---
# Format: NAME|IP|USER|PURPOSE
VPS_FLEET=(
  "kong-vps|51.83.45.13|debian|Kong + STOA gateway (Arena benchmark)"
  "gravitee-vps|54.36.209.237|debian|Gravitee APIM v4 (Arena benchmark)"
  "n8n-vps|51.254.139.205|debian|n8n + PocketBase + Healthchecks"
  # HEGEMON workers are dynamic — use hegemon/workers.txt
)

# --- Cloudflare Access (sourced from env or Infisical) ---
# Set these in ~/.zprofile or export before running scripts.
# Empty = no CF Access headers sent (backward compatible).
CF_ACCESS_CLIENT_ID="${CF_ACCESS_CLIENT_ID:-}"
CF_ACCESS_CLIENT_SECRET="${CF_ACCESS_CLIENT_SECRET:-}"

# --- Infisical ---
INFISICAL_URL="${INFISICAL_URL:-https://vault.gostoa.dev}"
INFISICAL_PROJECT_ID="${INFISICAL_PROJECT_ID:-97972ffc-990b-4d28-9c4d-0664d217f03b}"

# =============================================================================
# Helper functions
# =============================================================================

# Get VPS field by name: vps_get kong-vps ip → 51.83.45.13
vps_get() {
  local name="$1" field="$2"
  for entry in "${VPS_FLEET[@]}"; do
    IFS='|' read -r n ip user purpose <<< "$entry"
    if [ "$n" = "$name" ]; then
      case "$field" in
        ip)      echo "$ip" ;;
        user)    echo "$user" ;;
        purpose) echo "$purpose" ;;
        *)       echo "Unknown field: $field" >&2; return 1 ;;
      esac
      return 0
    fi
  done
  echo "Unknown VPS: $name" >&2
  return 1
}

# SSH to a named VPS: ssh_to kong-vps "docker ps"
ssh_to() {
  local name="$1"; shift
  local ip user
  ip=$(vps_get "$name" ip)
  user=$(vps_get "$name" user)
  ssh -i "$STOA_SSH_KEY" -o ConnectTimeout=10 "${user}@${ip}" "$@"
}

# SCP to a named VPS: scp_to kong-vps local_file remote_path
scp_to() {
  local name="$1" local_file="$2" remote_path="$3"
  local ip user
  ip=$(vps_get "$name" ip)
  user=$(vps_get "$name" user)
  scp -i "$STOA_SSH_KEY" "$local_file" "${user}@${ip}:${remote_path}"
}

# Run command on all VPS: for_each_vps "uptime"
for_each_vps() {
  local cmd="$1"
  for entry in "${VPS_FLEET[@]}"; do
    IFS='|' read -r name ip user purpose <<< "$entry"
    echo "=== $name ($ip) ==="
    ssh -i "$STOA_SSH_KEY" -o ConnectTimeout=10 "${user}@${ip}" "$cmd" 2>&1 || echo "[FAIL] $name unreachable"
    echo ""
  done
}

# Build curl headers for Infisical (CF Access + Bearer)
# Usage: infisical_curl_headers "$INFISICAL_TOKEN" → array of -H flags
infisical_curl_headers() {
  local token="${1:-$INFISICAL_TOKEN}"
  local headers=(-H "Authorization: Bearer ${token}" -H "Content-Type: application/json")
  if [ -n "$CF_ACCESS_CLIENT_ID" ] && [ -n "$CF_ACCESS_CLIENT_SECRET" ]; then
    headers+=(-H "CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}")
    headers+=(-H "CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}")
  fi
  echo "${headers[@]}"
}

# Curl wrapper for Infisical API with CF Access headers
# Usage: infisical_curl GET "/api/v3/secrets/raw?..." "$INFISICAL_TOKEN"
infisical_curl() {
  local method="$1" path="$2" token="${3:-${INFISICAL_TOKEN:-}}"
  local -a headers=(-H "Authorization: Bearer ${token}" -H "Content-Type: application/json")
  if [ -n "$CF_ACCESS_CLIENT_ID" ] && [ -n "$CF_ACCESS_CLIENT_SECRET" ]; then
    headers+=(-H "CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}")
    headers+=(-H "CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}")
  fi

  if [ "$#" -ge 4 ]; then
    # Has body (4th arg)
    curl -sf -X "$method" "${INFISICAL_URL}${path}" "${headers[@]}" -d "$4"
  else
    curl -sf -X "$method" "${INFISICAL_URL}${path}" "${headers[@]}"
  fi
}
