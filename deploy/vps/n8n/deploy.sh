#!/usr/bin/env bash
# Deploy n8n self-hosted to OVH VPS (n8n.gostoa.dev)
# Replaces n8n Cloud (hlfh.app.n8n.cloud) — removes execution limits
#
# Prerequisites:
#   - SSH key: ~/.ssh/id_ed25519_stoa
#   - DNS: n8n.gostoa.dev → 51.254.139.205 (Cloudflare, DNS-only)
#   - Docker + Docker Compose installed on VPS
#
# Usage: ./deploy/vps/n8n/deploy.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSH_KEY=~/.ssh/id_ed25519_stoa
VPS_IP="51.254.139.205"
VPS_USER="ubuntu"
REMOTE_DIR="/opt/n8n"

echo "=== n8n Self-Hosted Deploy ==="
echo "Target: ${VPS_USER}@${VPS_IP}"
echo ""

# Step 1: Ensure Docker is installed
echo "[1/6] Checking Docker on VPS..."
ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_IP}" "docker --version && docker compose version" || {
  echo "Docker not found. Installing..."
  ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_IP}" "curl -fsSL https://get.docker.com | sh && sudo usermod -aG docker ${VPS_USER}"
  echo "Docker installed. Please re-run this script (group change requires new SSH session)."
  exit 1
}

# Step 2: Create remote directory
echo "[2/6] Creating remote directory ${REMOTE_DIR}..."
ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_IP}" "sudo mkdir -p ${REMOTE_DIR} && sudo chown ${VPS_USER}:${VPS_USER} ${REMOTE_DIR}"

# Step 3: Copy files
echo "[3/6] Copying docker-compose.yml, Caddyfile, .env.template..."
scp -i "$SSH_KEY" -q \
  "$SCRIPT_DIR/docker-compose.yml" \
  "$SCRIPT_DIR/Caddyfile" \
  "$SCRIPT_DIR/.env.template" \
  "${VPS_USER}@${VPS_IP}:${REMOTE_DIR}/"

# Step 4: Generate .env if not exists
echo "[4/6] Checking .env file..."
ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_IP}" bash -c "'
  if [ ! -f ${REMOTE_DIR}/.env ]; then
    PG_PASS=\$(openssl rand -base64 24)
    ENC_KEY=\$(openssl rand -hex 32)
    cat > ${REMOTE_DIR}/.env <<INNEREOF
POSTGRES_PASSWORD=\${PG_PASS}
N8N_ENCRYPTION_KEY=\${ENC_KEY}
INNEREOF
    echo \".env created with generated secrets.\"
    echo \"IMPORTANT: Back up these values to Infisical!\"
    cat ${REMOTE_DIR}/.env
  else
    echo \".env already exists — keeping current values.\"
  fi
'"

# Step 5: Pull images and start
echo "[5/6] Pulling images and starting stack..."
ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_IP}" "cd ${REMOTE_DIR} && docker compose pull && docker compose up -d"

# Step 6: Wait for health check
echo "[6/6] Waiting for n8n to be ready..."
for i in $(seq 1 30); do
  if ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_IP}" "curl -sf http://localhost:5678/healthz > /dev/null 2>&1"; then
    echo "  n8n is healthy! (attempt $i)"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "  WARNING: n8n not healthy after 30 attempts. Check logs:"
    echo "  ssh -i $SSH_KEY ${VPS_USER}@${VPS_IP} 'cd ${REMOTE_DIR} && docker compose logs n8n --tail=50'"
    exit 1
  fi
  sleep 2
done

echo ""
echo "=== Deploy Complete ==="
echo ""
echo "Next steps:"
echo "  1. Create DNS record: n8n.gostoa.dev → ${VPS_IP} (Cloudflare, DNS-only)"
echo "  2. Wait for Caddy to obtain TLS certificate (auto, ~30s after DNS propagates)"
echo "  3. Access n8n: https://n8n.gostoa.dev"
echo "  4. Create admin account on first access"
echo "  5. Import 5 workflows from scripts/ai-ops/n8n-*.json"
echo "  6. Configure n8n Variables (Settings > Variables):"
echo "     - APPROVE_HMAC_SECRET"
echo "     - SLACK_SIGNING_SECRET"
echo "     - SLACK_ALLOWED_USERS"
echo "     - SLACK_ADMIN_USERS"
echo "  7. Configure n8n Credentials:"
echo "     - GitHub PAT (HTTP Header Auth)"
echo "  8. Update GitHub repo variables:"
echo "     gh variable set N8N_APPROVE_WEBHOOK_URL --body 'https://n8n.gostoa.dev/webhook/approve-ticket'"
echo "     gh variable set N8N_MERGE_WEBHOOK_URL --body 'https://n8n.gostoa.dev/webhook/merge-pr'"
echo "  9. Update Slack App:"
echo "     - Interactivity URL: https://n8n.gostoa.dev/webhook/slack-interactive"
echo "     - /stoa command URL: https://n8n.gostoa.dev/webhook/stoa-slash-command"
echo ""
echo "Verify:"
echo "  curl -s https://n8n.gostoa.dev/healthz"
echo "  ssh -i $SSH_KEY ${VPS_USER}@${VPS_IP} 'cd ${REMOTE_DIR} && docker compose logs --tail=20'"
echo ""
echo "Back up secrets to Infisical:"
echo "  ssh -i $SSH_KEY ${VPS_USER}@${VPS_IP} 'cat ${REMOTE_DIR}/.env'"
