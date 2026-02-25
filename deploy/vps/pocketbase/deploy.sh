#!/usr/bin/env bash
# Deploy PocketBase to OVH VPS (state.gostoa.dev)
# Shares VPS with n8n (51.254.139.205)
#
# Prerequisites:
#   - SSH key: ~/.ssh/id_ed25519_stoa
#   - DNS: state.gostoa.dev → 51.254.139.205 (Cloudflare, DNS-only)
#   - Docker running on VPS (already installed for n8n)
#   - n8n stack running (Caddy handles TLS)
#
# Usage: ./deploy/vps/pocketbase/deploy.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSH_KEY=~/.ssh/id_ed25519_stoa
VPS_IP="51.254.139.205"
VPS_USER="ubuntu"
REMOTE_DIR="/opt/pocketbase"
N8N_DIR="/opt/n8n"

echo "=== PocketBase Deploy (HEGEMON State Store) ==="
echo "Target: ${VPS_USER}@${VPS_IP}"
echo ""

SSH_CMD="ssh -i $SSH_KEY ${VPS_USER}@${VPS_IP}"

# Step 1: Create remote directory
echo "[1/7] Creating remote directory ${REMOTE_DIR}..."
$SSH_CMD "sudo mkdir -p ${REMOTE_DIR} && sudo chown ${VPS_USER}:${VPS_USER} ${REMOTE_DIR}"

# Step 2: Copy files
echo "[2/7] Copying docker-compose.yml + .env.template..."
scp -i "$SSH_KEY" -q \
  "$SCRIPT_DIR/docker-compose.yml" \
  "$SCRIPT_DIR/.env.template" \
  "$SCRIPT_DIR/setup-collections.sh" \
  "${VPS_USER}@${VPS_IP}:${REMOTE_DIR}/"
$SSH_CMD "chmod +x ${REMOTE_DIR}/setup-collections.sh"

# Step 3: Generate .env if not exists
echo "[3/7] Checking .env file..."
$SSH_CMD bash -c "'
  if [ ! -f ${REMOTE_DIR}/.env ]; then
    PB_PASS=\$(openssl rand -base64 24)
    cat > ${REMOTE_DIR}/.env <<INNEREOF
PB_ADMIN_EMAIL=admin@gostoa.dev
PB_ADMIN_PASSWORD=\${PB_PASS}
INNEREOF
    echo \".env created. IMPORTANT: Save PB_ADMIN_PASSWORD to Infisical!\"
    echo \"Password: \${PB_PASS}\"
  else
    echo \".env already exists — keeping current values.\"
  fi
'"

# Step 4: Create shared-proxy network (idempotent)
echo "[4/7] Setting up shared-proxy Docker network..."
$SSH_CMD "docker network create shared-proxy 2>/dev/null || true"
$SSH_CMD "docker network connect shared-proxy n8n-caddy 2>/dev/null || echo '  n8n-caddy already on shared-proxy (or not running)'"

# Step 5: Update n8n Caddyfile with state.gostoa.dev
echo "[5/7] Adding state.gostoa.dev to Caddy..."
$SSH_CMD bash -c "'
  CADDYFILE=${N8N_DIR}/Caddyfile
  if ! grep -q \"state.gostoa.dev\" \$CADDYFILE 2>/dev/null; then
    echo \"\" >> \$CADDYFILE
    echo \"state.gostoa.dev {\" >> \$CADDYFILE
    echo \"	reverse_proxy pocketbase:8090\" >> \$CADDYFILE
    echo \"}\" >> \$CADDYFILE
    echo \"  Added state.gostoa.dev to Caddyfile\"
  else
    echo \"  state.gostoa.dev already in Caddyfile\"
  fi
'"

# Step 6: Pull + start PocketBase, reload Caddy
echo "[6/7] Starting PocketBase + reloading Caddy..."
$SSH_CMD "cd ${REMOTE_DIR} && docker compose pull && docker compose up -d"
$SSH_CMD "docker exec n8n-caddy caddy reload --config /etc/caddy/Caddyfile 2>/dev/null || echo '  Caddy reload: will pick up on next restart'"

# Step 7: Health check
echo "[7/7] Waiting for PocketBase..."
for i in $(seq 1 20); do
  if $SSH_CMD "curl -sf http://localhost:8090/api/health > /dev/null 2>&1"; then
    echo "  PocketBase healthy! (attempt $i)"
    break
  fi
  if [ "$i" -eq 20 ]; then
    echo "  WARNING: PocketBase not healthy after 20 attempts."
    echo "  Check: $SSH_CMD 'cd ${REMOTE_DIR} && docker compose logs --tail=30'"
    exit 1
  fi
  sleep 2
done

echo ""
echo "=== Deploy Complete ==="
echo ""
echo "Next steps:"
echo "  1. Create DNS: state.gostoa.dev → ${VPS_IP} (Cloudflare, DNS-only)"
echo "  2. Run collection setup:"
echo "     $SSH_CMD 'cd ${REMOTE_DIR} && source .env && ./setup-collections.sh'"
echo "  3. Save PB_ADMIN_PASSWORD to Infisical: /pocketbase/PB_ADMIN_PASSWORD"
echo "  4. Set local env vars:"
echo "     export HEGEMON_REMOTE_URL=https://state.gostoa.dev"
echo "     export HEGEMON_REMOTE_PASSWORD=<password>"
echo ""
echo "Verify:"
echo "  curl -s https://state.gostoa.dev/api/health"
echo "  heg-state ls  # should show remote sync status"
