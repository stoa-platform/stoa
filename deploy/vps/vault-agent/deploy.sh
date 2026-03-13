#!/usr/bin/env bash
# Deploy Vault Agent to a VPS — systemd daemon with AppRole auth
# Phase 3 of Unified Secrets Management (CAB-1799)
#
# Prerequisites:
#   - SSH key: ~/.ssh/id_ed25519_stoa
#   - Vault running at hcvault.gostoa.dev with AppRoles created (Phase 0)
#   - Secrets migrated to Vault (Phase 1)
#   - VAULT_TOKEN set (admin token, for generating AppRole credentials)
#
# Usage:
#   ./deploy.sh <vps-host> <approle-name> <template1> [template2] ...
#
# Examples:
#   ./deploy.sh 51.254.139.205 vps-n8n n8n netbox pocketbase   # n8n VPS (3 services)
#   ./deploy.sh 51.83.45.13 vps-kong kong                       # Kong VPS
#   ./deploy.sh 54.36.209.237 vps-gravitee gravitee              # Gravitee VPS
#   ./deploy.sh 51.255.201.17 vps-webmethods webmethods          # webMethods VPS
#
# For HEGEMON workers, use deploy-hegemon.sh instead (in-memory secrets, no file).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519_stoa}"
VAULT_ADDR="${VAULT_ADDR:-https://hcvault.gostoa.dev}"
VAULT_BINARY_URL="https://releases.hashicorp.com/vault/1.18.4/vault_1.18.4_linux_amd64.zip"
REMOTE_CONFIG_DIR="/etc/vault-agent"
REMOTE_SECRETS_DIR="/opt/secrets"
REMOTE_TEMPLATES_DIR="/etc/vault-agent/templates"

