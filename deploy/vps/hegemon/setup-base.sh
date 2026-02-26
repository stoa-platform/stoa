#!/usr/bin/env bash
# Setup base packages, security, and swap on a freshly provisioned OVH VPS.
# Designed for Debian 12 (Bookworm). Run from local machine.
#
# Usage: ./setup-base.sh <VPS_IP> [SSH_KEY]
#   SSH_KEY defaults to ~/.ssh/id_ed25519_stoa
set -euo pipefail

VPS_IP="${1:?Usage: ./setup-base.sh <VPS_IP> [SSH_KEY]}"
SSH_KEY="${2:-$HOME/.ssh/id_ed25519_stoa}"
HEGEMON_USER="hegemon"
SWAP_SIZE="4G"

ssh_cmd() {
  ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new "root@${VPS_IP}" "$@"
}

echo "=== HEGEMON Base Setup: ${VPS_IP} ==="

# Step 1: Create hegemon user
echo "[1/6] Creating ${HEGEMON_USER} user..."
ssh_cmd "id ${HEGEMON_USER} &>/dev/null || {
  adduser ${HEGEMON_USER} --disabled-password --gecos 'HEGEMON Worker'
  usermod -aG sudo ${HEGEMON_USER}
  echo '${HEGEMON_USER} ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/${HEGEMON_USER}
  chmod 440 /etc/sudoers.d/${HEGEMON_USER}
}"

# Step 2: Copy SSH keys
echo "[2/6] Setting up SSH keys..."
ssh_cmd "mkdir -p /home/${HEGEMON_USER}/.ssh && \
  cp /root/.ssh/authorized_keys /home/${HEGEMON_USER}/.ssh/ && \
  chown -R ${HEGEMON_USER}:${HEGEMON_USER} /home/${HEGEMON_USER}/.ssh && \
  chmod 700 /home/${HEGEMON_USER}/.ssh && \
  chmod 600 /home/${HEGEMON_USER}/.ssh/authorized_keys"

# Step 3: Harden SSH
echo "[3/6] Hardening SSH..."
ssh_cmd "sed -i 's/^PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
  sed -i 's/^#PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
  systemctl restart sshd"

# Step 4: Install base packages
echo "[4/6] Installing packages..."
ssh_cmd "apt-get update -qq && apt-get upgrade -y -qq && \
  apt-get install -y -qq \
    tmux git curl jq wget gnupg ca-certificates \
    fail2ban ufw unattended-upgrades \
    build-essential htop"

# Step 5: Firewall
echo "[5/6] Configuring firewall..."
ssh_cmd "ufw allow ssh && ufw --force enable && \
  systemctl enable fail2ban && systemctl start fail2ban"

# Step 6: Swap
echo "[6/6] Creating ${SWAP_SIZE} swap..."
ssh_cmd "if ! swapon --show | grep -q /swapfile; then
  fallocate -l ${SWAP_SIZE} /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo 'vm.swappiness=10' >> /etc/sysctl.conf
  sysctl -p
fi
swapon --show"

echo ""
echo "=== Base Setup Complete ==="
echo "  User:     ${HEGEMON_USER} (sudo, no password)"
echo "  SSH:      root login disabled"
echo "  Firewall: UFW active (SSH only)"
echo "  Swap:     ${SWAP_SIZE}"
echo ""
echo "Next: ./deploy/vps/hegemon/setup-claude.sh ${VPS_IP}"
