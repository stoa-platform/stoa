#!/usr/bin/env bash
# Deploy PocketBase to OVH VPS (state.gostoa.dev)
# Shares VPS with n8n (51.254.139.205), Traefik handles TLS
#
# Architecture:
#   PocketBase runs inside n8n's docker-compose stack.
#   Traefik discovers it via Docker labels and provisions Let's Encrypt cert.
#   PocketBase data in Docker volume pb_data.
#   Config (.env) at /opt/pocketbase/.env.
#
# Prerequisites:
#   - SSH key: ~/.ssh/id_ed25519_stoa
#   - DNS: state.gostoa.dev → 51.254.139.205 (Cloudflare, DNS-only)
#   - Docker running on VPS (n8n stack with Traefik)
#
# Usage: ./deploy/vps/pocketbase/deploy.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSH_KEY=~/.ssh/id_ed25519_stoa
VPS_IP="51.254.139.205"
VPS_USER="debian"
CONFIG_DIR="/opt/pocketbase"
N8N_DIR="/home/debian/n8n"

echo "=== PocketBase Deploy (HEGEMON State Store) ==="
echo "Target: ${VPS_USER}@${VPS_IP}"
echo ""

SSH_CMD="ssh -i $SSH_KEY ${VPS_USER}@${VPS_IP}"

# Step 1: Create config directory
echo "[1/6] Creating config directory ${CONFIG_DIR}..."
$SSH_CMD "sudo mkdir -p ${CONFIG_DIR} && sudo chown ${VPS_USER}:${VPS_USER} ${CONFIG_DIR}"

# Step 2: Copy setup script + env template
echo "[2/6] Copying setup-collections.sh + .env.template..."
scp -i "$SSH_KEY" -q \
  "$SCRIPT_DIR/.env.template" \
  "$SCRIPT_DIR/setup-collections.sh" \
  "${VPS_USER}@${VPS_IP}:${CONFIG_DIR}/"
$SSH_CMD "chmod +x ${CONFIG_DIR}/setup-collections.sh"

# Step 3: Generate .env if not exists
echo "[3/6] Checking .env file..."
$SSH_CMD bash -c "'
  if [ ! -f ${CONFIG_DIR}/.env ]; then
    PB_PASS=\$(openssl rand -base64 24)
    cat > ${CONFIG_DIR}/.env <<INNEREOF
PB_ADMIN_EMAIL=admin@gostoa.dev
PB_ADMIN_PASSWORD=\${PB_PASS}
INNEREOF
    echo \".env created. IMPORTANT: Save PB_ADMIN_PASSWORD to Infisical!\"
    echo \"Password: \${PB_PASS}\"
  else
    echo \".env already exists — keeping current values.\"
  fi
'"

# Step 4: Inject PocketBase service into n8n docker-compose
echo "[4/6] Adding PocketBase to n8n docker-compose..."
$SSH_CMD bash -c "'
  COMPOSE=${N8N_DIR}/docker-compose.yml
  if grep -q \"pocketbase\" \$COMPOSE 2>/dev/null; then
    echo \"  PocketBase already in docker-compose.yml\"
  else
    echo \"\"
    echo \"  WARNING: PocketBase not found in \$COMPOSE\"
    echo \"  Add the pocketbase service manually (see deploy/vps/pocketbase/docker-compose.yml)\"
    echo \"  Key: Traefik labels for state.gostoa.dev, env_file: /opt/pocketbase/.env\"
    echo \"  Do NOT set command: — the elestio image entrypoint already includes serve\"
  fi
'"

# Step 5: Pull + start PocketBase
echo "[5/6] Pulling and starting PocketBase..."
$SSH_CMD "cd ${N8N_DIR} && docker compose pull pocketbase 2>/dev/null && docker compose up -d pocketbase"

# Step 6: Health check
echo "[6/6] Waiting for PocketBase..."
for i in $(seq 1 20); do
  if $SSH_CMD "curl -sf http://localhost:8090/api/health > /dev/null 2>&1"; then
    echo "  PocketBase healthy! (attempt $i)"
    break
  fi
  if [ "$i" -eq 20 ]; then
    echo "  WARNING: PocketBase not healthy after 20 attempts."
    echo "  Check: $SSH_CMD 'cd ${N8N_DIR} && docker compose logs pocketbase --tail=30'"
    exit 1
  fi
  sleep 2
done

echo ""
echo "=== Deploy Complete ==="
echo ""
echo "Next steps:"
echo "  1. Run collection setup (first time only):"
echo "     $SSH_CMD 'source ${CONFIG_DIR}/.env && ${CONFIG_DIR}/setup-collections.sh'"
echo "  2. Save PB_ADMIN_PASSWORD to Infisical: /pocketbase/PB_ADMIN_PASSWORD"
echo "  3. Set local env vars:"
echo "     export HEGEMON_REMOTE_URL=https://state.gostoa.dev"
echo "     export HEGEMON_REMOTE_PASSWORD=<password from Infisical>"
echo ""
echo "Verify:"
echo "  curl -s https://state.gostoa.dev/api/health"
echo "  heg-state sync   # push all local state to remote"
echo "  heg-state remote-ls  # query remote sessions"
