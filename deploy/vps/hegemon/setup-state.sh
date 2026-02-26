#!/usr/bin/env bash
# Install heg-state CLI and PocketBase integration on a HEGEMON VPS worker.
# Run from local machine after setup-claude.sh.
#
# Usage: ./setup-state.sh <VPS_IP> [SSH_KEY]
set -euo pipefail

VPS_IP="${1:?Usage: ./setup-state.sh <VPS_IP> [SSH_KEY]}"
SSH_KEY="${2:-$HOME/.ssh/id_ed25519_stoa}"
HEGEMON_USER="hegemon"

ssh_cmd() {
  ssh -i "$SSH_KEY" "${HEGEMON_USER}@${VPS_IP}" "$@"
}

scp_cmd() {
  scp -i "$SSH_KEY" "$1" "${HEGEMON_USER}@${VPS_IP}:$2"
}

echo "=== HEGEMON State + Slack Setup: ${VPS_IP} ==="

# Step 1: Install heg-state dependencies
echo "[1/5] Installing Python3 + certifi..."
ssh_cmd 'sudo apt-get install -y -qq python3 python3-certifi 2>/dev/null || true'

# Step 2: Deploy heg-state from stoa repo
echo "[2/5] Setting up heg-state CLI..."
ssh_cmd 'cd ~/stoa && bash hegemon/tools/state/setup.sh'

# Step 3: Configure PocketBase remote
echo "[3/5] Configuring PocketBase remote..."
ssh_cmd 'cat >> ~/.env.hegemon << "PBEOF"

# PocketBase remote (heg-state sync)
export HEGEMON_REMOTE_URL="https://state.gostoa.dev"
export HEGEMON_REMOTE_EMAIL="admin@gostoa.dev"
# Fill from Infisical /pocketbase/HEGEMON_REMOTE_PASSWORD:
export HEGEMON_REMOTE_PASSWORD=""
PBEOF'

echo "  IMPORTANT: Fill HEGEMON_REMOTE_PASSWORD in ~/.env.hegemon"

# Step 4: Deploy notify.sh
echo "[4/5] Deploying Slack notification wrapper..."
scp_cmd "deploy/vps/hegemon/notify.sh" "~/stoa/deploy/vps/hegemon/notify.sh"
ssh_cmd 'chmod +x ~/stoa/deploy/vps/hegemon/notify.sh && \
  grep -q "notify.sh" ~/.bashrc || \
  echo "source ~/stoa/deploy/vps/hegemon/notify.sh" >> ~/.bashrc'

# Step 5: Deploy hegemon-agent service
echo "[5/5] Installing hegemon-agent systemd service..."
ssh_cmd 'mkdir -p ~/.config/systemd/user ~/.local/bin

# Copy start script
cp ~/stoa/deploy/vps/hegemon/hegemon-start.sh ~/.local/bin/hegemon-start.sh
chmod +x ~/.local/bin/hegemon-start.sh

# Install service (system-level, needs sudo for boot start)
sudo cp ~/stoa/deploy/vps/hegemon/hegemon-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable hegemon-agent

# Enable lingering (so user services + tmux survive logout)
sudo loginctl enable-linger hegemon'

# Verify
echo ""
echo "=== State + Slack Setup Complete ==="
echo "  heg-state:  installed (~/.local/bin/heg-state)"
echo "  PocketBase:  configured (fill HEGEMON_REMOTE_PASSWORD)"
echo "  Slack:       notify.sh sourced in .bashrc"
echo "  Agent:       hegemon-agent.service enabled"
echo ""
echo "  Next steps:"
echo "    1. SSH: ssh -i ${SSH_KEY} ${HEGEMON_USER}@${VPS_IP}"
echo "    2. Fill HEGEMON_REMOTE_PASSWORD in ~/.env.hegemon"
echo "    3. Test heg-state:"
echo "       source ~/.env.hegemon"
echo "       heg-state start --ticket TEST-001 --role worker-1 --branch test"
echo "       heg-state remote-ls"
echo "       heg-state done TEST-001"
echo "    4. Test Slack:"
echo "       source ~/.env.hegemon && source ~/stoa/deploy/vps/hegemon/notify.sh"
echo "       hegemon_ping"
echo "    5. Start agent: sudo systemctl start hegemon-agent"
echo "       Attach: tmux -L hegemon attach -t hegemon"
