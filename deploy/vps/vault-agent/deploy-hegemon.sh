#!/usr/bin/env bash
# Deploy Vault Agent to HEGEMON workers — in-memory secrets (no file on disk)
# Phase 3 of Unified Secrets Management (CAB-1799)
#
# HEGEMON workers use env_template (not file templates) — secrets are injected
# directly into the process environment via Vault Agent's exec mode.
# This replaces infisical-loader.sh.
#
# Prerequisites:
#   - SSH key: ~/.ssh/id_ed25519_stoa
#   - Vault running with vps-hegemon AppRole (Phase 0)
#   - VAULT_TOKEN set (admin token)
#
# Usage:
#   ./deploy-hegemon.sh <worker-ip>           # Single worker
#   ./deploy-hegemon.sh all                   # All 5 workers
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519_stoa}"
VAULT_ADDR="${VAULT_ADDR:-https://hcvault.gostoa.dev}"
APPROLE_NAME="vps-hegemon"
SSH_USER="hegemon"

# Contabo HEGEMON workers
WORKERS=(
  "62.171.178.49"    # worker-1
  "161.97.93.225"    # worker-2
  "167.86.75.214"    # worker-3
  "5.189.152.183"    # worker-4
  "144.91.82.96"     # worker-5
)

SSH_CMD="ssh -i ${SSH_KEY} -o StrictHostKeyChecking=accept-new"

# --- Parse arguments ---
if [ $# -lt 1 ]; then
  echo "Usage: $0 <worker-ip|all>"
  echo ""
  echo "Workers:"
  for i in "${!WORKERS[@]}"; do
    echo "  ${WORKERS[$i]}  worker-$((i+1))"
  done
  exit 1
fi

if [ "$1" = "all" ]; then
  TARGETS=("${WORKERS[@]}")
else
  TARGETS=("$1")
fi

# --- Generate AppRole credentials ---
echo "=== HEGEMON Vault Agent Deploy ==="
echo "AppRole: ${APPROLE_NAME}"
echo "Targets: ${#TARGETS[@]} worker(s)"
echo ""

if [ -z "${VAULT_TOKEN:-}" ]; then
  echo "ERROR: VAULT_TOKEN not set."
  exit 1
fi

ROLE_ID=$(curl -sf -H "X-Vault-Token: ${VAULT_TOKEN}" \
  "${VAULT_ADDR}/v1/auth/approle/role/${APPROLE_NAME}/role-id" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['role_id'])")

echo "Role ID: ${ROLE_ID:0:8}..."
echo ""

for TARGET in "${TARGETS[@]}"; do
  echo "--- Deploying to ${TARGET} ---"

  # Generate a unique secret-id per worker
  SECRET_ID=$(curl -sf -X POST -H "X-Vault-Token: ${VAULT_TOKEN}" \
    "${VAULT_ADDR}/v1/auth/approle/role/${APPROLE_NAME}/secret-id" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['secret_id'])")

  # Step 1: Install Vault binary
  echo "  [1/4] Installing Vault binary..."
  $SSH_CMD "${SSH_USER}@${TARGET}" bash -s <<'REMOTE_INSTALL'
if command -v vault &>/dev/null; then
  echo "    Already installed: $(vault version | head -1)"
else
  cd /tmp
  sudo apt-get -qq update && sudo apt-get -qq install -y unzip curl >/dev/null 2>&1 || true
  curl -sfL "https://releases.hashicorp.com/vault/1.18.4/vault_1.18.4_linux_amd64.zip" -o vault.zip
  unzip -o vault.zip >/dev/null
  sudo mv vault /usr/local/bin/vault
  sudo chmod +x /usr/local/bin/vault
  rm vault.zip
  echo "    Installed: $(vault version | head -1)"
fi
REMOTE_INSTALL

  # Step 2: Write vault-loader.sh (replaces infisical-loader.sh)
  echo "  [2/4] Installing vault-loader.sh..."
  $SSH_CMD "${SSH_USER}@${TARGET}" mkdir -p ~/.hegemon ~/.local/bin

  cat "${SCRIPT_DIR}/../../../hegemon/daemon/vault-loader.sh" \
    | $SSH_CMD "${SSH_USER}@${TARGET}" "cat > ~/.local/bin/vault-loader.sh && chmod +x ~/.local/bin/vault-loader.sh"

  # Step 3: Write AppRole credentials
  echo "  [3/4] Writing AppRole credentials..."
  echo "${ROLE_ID}" | $SSH_CMD "${SSH_USER}@${TARGET}" "cat > ~/.hegemon/vault-role-id && chmod 600 ~/.hegemon/vault-role-id"
  echo "${SECRET_ID}" | $SSH_CMD "${SSH_USER}@${TARGET}" "cat > ~/.hegemon/vault-secret-id && chmod 600 ~/.hegemon/vault-secret-id"

  # Step 4: Update .env.hegemon to source vault-loader instead of infisical-loader
  echo "  [4/4] Updating .env.hegemon..."
  $SSH_CMD "${SSH_USER}@${TARGET}" bash -s <<'REMOTE_ENV'
# Replace infisical-loader source with vault-loader in .bashrc if present
if grep -q 'infisical-loader' ~/.bashrc 2>/dev/null; then
  sed -i 's|infisical-loader\.sh|vault-loader.sh|g' ~/.bashrc
  echo "    Updated .bashrc: infisical-loader → vault-loader"
fi
# Also update .env.hegemon to reference Vault
if [ -f ~/.env.hegemon ]; then
  if ! grep -q 'VAULT_ADDR' ~/.env.hegemon; then
    echo 'export VAULT_ADDR="https://hcvault.gostoa.dev"' >> ~/.env.hegemon
    echo "    Added VAULT_ADDR to .env.hegemon"
  fi
fi
REMOTE_ENV

  echo "  Done: ${TARGET}"
  echo ""
done

echo "=== HEGEMON Deploy Complete ==="
echo ""
echo "Verify on each worker:"
echo "  ssh -i ${SSH_KEY} ${SSH_USER}@<ip> 'source ~/.local/bin/vault-loader.sh && echo \$ANTHROPIC_API_KEY | head -c 10'"
echo ""
echo "To restart the agent service (picks up new secrets on next shell init):"
echo "  ssh -i ${SSH_KEY} ${SSH_USER}@<ip> 'sudo systemctl restart hegemon-agent'"