# --- Parse arguments ---
if [ $# -lt 3 ]; then
  echo "Usage: $0 <vps-host> <approle-name> <template1> [template2] ..."
  echo ""
  echo "VPS hosts and roles:"
  echo "  51.254.139.205  vps-n8n        n8n netbox pocketbase"
  echo "  51.83.45.13     vps-kong       kong"
  echo "  54.36.209.237   vps-gravitee   gravitee"
  echo "  51.255.201.17   vps-webmethods webmethods"
  exit 1
fi

VPS_HOST="$1"
APPROLE_NAME="$2"
shift 2
TEMPLATES=("$@")

# Detect SSH user (debian for OVH VPS, root for others)
SSH_USER="${SSH_USER:-debian}"

SSH_CMD="ssh -i ${SSH_KEY} -o StrictHostKeyChecking=accept-new"
SCP_CMD="scp -i ${SSH_KEY} -q"

echo "=== Vault Agent Deploy ==="
echo "Target:   ${SSH_USER}@${VPS_HOST}"
echo "AppRole:  ${APPROLE_NAME}"
echo "Services: ${TEMPLATES[*]}"
echo "Vault:    ${VAULT_ADDR}"
echo ""

# --- Step 1: Generate AppRole credentials from Vault ---
echo "[1/7] Generating AppRole credentials..."
if [ -z "${VAULT_TOKEN:-}" ]; then
  echo "  ERROR: VAULT_TOKEN not set. Export your admin token first."
  exit 1
fi

ROLE_ID=$(curl -sf -H "X-Vault-Token: ${VAULT_TOKEN}" \
  "${VAULT_ADDR}/v1/auth/approle/role/${APPROLE_NAME}/role-id" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['role_id'])")

SECRET_ID=$(curl -sf -X POST -H "X-Vault-Token: ${VAULT_TOKEN}" \
  "${VAULT_ADDR}/v1/auth/approle/role/${APPROLE_NAME}/secret-id" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['secret_id'])")

echo "  Role ID:   ${ROLE_ID:0:8}..."
echo "  Secret ID: ${SECRET_ID:0:8}... (generated)"

# --- Step 2: Install Vault binary on VPS ---
echo "[2/7] Installing Vault binary on VPS..."
$SSH_CMD "${SSH_USER}@${VPS_HOST}" bash -s <<'REMOTE_INSTALL'
if command -v vault &>/dev/null; then
  echo "  Vault $(vault version | head -1) already installed"
else
  echo "  Downloading Vault..."
  cd /tmp
  apt-get -qq update && apt-get -qq install -y unzip curl >/dev/null 2>&1 || true
  curl -sfL "https://releases.hashicorp.com/vault/1.18.4/vault_1.18.4_linux_amd64.zip" -o vault.zip
  unzip -o vault.zip >/dev/null
  mv vault /usr/local/bin/vault
  chmod +x /usr/local/bin/vault
  rm vault.zip
  echo "  Vault $(vault version | head -1) installed"
fi
REMOTE_INSTALL

# --- Step 3: Create directories and write credentials ---
echo "[3/7] Creating directories and writing credentials..."
$SSH_CMD "${SSH_USER}@${VPS_HOST}" bash -s <<REMOTE_DIRS
mkdir -p ${REMOTE_CONFIG_DIR} ${REMOTE_TEMPLATES_DIR} ${REMOTE_SECRETS_DIR}
chmod 750 ${REMOTE_CONFIG_DIR} ${REMOTE_TEMPLATES_DIR}
chmod 700 ${REMOTE_SECRETS_DIR}

# Write AppRole credentials (restrictive permissions)
printenv ROLE_ID_VAL > ${REMOTE_CONFIG_DIR}/role-id 2>/dev/null || echo "${ROLE_ID}" > ${REMOTE_CONFIG_DIR}/role-id
printenv SECRET_ID_VAL > ${REMOTE_CONFIG_DIR}/secret-id 2>/dev/null || echo "${SECRET_ID}" > ${REMOTE_CONFIG_DIR}/secret-id
chmod 600 ${REMOTE_CONFIG_DIR}/role-id ${REMOTE_CONFIG_DIR}/secret-id
REMOTE_DIRS

# Write credentials via separate SSH to avoid shell escaping issues
echo "${ROLE_ID}" | $SSH_CMD "${SSH_USER}@${VPS_HOST}" "cat > ${REMOTE_CONFIG_DIR}/role-id && chmod 600 ${REMOTE_CONFIG_DIR}/role-id"
echo "${SECRET_ID}" | $SSH_CMD "${SSH_USER}@${VPS_HOST}" "cat > ${REMOTE_CONFIG_DIR}/secret-id && chmod 600 ${REMOTE_CONFIG_DIR}/secret-id"

# --- Step 4: Copy templates ---
echo "[4/7] Copying secret templates..."
for tpl in "${TEMPLATES[@]}"; do
  TPL_FILE="${SCRIPT_DIR}/templates/${tpl}.env.tpl"
  if [ ! -f "$TPL_FILE" ]; then
    echo "  ERROR: Template not found: ${TPL_FILE}"
    exit 1
  fi
  $SCP_CMD "$TPL_FILE" "${SSH_USER}@${VPS_HOST}:${REMOTE_TEMPLATES_DIR}/"
  echo "  Copied: ${tpl}.env.tpl"
done

# --- Step 5: Generate and deploy Vault Agent config ---
echo "[5/7] Generating Vault Agent config..."

# Build template stanzas dynamically
TEMPLATE_STANZAS=""
for tpl in "${TEMPLATES[@]}"; do
  # Docker compose project directory — convention: /opt/<service>/
  COMPOSE_DIR="/opt/${tpl}"
  RESTART_CMD="docker compose -f ${COMPOSE_DIR}/docker-compose.yml restart 2>/dev/null || true"

  TEMPLATE_STANZAS="${TEMPLATE_STANZAS}
template {
  source      = \"${REMOTE_TEMPLATES_DIR}/${tpl}.env.tpl\"
  destination = \"${REMOTE_SECRETS_DIR}/${tpl}.env\"
  perms       = 0600
  command     = \"${RESTART_CMD}\"
  error_on_missing_key = true
  wait {
    min = \"5s\"
    max = \"30s\"
  }
}"
done

# Replace placeholders in config template
CONFIG_CONTENT=$(cat "${SCRIPT_DIR}/config.hcl.template")
CONFIG_CONTENT="${CONFIG_CONTENT//__VAULT_ADDR__/${VAULT_ADDR}}"
CONFIG_CONTENT="${CONFIG_CONTENT//__APPROLE_NAME__/${APPROLE_NAME}}"
CONFIG_CONTENT="${CONFIG_CONTENT//__TEMPLATE_STANZAS__/${TEMPLATE_STANZAS}}"

echo "${CONFIG_CONTENT}" | $SSH_CMD "${SSH_USER}@${VPS_HOST}" "cat > ${REMOTE_CONFIG_DIR}/config.hcl && chmod 640 ${REMOTE_CONFIG_DIR}/config.hcl"

# --- Step 6: Install and start systemd service ---
echo "[6/7] Installing systemd service..."
$SCP_CMD "${SCRIPT_DIR}/vault-agent.service" "${SSH_USER}@${VPS_HOST}:/etc/systemd/system/vault-agent.service"

$SSH_CMD "${SSH_USER}@${VPS_HOST}" bash -s <<'REMOTE_SYSTEMD'
systemctl daemon-reload
systemctl enable vault-agent
systemctl restart vault-agent
sleep 3
if systemctl is-active --quiet vault-agent; then
  echo "  vault-agent: ACTIVE"
else
  echo "  vault-agent: FAILED — check: journalctl -u vault-agent --no-pager -n 30"
  exit 1
fi
REMOTE_SYSTEMD

# --- Step 7: Verify secrets rendered ---
echo "[7/7] Verifying rendered secrets..."
for tpl in "${TEMPLATES[@]}"; do
  # Wait up to 15s for the template to render
  FOUND=false
  for attempt in 1 2 3 4 5; do
    FILE_CHECK=$($SSH_CMD "${SSH_USER}@${VPS_HOST}" "test -s ${REMOTE_SECRETS_DIR}/${tpl}.env && echo 'OK' || echo 'MISSING'")
    if [ "$FILE_CHECK" = "OK" ]; then
      KEY_COUNT=$($SSH_CMD "${SSH_USER}@${VPS_HOST}" "grep -c '=' ${REMOTE_SECRETS_DIR}/${tpl}.env 2>/dev/null || echo 0")
      echo "  ${tpl}.env: OK (${KEY_COUNT} keys)"
      FOUND=true
      break
    fi
    sleep 3
  done
  if [ "$FOUND" = false ]; then
    echo "  ${tpl}.env: NOT RENDERED — check: journalctl -u vault-agent --no-pager -n 50"
  fi
done

echo ""
echo "=== Vault Agent Deploy Complete ==="
echo ""
echo "Service: systemctl status vault-agent"
echo "Logs:    journalctl -u vault-agent -f"
echo "Secrets: ls -la ${REMOTE_SECRETS_DIR}/"
echo ""
echo "Next: update docker-compose.yml to use env_file: ${REMOTE_SECRETS_DIR}/<service>.env"
echo "Then: remove old plaintext .env files"
