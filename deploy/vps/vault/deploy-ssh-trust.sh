#!/usr/bin/env bash
# =============================================================================
# Deploy Vault SSH CA Trust to All VPS
# =============================================================================
# Deploys the Vault SSH CA public key to all VPS so they trust
# Vault-signed certificates. Configures sshd TrustedUserCAKeys.
#
# Usage:
#   ./deploy-ssh-trust.sh              # Deploy CA to all VPS
#   ./deploy-ssh-trust.sh --dry-run    # Show what would be done
#   ./deploy-ssh-trust.sh --verify     # Verify CA is trusted on all VPS
#
# Prerequisites:
#   - SSH access from current device (STOA_SSH_KEY)
#   - CA public key exists (run setup-ssh-engine.sh first)
#
# Phase 5 — CAB-1802
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPS_DIR="${SCRIPT_DIR}/../../../scripts/ops"
source "${OPS_DIR}/vps-inventory.sh"

CA_PUBKEY_FILE="${SCRIPT_DIR}/ssh-ca-pubkey.pem"
REMOTE_CA_PATH="/etc/ssh/vault-ca.pub"
SSHD_CONFIG="/etc/ssh/sshd_config"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

DRY_RUN=false
VERIFY_ONLY=false

for arg in "$@"; do
  case $arg in
    --dry-run) DRY_RUN=true ;;
    --verify)  VERIFY_ONLY=true ;;
  esac
done

# --- Verify mode ---
if [ "$VERIFY_ONLY" = true ]; then
  echo -e "${CYAN}=== Verifying Vault SSH CA Trust ===${NC}"
  echo ""
  success=0
  fail=0
  for entry in "${VPS_FLEET[@]}"; do
    IFS='|' read -r name ip user purpose <<< "$entry"
    echo -n "  $name ($ip)... "
    if ssh -i "$STOA_SSH_KEY" -o ConnectTimeout=10 "${user}@${ip}" \
      "test -f ${REMOTE_CA_PATH} && grep -q 'TrustedUserCAKeys' ${SSHD_CONFIG}" 2>/dev/null; then
      echo -e "${GREEN}[trusted]${NC}"
      ((success++))
    else
      echo -e "${RED}[not configured]${NC}"
      ((fail++))
    fi
  done
  echo ""
  echo -e "Trusted: ${GREEN}${success}${NC} / ${#VPS_FLEET[@]}"
  [ $fail -gt 0 ] && echo -e "${YELLOW}Run without --verify to deploy CA to remaining VPS.${NC}"
  exit 0
fi

# --- Pre-flight checks ---
if [ ! -f "$CA_PUBKEY_FILE" ]; then
  echo "ERROR: CA public key not found at ${CA_PUBKEY_FILE}"
  echo "  Run ./setup-ssh-engine.sh first (or --export-ca)"
  exit 1
fi

CA_CONTENT=$(cat "$CA_PUBKEY_FILE")

echo -e "${CYAN}=== Deploying Vault SSH CA to VPS Fleet ===${NC}"
echo -e "  CA key:    ${CA_PUBKEY_FILE}"
echo -e "  Remote:    ${REMOTE_CA_PATH}"
echo -e "  Dry run:   ${DRY_RUN}"
echo ""

# Also include HEGEMON workers
HEGEMON_WORKERS_FILE="${SCRIPT_DIR}/../hegemon/workers.txt"
EXTRA_HOSTS=()
if [ -f "$HEGEMON_WORKERS_FILE" ]; then
  while IFS='|' read -r name ip || [ -n "$name" ]; do
    [ -z "$name" ] || [[ "$name" == \#* ]] && continue
    EXTRA_HOSTS+=("${name}|${ip}|root|HEGEMON worker")
  done < "$HEGEMON_WORKERS_FILE"
fi

ALL_HOSTS=("${VPS_FLEET[@]}" ${EXTRA_HOSTS[@]+"${EXTRA_HOSTS[@]}"})

success=0
fail=0

for entry in "${ALL_HOSTS[@]}"; do
  IFS='|' read -r name ip user purpose <<< "$entry"
  echo -n "  $name ($ip, $user)... "

  if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}[dry-run]${NC}"
    continue
  fi

  # Deploy CA public key + configure sshd (idempotent)
  if ssh -i "$STOA_SSH_KEY" -o ConnectTimeout=10 "${user}@${ip}" bash -s <<REMOTE_SCRIPT 2>/dev/null; then
    # Write CA public key
    echo '${CA_CONTENT}' | sudo tee ${REMOTE_CA_PATH} > /dev/null
    sudo chmod 644 ${REMOTE_CA_PATH}

    # Add TrustedUserCAKeys if not already present
    if ! grep -q 'TrustedUserCAKeys ${REMOTE_CA_PATH}' ${SSHD_CONFIG} 2>/dev/null; then
      echo "" | sudo tee -a ${SSHD_CONFIG} > /dev/null
      echo "# Vault SSH CA — trust Vault-signed certificates (CAB-1802)" | sudo tee -a ${SSHD_CONFIG} > /dev/null
      echo "TrustedUserCAKeys ${REMOTE_CA_PATH}" | sudo tee -a ${SSHD_CONFIG} > /dev/null
      # Validate config before reloading
      if sudo sshd -t 2>/dev/null; then
        sudo systemctl reload sshd 2>/dev/null || sudo systemctl reload ssh 2>/dev/null || true
        echo "configured+reloaded"
      else
        echo "ERROR: sshd config validation failed" >&2
        exit 1
      fi
    else
      # Update CA key content (idempotent)
      echo '${CA_CONTENT}' | sudo tee ${REMOTE_CA_PATH} > /dev/null
      echo "already-configured"
    fi
REMOTE_SCRIPT
    echo -e "${GREEN}[ok]${NC}"
    ((success++))
  else
    echo -e "${RED}[fail]${NC}"
    ((fail++))
  fi
done

echo ""
echo -e "${CYAN}=== Summary ===${NC}"
echo -e "  Success: ${GREEN}${success}${NC}"
echo -e "  Failed:  ${RED}${fail}${NC}"
echo -e "  Total:   ${#ALL_HOSTS[@]}"
echo ""
echo "Verify: $0 --verify"
echo ""
echo "Test signed SSH login:"
echo "  vault write -field=signed_key ssh-client-signer/sign/admin public_key=@~/.ssh/id_ed25519.pub > ~/.ssh/id_ed25519-cert.pub"
echo "  ssh -o CertificateFile=~/.ssh/id_ed25519-cert.pub debian@<vps-ip>"

if [ $fail -gt 0 ]; then
  echo -e "\n${YELLOW}Some VPS were unreachable. Retry or check SSH access.${NC}"
  exit 1
fi
