#!/usr/bin/env bash
# Gateway Arena — Enterprise AI Readiness Orchestrator (Layer 1)
#
# Runs enterprise k6 scenarios for each gateway. Gateways without MCP
# endpoints score 0 (not N/A) — the spec is open for anyone to implement.
#
# Env vars:
#   GATEWAYS          — JSON array with mcp_base field (null = no MCP support)
#   PUSHGATEWAY_URL   — Pushgateway URL (default: http://pushgateway.monitoring.svc:9091)
#   PUSHGATEWAY_AUTH  — Basic auth user:pass for external Pushgateway (optional)
#   RUNS              — Number of runs per gateway (default: 3)
#   DISCARD_FIRST     — Discard first N runs as warm-up (default: 1)
#   TIMEOUT           — Request timeout in seconds (default: 10)
#   ARENA_JWT         — Bearer token for authenticated scenarios (optional)
#   SCRIPT_PATH       — Path to benchmark-enterprise.js (default: /scripts/benchmark-enterprise.js)
#   ARENA_INSTANCE    — Instance label for Pushgateway grouping (default: "default")
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PUSHGATEWAY_URL="${PUSHGATEWAY_URL:-http://pushgateway.monitoring.svc:9091}"
RUNS="${RUNS:-3}"
DISCARD_FIRST="${DISCARD_FIRST:-1}"
TIMEOUT="${TIMEOUT:-10}"
SCRIPT_PATH="${SCRIPT_PATH:-/scripts/benchmark-enterprise.js}"
ARENA_INSTANCE="${ARENA_INSTANCE:-default}"
ARENA_JWT="${ARENA_JWT:-}"
SCENARIOS="ent_mcp_discovery ent_mcp_toolcall ent_auth_chain ent_policy_eval ent_guardrails ent_quota_burst ent_resilience ent_governance"
WORK_DIR="/tmp/arena-enterprise"

log_json() {
  local ts
  ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  echo "{\"time\":\"${ts}\",\"level\":\"INFO\",\"msg\":$1}"
}

log_json "\"Arena Enterprise orchestrator starting (Layer 1)\""

# Parse GATEWAYS JSON
if [ -z "${GATEWAYS:-}" ]; then
  echo "ERROR: GATEWAYS env var not set" >&2
  exit 1
fi

GATEWAY_COUNT=$(echo "$GATEWAYS" | jq 'length')
log_json "$(echo "$GATEWAYS" | jq -c '{event:"enterprise_config",gateways:length,runs:'"$RUNS"',discard:'"$DISCARD_FIRST"'}')"

rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"

# ---------------------------------------------------------------------------
# Run benchmarks
# ---------------------------------------------------------------------------
for gw_idx in $(seq 0 $((GATEWAY_COUNT - 1))); do
  GW_NAME=$(echo "$GATEWAYS" | jq -r ".[$gw_idx].name")
  GW_TARGET=$(echo "$GATEWAYS" | jq -r ".[$gw_idx].target // .[$gw_idx].health")
  GW_MCP=$(echo "$GATEWAYS" | jq -r ".[$gw_idx].mcp_base // empty")
  GW_MCP_PROTO=$(echo "$GATEWAYS" | jq -r ".[$gw_idx].mcp_protocol // \"stoa\"")
  GW_HEADERS=$(echo "$GATEWAYS" | jq -c ".[$gw_idx].proxy_headers // {}")

  log_json "\"Benchmarking gateway: ${GW_NAME} (mcp_base: ${GW_MCP:-none})\""
  mkdir -p "$WORK_DIR/$GW_NAME"

  for run in $(seq 1 "$RUNS"); do
    mkdir -p "$WORK_DIR/$GW_NAME/run-$run"

    # Warm-up run
    k6 run \
      --env SCENARIO=ent_warmup \
      --env TARGET_URL="$GW_TARGET" \
      --env MCP_BASE="$GW_MCP" \
      --env MCP_PROTOCOL="$GW_MCP_PROTO" \
      --env HEADERS="$GW_HEADERS" \
      --env ARENA_JWT="$ARENA_JWT" \
      --env TIMEOUT="$TIMEOUT" \
      --env SUMMARY_FILE="/dev/null" \
      --quiet \
      "$SCRIPT_PATH" 2>/dev/null || true

    # Run each enterprise scenario
    for scenario in $SCENARIOS; do
      SUMMARY_FILE="$WORK_DIR/$GW_NAME/run-$run/${scenario}.json"
      k6 run \
        --env SCENARIO="$scenario" \
        --env TARGET_URL="$GW_TARGET" \
        --env MCP_BASE="$GW_MCP" \
        --env MCP_PROTOCOL="$GW_MCP_PROTO" \
        --env HEADERS="$GW_HEADERS" \
        --env ARENA_JWT="$ARENA_JWT" \
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
SCORER_STDERR="$WORK_DIR/scorer_stderr.txt"
SCORER_PATH="$(dirname "$SCRIPT_PATH")/run-arena-enterprise.py"

log_json "\"Computing enterprise scores via run-arena-enterprise.py\""
python3 "$SCORER_PATH" "$WORK_DIR" "$GATEWAYS" > "$METRICS_FILE" 2> "$SCORER_STDERR"

# Log scorer stderr
while IFS= read -r line; do
  log_json "\"$line\""
done < "$SCORER_STDERR"

# ---------------------------------------------------------------------------
# Push to Pushgateway
# ---------------------------------------------------------------------------
PUSH_URL="${PUSHGATEWAY_URL}/metrics/job/gateway_arena_enterprise/instance/${ARENA_INSTANCE}"
RESPONSE_FILE="$WORK_DIR/push_response.txt"
CURL_AUTH=""
if [ -n "${PUSHGATEWAY_AUTH:-}" ]; then
  CURL_AUTH="-u ${PUSHGATEWAY_AUTH}"
fi
HTTP_CODE=$(curl -s -o "$RESPONSE_FILE" -w "%{http_code}" -X PUT --data-binary @"$METRICS_FILE" \
  -H "Content-Type: text/plain" $CURL_AUTH "$PUSH_URL" 2>/dev/null)
[ -z "$HTTP_CODE" ] && HTTP_CODE="000"

if [ "$HTTP_CODE" -lt 300 ] && [ "$HTTP_CODE" != "000" ]; then
  METRIC_LINES=$(wc -l < "$METRICS_FILE" | tr -d ' ')
  log_json "\"Pushed $METRIC_LINES enterprise metric lines to $PUSH_URL (HTTP $HTTP_CODE)\""
else
  RESP_BODY=$(cat "$RESPONSE_FILE" 2>/dev/null | head -c 500 | tr '"' "'")
  METRIC_SIZE=$(wc -c < "$METRICS_FILE" | tr -d ' ')
  log_json "\"WARNING: Pushgateway returned HTTP $HTTP_CODE (payload ${METRIC_SIZE} bytes): $RESP_BODY\""
fi

# Cleanup
rm -rf "$WORK_DIR"

log_json "\"Arena Enterprise orchestrator finished\""
