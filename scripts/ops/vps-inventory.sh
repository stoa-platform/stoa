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
# IPs sourced from env vars — see stoa-infra/docs/carto/dns-inventory.md for values.
# Set all VPS_*_IP variables before sourcing this file.
# Format: NAME|IP|USER|PURPOSE
VPS_FLEET=(
  "kong-vps|${VPS_KONG_IP:?Set VPS_KONG_IP}|debian|Kong + STOA gateway (Arena benchmark)"
  "gravitee-vps|${VPS_GRAVITEE_IP:?Set VPS_GRAVITEE_IP}|debian|Gravitee APIM v4 (Arena benchmark)"
  "n8n-vps|${VPS_N8N_IP:?Set VPS_N8N_IP}|debian|n8n + PocketBase + Healthchecks"
  "webmethods-vps|${VPS_WEBMETHODS_IP:?Set VPS_WEBMETHODS_IP}|debian|webMethods API Gateway trial (vps-wm.gostoa.dev)"
  "bench-vps|${VPS_BENCH_IP:?Set VPS_BENCH_IP}|debian|OpenSearch bench + Arena runner (STOA-bench)"
  # HEGEMON workers are dynamic — use hegemon/workers.txt
)

# =============================================================================
# Helper functions
# =============================================================================

# Get VPS field by name: vps_get kong-vps ip → returns VPS_KONG_IP value
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
