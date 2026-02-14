#!/usr/bin/env bash
# Gateway Arena — k6 Orchestrator
#
# Runs k6 benchmark for each gateway, N runs per gateway, computes median
# composite score, and pushes metrics to Prometheus Pushgateway.
#
# Env vars:
#   GATEWAYS        — JSON array of gateway configs (same format as Python version)
#   PUSHGATEWAY_URL — Pushgateway URL (default: http://pushgateway.monitoring.svc:9091)
#   RUNS            — Number of runs per gateway (default: 5)
#   DISCARD_FIRST   — Discard first N runs as JVM warm-up (default: 1)
#   TIMEOUT         — Request timeout in seconds (default: 5)
#   SCRIPT_PATH     — Path to benchmark.js (default: /scripts/benchmark.js)
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PUSHGATEWAY_URL="${PUSHGATEWAY_URL:-http://pushgateway.monitoring.svc:9091}"
RUNS="${RUNS:-5}"
DISCARD_FIRST="${DISCARD_FIRST:-1}"
TIMEOUT="${TIMEOUT:-5}"
SCRIPT_PATH="${SCRIPT_PATH:-/scripts/benchmark.js}"
SCENARIOS="health sequential burst_10 burst_50 burst_100 sustained"
WORK_DIR="/tmp/arena"

log_json() {
  local ts
  ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  echo "{\"time\":\"${ts}\",\"level\":\"INFO\",\"msg\":$1}"
}

log_json "\"Arena k6 orchestrator starting\""

# Parse GATEWAYS JSON
if [ -z "${GATEWAYS:-}" ]; then
  echo "ERROR: GATEWAYS env var not set" >&2
  exit 1
fi

GATEWAY_COUNT=$(echo "$GATEWAYS" | jq 'length')
log_json "$(echo "$GATEWAYS" | jq -c '{event:"config",gateways:length,runs:'"$RUNS"',discard:'"$DISCARD_FIRST"',scenarios:"'"$SCENARIOS"'"}')"

rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"

# ---------------------------------------------------------------------------
# Run benchmarks
# ---------------------------------------------------------------------------
for gw_idx in $(seq 0 $((GATEWAY_COUNT - 1))); do
  GW_NAME=$(echo "$GATEWAYS" | jq -r ".[$gw_idx].name")
  GW_HEALTH=$(echo "$GATEWAYS" | jq -r ".[$gw_idx].health")
  GW_PROXY=$(echo "$GATEWAYS" | jq -r ".[$gw_idx].proxy")
  GW_HEADERS=$(echo "$GATEWAYS" | jq -c ".[$gw_idx].proxy_headers // {}")

  log_json "\"Benchmarking gateway: ${GW_NAME}\""
  mkdir -p "$WORK_DIR/$GW_NAME"

  for run in $(seq 1 "$RUNS"); do
    mkdir -p "$WORK_DIR/$GW_NAME/run-$run"

    # Warm-up run (output discarded)
    k6 run \
      --env SCENARIO=warmup \
      --env TARGET_URL="$GW_PROXY" \
      --env HEALTH_URL="$GW_HEALTH" \
      --env HEADERS="$GW_HEADERS" \
      --env TIMEOUT="$TIMEOUT" \
      --env SUMMARY_FILE="/dev/null" \
      --quiet \
      "$SCRIPT_PATH" 2>/dev/null || true

    # Run each scenario
    for scenario in $SCENARIOS; do
      SUMMARY_FILE="$WORK_DIR/$GW_NAME/run-$run/${scenario}.json"
      k6 run \
        --env SCENARIO="$scenario" \
        --env TARGET_URL="$GW_PROXY" \
        --env HEALTH_URL="$GW_HEALTH" \
        --env HEADERS="$GW_HEADERS" \
        --env TIMEOUT="$TIMEOUT" \
        --env SUMMARY_FILE="$SUMMARY_FILE" \
        --quiet \
        "$SCRIPT_PATH" 2>/dev/null || true
    done

    log_json "\"Run $run/$RUNS complete for $GW_NAME\""
  done
done

# ---------------------------------------------------------------------------
# Compute scores + CI95 via Python aggregator
# ---------------------------------------------------------------------------
METRICS_FILE="$WORK_DIR/metrics.txt"
SCORER_PATH="$(dirname "$SCRIPT_PATH")/run-arena.py"

log_json "\"Computing scores with CI95 via run-arena.py\""
python3 "$SCORER_PATH" "$WORK_DIR" "$GATEWAYS" > "$METRICS_FILE" 2> >(while IFS= read -r line; do
  log_json "\"$line\""
done)

# ---------------------------------------------------------------------------
# Push to Pushgateway
# ---------------------------------------------------------------------------
PUSH_URL="${PUSHGATEWAY_URL}/metrics/job/gateway_arena"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X PUT --data-binary @"$METRICS_FILE" \
  -H "Content-Type: text/plain" "$PUSH_URL" 2>/dev/null)
[ -z "$HTTP_CODE" ] && HTTP_CODE="000"

if [ "$HTTP_CODE" -lt 300 ] && [ "$HTTP_CODE" != "000" ]; then
  METRIC_LINES=$(wc -l < "$METRICS_FILE" | tr -d ' ')
  log_json "\"Pushed $METRIC_LINES metric lines to $PUSH_URL\""
else
  log_json "\"WARNING: Pushgateway returned HTTP $HTTP_CODE\""
fi

# Cleanup
rm -rf "$WORK_DIR"

log_json "\"Arena k6 orchestrator finished\""
