#!/usr/bin/env bash
# =============================================================================
# STOA Platform — SSH Key Distribution
# =============================================================================
# Distributes a new SSH public key to all VPS in the fleet.
# Run from a device that ALREADY has SSH access (e.g., desktop).
#
# Usage:
#   ./scripts/ops/distribute-ssh-key.sh ~/.ssh/id_ed25519_stoa_laptop.pub
#   ./scripts/ops/distribute-ssh-key.sh ~/.ssh/id_ed25519_stoa_laptop.pub --dry-run
#   ./scripts/ops/distribute-ssh-key.sh --remove ~/.ssh/id_ed25519_stoa_laptop.pub
#
# Prerequisites:
#   - SSH access from current device (STOA_SSH_KEY or ~/.ssh/id_ed25519_stoa)
#   - Target public key file exists
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/vps-inventory.sh"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

DRY_RUN=false
REMOVE=false
PUBKEY_FILE=""

usage() {
  echo "Usage: $0 [--remove] [--dry-run] <pubkey-file>"
  echo ""
  echo "Options:"
  echo "  --dry-run     Show what would be done without making changes"
  echo "  --remove      Remove the key from all VPS instead of adding it"
  echo ""
  echo "Examples:"
  echo "  $0 ~/.ssh/id_ed25519_stoa_laptop.pub         # Add laptop key to all VPS"
  echo "  $0 --remove ~/.ssh/id_ed25519_stoa_laptop.pub # Revoke laptop key from all VPS"
  exit 1
}

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=true; shift ;;
    --remove)  REMOVE=true; shift ;;
    -h|--help) usage ;;
    *)
      if [ -z "$PUBKEY_FILE" ]; then
        PUBKEY_FILE="$1"
      else
        echo "Unknown argument: $1" >&2; usage
      fi
      shift ;;
  esac
done

[ -z "$PUBKEY_FILE" ] && usage
[ ! -f "$PUBKEY_FILE" ] && { echo -e "${RED}File not found: $PUBKEY_FILE${NC}"; exit 1; }

PUBKEY=$(cat "$PUBKEY_FILE")
KEY_FINGERPRINT=$(ssh-keygen -lf "$PUBKEY_FILE" | awk '{print $2}')
KEY_COMMENT=$(awk '{print $3}' "$PUBKEY_FILE")

echo ""
echo -e "${CYAN}=== STOA SSH Key Distribution ===${NC}"
echo -e "  Key:         ${KEY_COMMENT:-unknown} (${KEY_FINGERPRINT})"
echo -e "  Action:      $([ "$REMOVE" = true ] && echo "REMOVE" || echo "ADD")"
echo -e "  Dry run:     $DRY_RUN"
echo -e "  Source key:  $STOA_SSH_KEY"
echo ""

# Also include HEGEMON workers if workers.txt exists
HEGEMON_WORKERS_FILE="$SCRIPT_DIR/../../deploy/vps/hegemon/workers.txt"
EXTRA_HOSTS=()
if [ -f "$HEGEMON_WORKERS_FILE" ]; then
  while IFS='|' read -r name ip || [ -n "$name" ]; do
    [ -z "$name" ] || [[ "$name" == \#* ]] && continue
    EXTRA_HOSTS+=("${name}|${ip}|hegemon|HEGEMON worker")
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

  if [ "$REMOVE" = true ]; then
    # Remove the key (match by fingerprint to avoid partial line issues)
    if ssh -i "$STOA_SSH_KEY" -o ConnectTimeout=10 "${user}@${ip}" \
      "grep -v '${KEY_FINGERPRINT}' ~/.ssh/authorized_keys > ~/.ssh/authorized_keys.tmp && \
       mv ~/.ssh/authorized_keys.tmp ~/.ssh/authorized_keys && \
       chmod 600 ~/.ssh/authorized_keys" 2>/dev/null; then
      echo -e "${GREEN}[removed]${NC}"
      ((success++))
    else
      echo -e "${RED}[fail]${NC}"
      ((fail++))
    fi
  else
    # Add the key (idempotent — skip if already present)
    if ssh -i "$STOA_SSH_KEY" -o ConnectTimeout=10 "${user}@${ip}" \
      "grep -qF '${KEY_FINGERPRINT}' ~/.ssh/authorized_keys 2>/dev/null && \
       echo 'already present' || \
       (echo '${PUBKEY}' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && echo 'added')" 2>/dev/null; then
      echo -e "${GREEN}[ok]${NC}"
      ((success++))
    else
      echo -e "${RED}[fail]${NC}"
      ((fail++))
    fi

    # Also add to root if current user has sudo (for VPS that need root access during setup)
    if [ "$user" != "root" ]; then
      ssh -i "$STOA_SSH_KEY" -o ConnectTimeout=10 "${user}@${ip}" \
        "sudo grep -qF '${KEY_FINGERPRINT}' /root/.ssh/authorized_keys 2>/dev/null || \
         sudo sh -c 'echo \"${PUBKEY}\" >> /root/.ssh/authorized_keys'" 2>/dev/null || true
    fi
  fi
done

echo ""
echo -e "${CYAN}=== Summary ===${NC}"
echo -e "  Success: ${GREEN}${success}${NC}"
echo -e "  Failed:  ${RED}${fail}${NC}"
echo -e "  Total:   ${#ALL_HOSTS[@]}"

if [ $fail -gt 0 ]; then
  echo -e "\n${YELLOW}Some VPS were unreachable. Retry or check SSH access.${NC}"
  exit 1
fi
