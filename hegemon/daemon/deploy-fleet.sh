#!/usr/bin/env bash
# Deploy HEGEMON daemon binary to all workers in the fleet.
#
# Usage:
#   ./deploy-fleet.sh                     # Deploy to all workers from config.example.yaml
#   ./deploy-fleet.sh host1 host2 host3   # Deploy to specific hosts
#   ./deploy-fleet.sh --status-only       # Just check daemon status on all hosts
#   ./deploy-fleet.sh --build-only        # Build binary, skip deploy
#
# Prerequisites:
#   - Go 1.22+ installed locally
#   - SSH key access to target hosts
#   - config.yaml prepared per host (from config.example.yaml)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
USER="${HEGEMON_USER:-hegemon}"
BINARY="hegemon"
CONFIG="${HEGEMON_CONFIG:-config.yaml}"

# Parse flags.
STATUS_ONLY=false
BUILD_ONLY=false
HOSTS=()

for arg in "$@"; do
  case "$arg" in
    --status-only) STATUS_ONLY=true ;;
    --build-only)  BUILD_ONLY=true ;;
    *)             HOSTS+=("$arg") ;;
  esac
done

# If no hosts given, extract from config.example.yaml.
if [ ${#HOSTS[@]} -eq 0 ]; then
  if [ -f "${SCRIPT_DIR}/config.example.yaml" ]; then
    HOSTS=($(grep -E '^\s+host:' "${SCRIPT_DIR}/config.example.yaml" | awk '{print $2}' | tr -d '"'))
  fi
  if [ ${#HOSTS[@]} -eq 0 ]; then
    echo "ERROR: No hosts provided and none found in config.example.yaml"
    echo "Usage: $0 [--status-only|--build-only] [host1 host2 ...]"
    exit 1
  fi
fi

echo "Fleet: ${HOSTS[*]} (${#HOSTS[@]} hosts)"
echo ""

# Status-only mode: just check systemctl status on each host.
if $STATUS_ONLY; then
  for host in "${HOSTS[@]}"; do
    echo "=== ${host} ==="
    ssh -o ConnectTimeout=5 "${USER}@${host}" "sudo systemctl status hegemon --no-pager 2>&1 | head -15" || echo "  UNREACHABLE"
    echo ""
  done
  exit 0
fi

# Build binary.
echo "=== Building hegemon binary (linux/amd64) ==="
cd "${SCRIPT_DIR}"
GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build -ldflags="-s -w" -o "${BINARY}" ./cmd/hegemon/
ls -lh "${BINARY}"
echo ""

if $BUILD_ONLY; then
  echo "Build complete. Binary: ${SCRIPT_DIR}/${BINARY}"
  exit 0
fi

# Deploy to each host.
FAILED=()
for host in "${HOSTS[@]}"; do
  echo "=== Deploying to ${USER}@${host} ==="
  if "${SCRIPT_DIR}/deploy.sh" "${host}" "${CONFIG}" 2>&1; then
    echo "  OK"
  else
    echo "  FAILED"
    FAILED+=("${host}")
  fi
  echo ""
done

# Cleanup local binary.
rm -f "${SCRIPT_DIR}/${BINARY}"

# Summary.
echo "=== Fleet Deploy Summary ==="
echo "Total: ${#HOSTS[@]}, Failed: ${#FAILED[@]}"
if [ ${#FAILED[@]} -gt 0 ]; then
  echo "Failed hosts: ${FAILED[*]}"
  exit 1
fi
echo "All hosts deployed successfully."
