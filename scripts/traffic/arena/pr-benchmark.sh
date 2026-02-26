#!/usr/bin/env bash
# PR benchmark — runs on PRs touching stoa-gateway, compares against baseline.
#
# Starts the gateway binary, runs k6 for each scenario, then invokes
# compare_results.py to detect regressions.
#
# Usage:
#   pr-benchmark.sh <gateway_binary> <baseline_dir> <results_dir>
#
# Env vars:
#   GATEWAY_PORT  — Port for the gateway (default: 8091)
#   K6_BINARY     — Path to k6 binary (default: k6)
#   FAIL_ON_WARN  — Set to "true" to fail on WARN verdicts (default: false)
set -euo pipefail

GATEWAY_BINARY="${1:?Usage: pr-benchmark.sh <gateway_binary> <baseline_dir> <results_dir>}"
BASELINE_DIR="${2:?Usage: pr-benchmark.sh <gateway_binary> <baseline_dir> <results_dir>}"
RESULTS_DIR="${3:?Usage: pr-benchmark.sh <gateway_binary> <baseline_dir> <results_dir>}"
GATEWAY_PORT="${GATEWAY_PORT:-8091}"
K6_BINARY="${K6_BINARY:-k6}"
FAIL_ON_WARN="${FAIL_ON_WARN:-false}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCENARIOS="health sequential burst_50"

log() { echo "[pr-bench] $(date -u +%H:%M:%S) $*"; }

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
mkdir -p "$RESULTS_DIR"

for scenario in $SCENARIOS; do
  SUMMARY_FILE="${RESULTS_DIR}/${scenario}.json"
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

log "Benchmarking complete. Results in ${RESULTS_DIR}/"

# -------------------------------------------------------------------
# 4. Compare against baseline
# -------------------------------------------------------------------
log "Comparing against baseline at ${BASELINE_DIR}..."

COMPARE_ARGS=("$BASELINE_DIR" "$RESULTS_DIR")
if [ "$FAIL_ON_WARN" = "true" ]; then
  COMPARE_ARGS+=("--fail-on-warn")
fi

python3 "${SCRIPT_DIR}/compare_results.py" "${COMPARE_ARGS[@]}"
