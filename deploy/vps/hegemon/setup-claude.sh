#!/usr/bin/env bash
# Install Claude Code CLI, Node.js, git deploy key, and memory watchdog
# on a HEGEMON VPS worker. Run from local machine after setup-base.sh.
#
# Usage: ./setup-claude.sh <VPS_IP> [SSH_KEY]
set -euo pipefail

VPS_IP="${1:?Usage: ./setup-claude.sh <VPS_IP> [SSH_KEY]}"
SSH_KEY="${2:-$HOME/.ssh/id_ed25519_stoa}"
HEGEMON_USER="hegemon"

ssh_cmd() {
  ssh -i "$SSH_KEY" "${HEGEMON_USER}@${VPS_IP}" "$@"
}

scp_cmd() {
  scp -i "$SSH_KEY" "$1" "${HEGEMON_USER}@${VPS_IP}:$2"
}

echo "=== HEGEMON Claude Code Setup: ${VPS_IP} ==="

# Step 1: Claude Code CLI (native binary)
echo "[1/6] Installing Claude Code CLI..."
ssh_cmd 'curl -fsSL https://claude.ai/install.sh | sh && \
  echo "export PATH=\"\$HOME/.local/bin:\$PATH\"" >> ~/.bashrc && \
  export PATH="$HOME/.local/bin:$PATH" && \
  claude --version'

# Step 2: Node.js 20 (for MCP servers)
echo "[2/6] Installing Node.js 20..."
ssh_cmd 'curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && \
  sudo apt-get install -y -qq nodejs && \
  node --version'

# Step 3: Git deploy key
echo "[3/6] Setting up git deploy key..."
ssh_cmd 'if [ ! -f ~/.ssh/stoa-deploy ]; then
  ssh-keygen -t ed25519 -f ~/.ssh/stoa-deploy -N "" -C "hegemon@$(hostname)"
fi'

DEPLOY_KEY=$(ssh_cmd 'cat ~/.ssh/stoa-deploy.pub')
echo "  Deploy key (add to GitHub repo Settings > Deploy Keys with write access):"
echo ""
echo "  ${DEPLOY_KEY}"
echo ""
read -rp "  Press Enter after adding the deploy key to GitHub... "

ssh_cmd 'cat > ~/.ssh/config << "SSHEOF"
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/stoa-deploy
  IdentitiesOnly yes
SSHEOF
chmod 600 ~/.ssh/config
ssh -o StrictHostKeyChecking=accept-new -T git@github.com 2>&1 || true'

# Step 4: Clone stoa repo
echo "[4/6] Cloning stoa repo..."
ssh_cmd 'if [ ! -d ~/stoa ]; then
  git clone git@github.com:stoa-platform/stoa.git ~/stoa
fi
cd ~/stoa && git status
git config --global user.email "hegemon-worker@gostoa.dev"
git config --global user.name "HEGEMON Worker ($(hostname))"'

# Step 5: Environment variables template
echo "[5/6] Creating environment template..."
ssh_cmd 'cat > ~/.env.hegemon << "ENVEOF"
# Fill values from Infisical (vault.gostoa.dev)
# Path: /anthropic/ANTHROPIC_API_KEY
export ANTHROPIC_API_KEY=""

# Path: /slack/SLACK_WEBHOOK_URL
export SLACK_WEBHOOK_URL=""

# PocketBase state store
export POCKETBASE_URL="https://state.gostoa.dev"

# Worker identity
export HEGEMON_ROLE="worker-1"
export HEGEMON_HOSTNAME="$(hostname)"
ENVEOF
chmod 600 ~/.env.hegemon
grep -q "env.hegemon" ~/.bashrc || echo "source ~/.env.hegemon" >> ~/.bashrc'

echo "  IMPORTANT: SSH into the VPS and fill ANTHROPIC_API_KEY and SLACK_WEBHOOK_URL"
echo "  from Infisical before testing Claude Code."

# Step 6: Memory watchdog
echo "[6/6] Installing memory watchdog..."
ssh_cmd 'mkdir -p ~/.local/bin ~/.local/log ~/.config/systemd/user

cat > ~/.local/bin/claude-watchdog.sh << "WDEOF"
#!/usr/bin/env bash
# Monitor Claude Code RSS. Kill if exceeding threshold.
THRESHOLD_KB=$((7 * 1024 * 1024))  # 7 GB
SLEEP_INTERVAL=30

while true; do
  for pid in $(pgrep -x claude 2>/dev/null); do
    rss_kb=$(awk "/VmRSS/{print \$2}" /proc/${pid}/status 2>/dev/null || echo 0)
    if [ "${rss_kb}" -gt "${THRESHOLD_KB}" ]; then
      echo "$(date -Is) WATCHDOG: claude PID ${pid} RSS ${rss_kb}KB > ${THRESHOLD_KB}KB. Killing." \
        >> ~/.local/log/claude-watchdog.log
      kill -9 "${pid}"
    fi
  done
  sleep "${SLEEP_INTERVAL}"
done
WDEOF
chmod +x ~/.local/bin/claude-watchdog.sh

cat > ~/.config/systemd/user/claude-watchdog.service << "SVCEOF"
[Unit]
Description=Claude Code CLI memory watchdog
After=default.target

[Service]
ExecStart=%h/.local/bin/claude-watchdog.sh
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
SVCEOF

systemctl --user daemon-reload
systemctl --user enable claude-watchdog
systemctl --user start claude-watchdog'

# Also install the cgroup wrapper
ssh_cmd 'cat > ~/.local/bin/claude-limited << "CLEOF"
#!/usr/bin/env bash
# Execute claude in a cgroup limited to 6 GB.
# If exceeded, kernel OOM-kills the scope (not the VPS).
exec systemd-run --scope --user -p MemoryMax=6G claude "$@"
CLEOF
chmod +x ~/.local/bin/claude-limited'

echo ""
echo "=== Claude Code Setup Complete ==="
echo "  Claude CLI:  installed (native binary)"
echo "  Node.js:     v20.x"
echo "  Git:         deploy key configured"
echo "  Repo:        ~/stoa cloned"
echo "  Watchdog:    active (7GB threshold)"
echo "  cgroup:      claude-limited wrapper available"
echo ""
echo "  Next steps:"
echo "    1. SSH: ssh -i ${SSH_KEY} ${HEGEMON_USER}@${VPS_IP}"
echo "    2. Fill ~/.env.hegemon with secrets from Infisical"
echo "    3. Test: claude -p 'What is 2+2?' --output-format json"
echo "    4. Test: cd ~/stoa && git checkout -b test-vps && git push origin test-vps"
