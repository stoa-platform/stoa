#!/usr/bin/env bash
# Deploy HashiCorp Vault to OVH VPS (hcv.gostoa.dev)
# Phase 0 of Unified Secrets Management (CAB-1796)
#
# Prerequisites:
#   - SSH key: ~/.ssh/id_ed25519_stoa
#   - DNS: hcv.gostoa.dev → 51.255.193.129 (Cloudflare, DNS-only)
#   - Docker + Docker Compose installed on VPS
#   - Vault NOT yet initialized (first run) OR already running (update)
#
# Usage:
#   ./deploy/vps/vault/deploy.sh          # Full deploy
#   ./deploy/vps/vault/deploy.sh --init   # Deploy + initialize + configure
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSH_KEY=~/.ssh/id_ed25519_stoa
VPS_IP="51.255.193.129"
VPS_USER="root"
REMOTE_DIR="/opt/vault"
INIT_MODE=false

for arg in "$@"; do
  case $arg in
    --init) INIT_MODE=true ;;
  esac
done

echo "=== HashiCorp Vault Deploy ==="
echo "Target: ${VPS_USER}@${VPS_IP} (spare-gra-vps)"
echo "URL:    https://hcv.gostoa.dev"
echo ""

# Step 1: Ensure Docker is installed
echo "[1/7] Checking Docker on VPS..."
ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_IP}" "docker --version && docker compose version" || {
  echo "Docker not found. Installing..."
  ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_IP}" "curl -fsSL https://get.docker.com | sh"
  echo "Docker installed."
}

# Step 2: Create remote directories
echo "[2/7] Creating remote directories..."
ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_IP}" "mkdir -p ${REMOTE_DIR}/config ${REMOTE_DIR}/policies"

# Step 3: Copy files
echo "[3/7] Copying configuration files..."
scp -i "$SSH_KEY" -q \
  "$SCRIPT_DIR/docker-compose.yml" \
  "$SCRIPT_DIR/Caddyfile" \
  "${VPS_USER}@${VPS_IP}:${REMOTE_DIR}/"

scp -i "$SSH_KEY" -q \
  "$SCRIPT_DIR/config/vault.hcl" \
  "${VPS_USER}@${VPS_IP}:${REMOTE_DIR}/config/"

scp -i "$SSH_KEY" -q \
  "$SCRIPT_DIR/policies/"*.hcl \
  "${VPS_USER}@${VPS_IP}:${REMOTE_DIR}/policies/"

scp -i "$SSH_KEY" -q \
  "$SCRIPT_DIR/init-vault.sh" \
  "${VPS_USER}@${VPS_IP}:${REMOTE_DIR}/"
ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_IP}" "chmod +x ${REMOTE_DIR}/init-vault.sh"

# Step 4: Pull images and start
echo "[4/7] Pulling images and starting stack..."
ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_IP}" "cd ${REMOTE_DIR} && docker compose pull && docker compose up -d"

# Step 5: Wait for Vault to be ready
echo "[5/7] Waiting for Vault to be ready..."
for i in $(seq 1 30); do
  # Vault returns 501 when not initialized, 503 when sealed, 200 when ready
  HTTP_CODE=$(ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_IP}" \
    "curl -sf -o /dev/null -w '%{http_code}' http://127.0.0.1:8200/v1/sys/health?standbyok=true&uninitcode=501&sealedcode=503 2>/dev/null || echo 000")
  if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "501" ] || [ "$HTTP_CODE" = "503" ]; then
    echo "  Vault is responding (HTTP $HTTP_CODE, attempt $i)"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "  ERROR: Vault not responding after 30 attempts."
    echo "  Check: ssh -i $SSH_KEY ${VPS_USER}@${VPS_IP} 'cd ${REMOTE_DIR} && docker compose logs vault --tail=50'"
    exit 1
  fi
  sleep 2
done

# Step 6: Initialize if --init flag and not yet initialized
if [ "$INIT_MODE" = true ]; then
  echo "[6/7] Checking initialization status..."
  INIT_STATUS=$(ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_IP}" \
    "curl -sf http://127.0.0.1:8200/v1/sys/health?standbyok=true&uninitcode=501&sealedcode=503 -o /dev/null -w '%{http_code}' 2>/dev/null || echo 000")

  if [ "$INIT_STATUS" = "501" ]; then
    echo "  Vault not initialized. Running init-vault.sh..."
    ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_IP}" "cd ${REMOTE_DIR} && ./init-vault.sh"
  elif [ "$INIT_STATUS" = "503" ]; then
    echo "  Vault is sealed. Unseal keys are in /opt/vault/init-keys.json on the VPS."
    echo "  Run: ssh -i $SSH_KEY ${VPS_USER}@${VPS_IP} 'cd ${REMOTE_DIR} && ./init-vault.sh --unseal'"
  elif [ "$INIT_STATUS" = "200" ]; then
    echo "  Vault already initialized and unsealed."
  else
    echo "  WARNING: Unexpected status $INIT_STATUS"
  fi
else
  echo "[6/7] Skipping init (use --init for first-time setup)"
fi

# Step 7: Final status
echo "[7/7] Verifying deployment..."
FINAL_STATUS=$(ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_IP}" \
  "curl -sf http://127.0.0.1:8200/v1/sys/health 2>/dev/null | python3 -c 'import sys,json; d=json.load(sys.stdin); print(f\"initialized={d[\"initialized\"]} sealed={d[\"sealed\"]} version={d[\"version\"]}\")' 2>/dev/null || echo 'unavailable'")
echo "  Status: $FINAL_STATUS"

echo ""
echo "=== Deploy Complete ==="
echo ""
echo "Vault: https://hcv.gostoa.dev"
echo "UI:    https://hcv.gostoa.dev/ui/"
echo ""
if [ "$INIT_MODE" = true ]; then
  echo "CRITICAL: Back up init-keys.json from the VPS to a secure location!"
  echo "  ssh -i $SSH_KEY ${VPS_USER}@${VPS_IP} 'cat ${REMOTE_DIR}/init-keys.json'"
  echo ""
fi
echo "Next steps:"
echo "  1. Create DNS: hcv.gostoa.dev → ${VPS_IP} (Cloudflare, DNS-only)"
echo "  2. First deploy: ./deploy.sh --init"
echo "  3. Back up init-keys.json to Infisical (one-time)"
echo "  4. Run migrate-to-vault.sh (Phase 1)"
echo ""
echo "Verify:"
echo "  curl -s https://hcv.gostoa.dev/v1/sys/health | jq ."
echo "  ssh -i $SSH_KEY ${VPS_USER}@${VPS_IP} 'cd ${REMOTE_DIR} && docker compose logs --tail=20'"
