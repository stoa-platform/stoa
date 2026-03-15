#!/usr/bin/env bash
# deploy.sh — Deploy stoa-connect agent to a VPS
#
# Usage: ./deploy.sh <vps-host> <instance-name> <environment>
#
# Prerequisites:
#   - Vault secret at stoa/shared/stoa-connect (STOA_CONTROL_PLANE_URL + STOA_GATEWAY_API_KEY)
#   - Vault Agent deployed on VPS with stoa-connect.env.tpl template
#   - SSH access to VPS (key-based, no password)
#
# Example:
#   ./deploy.sh 51.83.45.13 kong-vps production
#   ./deploy.sh 54.36.209.237 gravitee-vps production
#   ./deploy.sh 51.255.201.17 webmethods-vps production

set -euo pipefail

# --- Args ---
VPS_HOST="${1:?Usage: $0 <vps-host> <instance-name> <environment>}"
INSTANCE_NAME="${2:?Usage: $0 <vps-host> <instance-name> <environment>}"
ENVIRONMENT="${3:-production}"

SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519_stoa}"
SSH_OPTS="-o StrictHostKeyChecking=accept-new -i ${SSH_KEY}"

# stoa-connect release to install (update when new release is cut)
RELEASE_VERSION="${STOA_CONNECT_VERSION:-latest}"
RELEASE_REPO="stoa-platform/stoactl"
BINARY_NAME="stoa-connect"
INSTALL_PATH="/usr/local/bin/${BINARY_NAME}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Deploying stoa-connect to ${VPS_HOST} (${INSTANCE_NAME}) ==="

# --- Step 1: Download binary ---
echo "[1/5] Downloading stoa-connect binary..."
# Release uses tarballs: stoa-connect_0.2.0_linux_amd64.tar.gz
if [ "${RELEASE_VERSION}" = "latest" ]; then
    DOWNLOAD_URL="https://github.com/${RELEASE_REPO}/releases/latest/download/${BINARY_NAME}_latest_linux_amd64.tar.gz"
else
    # Strip 'v' prefix for tarball name: v0.2.0 -> 0.2.0
    VERSION_CLEAN="${RELEASE_VERSION#v}"
    DOWNLOAD_URL="https://github.com/${RELEASE_REPO}/releases/download/${RELEASE_VERSION}/${BINARY_NAME}_${VERSION_CLEAN}_linux_amd64.tar.gz"
fi

TMPDIR="$(mktemp -d)"
curl -fSL "${DOWNLOAD_URL}" -o "${TMPDIR}/${BINARY_NAME}.tar.gz"
tar xzf "${TMPDIR}/${BINARY_NAME}.tar.gz" -C "${TMPDIR}"
chmod +x "${TMPDIR}/${BINARY_NAME}"
echo "  Downloaded $(du -h "${TMPDIR}/${BINARY_NAME}" | cut -f1) binary"

# --- Step 2: Upload binary ---
echo "[2/5] Uploading binary to ${VPS_HOST}:${INSTALL_PATH}..."
scp ${SSH_OPTS} "${TMPDIR}/${BINARY_NAME}" "root@${VPS_HOST}:/tmp/${BINARY_NAME}"
ssh ${SSH_OPTS} "root@${VPS_HOST}" "mv /tmp/${BINARY_NAME} ${INSTALL_PATH} && chmod +x ${INSTALL_PATH}"
rm -rf "${TMPDIR}"

# --- Step 3: Verify secrets file exists ---
echo "[3/5] Verifying Vault Agent rendered secrets..."
ssh ${SSH_OPTS} "root@${VPS_HOST}" "test -f /opt/secrets/stoa-connect.env" || {
    echo "ERROR: /opt/secrets/stoa-connect.env not found on ${VPS_HOST}"
    echo "  Run vault-agent deploy with stoa-connect template first:"
    echo "  ./deploy/vps/vault-agent/deploy.sh ${VPS_HOST} vps-${INSTANCE_NAME} ${INSTANCE_NAME} stoa-connect"
    exit 1
}

# --- Step 4: Install systemd unit ---
echo "[4/5] Installing systemd unit..."
scp ${SSH_OPTS} "${SCRIPT_DIR}/stoa-connect.service" "root@${VPS_HOST}:/etc/systemd/system/stoa-connect.service"

# Override instance name
ssh ${SSH_OPTS} "root@${VPS_HOST}" bash <<REMOTE
    mkdir -p /etc/systemd/system/stoa-connect.service.d
    cat > /etc/systemd/system/stoa-connect.service.d/override.conf <<OVERRIDE
[Service]
Environment=STOA_INSTANCE_NAME=${INSTANCE_NAME}
Environment=STOA_ENVIRONMENT=${ENVIRONMENT}
OVERRIDE
    systemctl daemon-reload
    systemctl enable stoa-connect
    systemctl restart stoa-connect
REMOTE

echo "  Service installed and started"

# --- Step 5: Verify ---
echo "[5/5] Verifying registration..."
sleep 3
ssh ${SSH_OPTS} "root@${VPS_HOST}" "systemctl is-active stoa-connect && journalctl -u stoa-connect --no-pager -n 5"

echo ""
echo "=== stoa-connect deployed to ${VPS_HOST} (${INSTANCE_NAME}) ==="
echo ""
echo "Verify registration:"
echo "  curl -s localhost:8090/health  (on VPS)"
echo "  curl -sH 'Authorization: Bearer \${TOKEN}' '${STOA_CONTROL_PLANE_URL:-https://api.gostoa.dev}/v1/admin/gateways' | jq '.items[] | select(.mode == \"connect\")'"
