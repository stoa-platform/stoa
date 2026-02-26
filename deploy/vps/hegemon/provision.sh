#!/usr/bin/env bash
# Provision a HEGEMON worker VPS on OVH via API.
#
# Prerequisites:
#   - OVH API credentials in environment (or from Infisical /ovh)
#   - jq installed locally
#
# Usage: ./provision.sh [worker-name]
#   Default: hegemon-worker-1
set -euo pipefail

WORKER_NAME="${1:-hegemon-worker-1}"
DATACENTER="gra"
OS_ID="debian12_64"
VPS_OFFER="vps-1"    # VPS 2026 gen: 4 vCPU, 8GB, 75GB NVMe, €4.49/mo

# OVH API credentials (from env or Infisical)
: "${OVH_APPLICATION_KEY:?Set OVH_APPLICATION_KEY from Infisical /ovh}"
: "${OVH_APPLICATION_SECRET:?Set OVH_APPLICATION_SECRET from Infisical /ovh}"
: "${OVH_CONSUMER_KEY:?Set OVH_CONSUMER_KEY from Infisical /ovh}"

OVH_API="https://eu.api.ovh.com/1.0"

# --- OVH API signature helper ---
ovh_request() {
  local method="$1" path="$2" body="${3:-}"
  local url="${OVH_API}${path}"
  local timestamp
  timestamp=$(curl -s "${OVH_API}/auth/time")
  local to_sign="${OVH_APPLICATION_SECRET}+${OVH_CONSUMER_KEY}+${method}+${url}+${body}+${timestamp}"
  local signature
  signature="\$1\$$(printf '%s' "$to_sign" | sha1sum | cut -d' ' -f1)"

  curl -s -X "$method" "$url" \
    -H "X-Ovh-Application: ${OVH_APPLICATION_KEY}" \
    -H "X-Ovh-Consumer: ${OVH_CONSUMER_KEY}" \
    -H "X-Ovh-Timestamp: ${timestamp}" \
    -H "X-Ovh-Signature: ${signature}" \
    -H "Content-Type: application/json" \
    ${body:+-d "$body"}
}

echo "=== HEGEMON VPS Provisioning ==="
echo "  Worker: ${WORKER_NAME}"
echo "  Offer:  ${VPS_OFFER} (4 vCPU, 8GB, 75GB NVMe)"
echo "  DC:     ${DATACENTER}"
echo "  OS:     Debian 12"
echo ""

# Step 1: List existing VPS to check for duplicates
echo "[1/3] Checking existing VPS..."
EXISTING=$(ovh_request GET "/vps")
echo "  Current VPS: $(echo "$EXISTING" | jq -r '.[]' | wc -l | tr -d ' ') instances"

# Step 2: List available VPS offers
echo "[2/3] Listing available offers..."
echo "  Note: VPS ordering requires OVH Manager or /order API."
echo "  Use OVH Manager: https://www.ovh.com/manager/#/dedicated/vps"
echo ""
echo "  Recommended: VPS Starter 2026 (renamed VPS-1)"
echo "    - 4 vCPU, 8 GB RAM, 75 GB NVMe"
echo "    - Datacenter: GRA (Gravelines)"
echo "    - OS: Debian 12"
echo "    - Price: EUR 4.49/mo"

# Step 3: Instructions
echo ""
echo "[3/3] After provisioning, run setup:"
echo ""
echo "  # Get the VPS IP from OVH Manager, then:"
echo "  export VPS_IP=<new-vps-ip>"
echo "  ./deploy/vps/hegemon/setup-base.sh \$VPS_IP"
echo "  ./deploy/vps/hegemon/setup-claude.sh \$VPS_IP"
echo ""
echo "  # Verify:"
echo "  ssh hegemon@\$VPS_IP 'claude --version && tmux -V && git --version'"
