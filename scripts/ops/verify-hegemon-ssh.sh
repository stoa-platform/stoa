#!/bin/bash
#
# verify-hegemon-ssh.sh — Test SSH connectivity to HEGEMON workers
#
# Usage:
#   ./verify-hegemon-ssh.sh              # Test all workers
#   ./verify-hegemon-ssh.sh "$HEGEMON_W1_IP"  # Test specific worker
#   ./verify-hegemon-ssh.sh --fix        # Attempt auto-fix (requires worker-3 access)
#
# Exit codes:
#   0 = All workers reachable
#   1 = Some workers unreachable
#   2 = Critical error (invalid args)
#

set -e

# Worker inventory — IPs sourced from env vars (see stoa-infra/docs/carto/dns-inventory.md)
# Override any individual IP via env: HEGEMON_W1_IP=x.x.x.x ./verify-hegemon-ssh.sh
declare -A WORKERS=(
  [worker-1]="${HEGEMON_W1_IP:?Set HEGEMON_W1_IP}"
  [worker-2]="${HEGEMON_W2_IP:?Set HEGEMON_W2_IP}"
  [worker-3]="${HEGEMON_W3_IP:?Set HEGEMON_W3_IP}"
  [worker-4]="${HEGEMON_W4_IP:?Set HEGEMON_W4_IP}"
  [worker-5]="${HEGEMON_W5_IP:?Set HEGEMON_W5_IP}"
)

SSH_KEY="${STOA_SSH_KEY:=$HOME/.ssh/id_ed25519_stoa}"
SSH_USER="hegemon"
SSH_TIMEOUT=5
VERBOSE=false
FIX_MODE=false

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
  echo -e "\n${BLUE}=== $1 ===${NC}"
}

print_ok() {
  echo -e "${GREEN}✓${NC} $1"
}

print_fail() {
  echo -e "${RED}✗${NC} $1"
}

print_warn() {
  echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
  echo -e "  → $1"
}

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS] [WORKER_IP]

Test SSH connectivity to HEGEMON workers.

Options:
  --help          Show this help message
  --verbose       Verbose output
  --fix           Attempt auto-fix using worker-3 as bastion
  --key PATH      SSH key path (default: \$STOA_SSH_KEY or ~/.ssh/id_ed25519_stoa)

Examples:
  # Test all workers
  $(basename "$0")

  # Test specific worker
  $(basename "$0") "\$HEGEMON_W1_IP"

  # Verbose output
  $(basename "$0") --verbose

  # Auto-fix (requires worker-3 access)
  $(basename "$0") --fix
EOF
  exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --help)
      usage
      ;;
    --verbose)
      VERBOSE=true
      shift
      ;;
    --fix)
      FIX_MODE=true
      shift
      ;;
    --key)
      SSH_KEY="$2"
      shift 2
      ;;
    *)
      # Check if it's a valid IP
      if [[ $1 =~ ^[0-9.]+$ ]]; then
        TEST_IP="$1"
      else
        print_fail "Unknown option: $1"
        usage
      fi
      shift
      ;;
  esac
done

# Verify SSH key exists
if [[ ! -f "$SSH_KEY" ]]; then
  print_fail "SSH key not found: $SSH_KEY"
  echo "Set STOA_SSH_KEY or use --key option"
  exit 2
fi

# Test connectivity to a single worker
test_worker() {
  local name="$1"
  local ip="$2"

  # Skip if testing specific IP and it doesn't match
  if [[ -n "$TEST_IP" && "$ip" != "$TEST_IP" ]]; then
    return 0
  fi

  if $VERBOSE; then
    print_info "Testing $name ($ip)..."
  fi

  # Test SSH connection
  if timeout $SSH_TIMEOUT ssh \
    -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    -o ConnectTimeout=$SSH_TIMEOUT \
    -i "$SSH_KEY" \
    "${SSH_USER}@${ip}" \
    "echo OK" &>/dev/null; then

    print_ok "$name ($ip) — reachable"

    # Get additional info if verbose
    if $VERBOSE; then
      uptime_info=$(ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -i "$SSH_KEY" "${SSH_USER}@${ip}" "uptime" 2>/dev/null || echo "unknown")
      print_info "  Uptime: $uptime_info"

      service_status=$(ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -i "$SSH_KEY" "${SSH_USER}@${ip}" \
        "systemctl is-enabled hegemon-agent.service 2>/dev/null || echo 'N/A'" 2>/dev/null)
      print_info "  Service status: $service_status"
    fi

    return 0
  else
    print_fail "$name ($ip) — unreachable"
    UNREACHABLE_WORKERS+=("$name")
    UNREACHABLE_IPS+=("$ip")
    return 1
  fi
}

print_header "HEGEMON SSH Connectivity Check"
echo "SSH Key: $SSH_KEY"
echo "User: $SSH_USER"
echo "Timeout: ${SSH_TIMEOUT}s"

# Arrays to track unreachable workers
declare -a UNREACHABLE_WORKERS=()
declare -a UNREACHABLE_IPS=()

# Test all workers
for worker in "${!WORKERS[@]}"; do
  ip="${WORKERS[$worker]}"
  test_worker "$worker" "$ip" || true
done

print_header "Summary"

if [[ ${#UNREACHABLE_WORKERS[@]} -eq 0 ]]; then
  print_ok "All workers reachable ✓"
  exit 0
else
  print_fail "${#UNREACHABLE_WORKERS[@]} worker(s) unreachable:"
  for i in "${!UNREACHABLE_WORKERS[@]}"; do
    print_info "${UNREACHABLE_WORKERS[$i]} (${UNREACHABLE_IPS[$i]})"
  done

  echo ""
  echo "Recovery steps:"
  print_info "1. Follow the recovery procedure in docs/runbooks/hegemon-ssh-recovery.md"
  print_info "2. Use Contabo VNC console to deploy SSH key"
  print_info "3. Re-run this script to verify: ./$(basename "$0") --verbose"

  if [[ "$FIX_MODE" == true ]]; then
    print_warn "Auto-fix mode requested (not yet implemented)"
    print_info "Currently requires manual VNC console access"
  fi

  exit 1
fi
