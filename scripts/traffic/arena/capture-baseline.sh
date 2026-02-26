#!/usr/bin/env bash
# Capture performance baseline — runs after merge to main.
#
# Starts the gateway binary, waits for health, runs k6 for each scenario,
# and saves JSON summaries to the baseline directory.
#
# Usage:
#   capture-baseline.sh <gateway_binary> <output_dir>
#
# Env vars:
#   GATEWAY_PORT — Port for the gateway (default: 8090)
#   K6_BINARY    — Path to k6 binary (default: k6)
set -euo pipefail

GATEWAY_BINARY="${1:?Usage: capture-baseline.sh <gateway_binary> <output_dir>}"
OUTPUT_DIR="${2:?Usage: capture-baseline.sh <gateway_binary> <output_dir>}"
GATEWAY_PORT="${GATEWAY_PORT:-8090}"
K6_BINARY="${K6_BINARY:-k6}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCENARIOS="health sequential burst_50"

log() { echo "[baseline] $(date -u +%H:%M:%S) $*"; }

# -------------------------------------------------------------------
# 1. Start gateway
# -------------------------------------------------------------------
log "Starting gateway on port ${GATEWAY_PORT}..."
"$GATEWAY_BINARY" --port "$GATEWAY_PORT" &
GATEWAY_PID=$!

cleanup() {
  log "Stopping gateway (PID ${GATEWAY_PID})..."
  kill "$GATEWAY_PID" 2>/dev/null || true
  wait "$GATEWAY_PID" 2>/dev/null || true
}
trap cleanup EXIT

# -------------------------------------------------------------------
# 2. Wait for health
# -------------------------------------------------------------------
HEALTH_URL="http://127.0.0.1:${GATEWAY_PORT}/health"
log "Waiting for gateway at ${HEALTH_URL}..."
for i in $(seq 1 30); do
  if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
    log "Gateway healthy after ${i}s"
    break
  fi
  if [ "$i" -eq 30 ]; then
    log "ERROR: Gateway not healthy after 30s"
    exit 1
  fi
  sleep 1
done

# -------------------------------------------------------------------
# 3. Run k6 scenarios
# -------------------------------------------------------------------
TARGET_URL="http://127.0.0.1:${GATEWAY_PORT}/echo/get"
mkdir -p "$OUTPUT_DIR"

for scenario in $SCENARIOS; do
  SUMMARY_FILE="${OUTPUT_DIR}/${scenario}.json"
  log "Running scenario: ${scenario} → ${SUMMARY_FILE}"

  "$K6_BINARY" run \
    --env SCENARIO="$scenario" \
    --env TARGET_URL="$TARGET_URL" \
    --env HEALTH_URL="$HEALTH_URL" \
    --env SUMMARY_FILE="$SUMMARY_FILE" \
    --quiet \
    "${SCRIPT_DIR}/benchmark-ci.js" 2>/dev/null || {
      log "WARNING: Scenario ${scenario} had errors (continuing)"
    }
done

log "Baseline capture complete. Results in ${OUTPUT_DIR}/"
ls -la "$OUTPUT_DIR/"
