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

# Scoring caps (same as Python version)
CAP_BASE=0.4        # 400ms for sequential P95
CAP_BURST50=2.5     # 2500ms for burst_50 P95
CAP_BURST100=4.0    # 4000ms for burst_100 P95

# Scoring weights (same as Python version)
W_BASE=0.15
W_BURST50=0.25
W_BURST100=0.25
W_AVAIL=0.15
W_ERROR=0.10
W_CONSIST=0.10

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
# Compute scores (median of valid runs, discard first N)
# ---------------------------------------------------------------------------
METRICS_FILE="$WORK_DIR/metrics.txt"
LEADERBOARD="[]"

# Extract a percentile from k6 JSON summary (returns seconds, k6 reports ms)
# Usage: extract_pct <json_file> <percentile_key>  e.g. "p(95)"
extract_pct() {
  local json_file="$1" key="$2"
  if [ -f "$json_file" ]; then
    jq -r ".metrics.http_req_duration.values[\"$key\"] // 0" "$json_file" 2>/dev/null | awk '{printf "%.6f", $1/1000}'
  else
    echo "0"
  fi
}

# Extract check pass/fail counts
extract_checks() {
  local json_file="$1" field="$2"  # field: passes or fails
  if [ -f "$json_file" ]; then
    jq -r ".metrics.checks.values.$field // 0" "$json_file" 2>/dev/null
  else
    echo "0"
  fi
}

# Median of an array (expects newline-separated values on stdin)
median() {
  sort -n | awk '{a[NR]=$1} END{print a[int((NR+1)/2)]}'
}

# Latency score: 100 * (1 - p95/cap), clamped to [0, 100]
latency_score() {
  local p95="$1" cap="$2"
  awk "BEGIN{s=100*(1-$p95/$cap); if(s<0)s=0; if(s>100)s=100; printf \"%.4f\",s}"
}

# Start metrics output
cat > "$METRICS_FILE" <<'PROM_HEADER'
# HELP gateway_arena_score Composite arena score 0-100
# TYPE gateway_arena_score gauge
# HELP gateway_arena_availability Gateway availability 0-1
# TYPE gateway_arena_availability gauge
# HELP gateway_arena_p50_seconds P50 latency
# TYPE gateway_arena_p50_seconds gauge
# HELP gateway_arena_p95_seconds P95 latency
# TYPE gateway_arena_p95_seconds gauge
# HELP gateway_arena_p99_seconds P99 latency
# TYPE gateway_arena_p99_seconds gauge
# HELP gateway_arena_requests_total Total gateway arena requests by status
# TYPE gateway_arena_requests_total counter
# HELP gateway_arena_score_stddev Run-to-run standard deviation
# TYPE gateway_arena_score_stddev gauge
# HELP gateway_arena_runs Number of valid runs after discard
# TYPE gateway_arena_runs gauge
PROM_HEADER

for gw_idx in $(seq 0 $((GATEWAY_COUNT - 1))); do
  GW_NAME=$(echo "$GATEWAYS" | jq -r ".[$gw_idx].name")

  # Collect per-run composite scores (for stddev)
  RUN_SCORES=""
  VALID_RUNS=0

  # Collect per-scenario medians across valid runs
  declare -A SCENARIO_P95_VALUES
  declare -A SCENARIO_P50_VALUES
  declare -A SCENARIO_P25_VALUES
  declare -A SCENARIO_P75_VALUES
  declare -A SCENARIO_P99_VALUES
  declare -A SCENARIO_OK_TOTAL
  declare -A SCENARIO_FAIL_TOTAL

  for scenario in $SCENARIOS; do
    SCENARIO_P95_VALUES[$scenario]=""
    SCENARIO_P50_VALUES[$scenario]=""
    SCENARIO_P25_VALUES[$scenario]=""
    SCENARIO_P75_VALUES[$scenario]=""
    SCENARIO_P99_VALUES[$scenario]=""
    SCENARIO_OK_TOTAL[$scenario]=0
    SCENARIO_FAIL_TOTAL[$scenario]=0
  done

  for run in $(seq 1 "$RUNS"); do
    # Skip first N runs (JVM/cold-start warm-up)
    if [ "$run" -le "$DISCARD_FIRST" ]; then
      continue
    fi

    VALID_RUNS=$((VALID_RUNS + 1))

    # Collect per-scenario P95 for this run
    for scenario in $SCENARIOS; do
      JSON_FILE="$WORK_DIR/$GW_NAME/run-$run/${scenario}.json"
      p95=$(extract_pct "$JSON_FILE" "p(95)")
      p50=$(extract_pct "$JSON_FILE" "p(50)")
      p25=$(extract_pct "$JSON_FILE" "p(25)")
      p75=$(extract_pct "$JSON_FILE" "p(75)")
      p99=$(extract_pct "$JSON_FILE" "p(99)")
      ok=$(extract_checks "$JSON_FILE" "passes")
      fail=$(extract_checks "$JSON_FILE" "fails")

      SCENARIO_P95_VALUES[$scenario]="${SCENARIO_P95_VALUES[$scenario]}${p95}"$'\n'
      SCENARIO_P50_VALUES[$scenario]="${SCENARIO_P50_VALUES[$scenario]}${p50}"$'\n'
      SCENARIO_P25_VALUES[$scenario]="${SCENARIO_P25_VALUES[$scenario]}${p25}"$'\n'
      SCENARIO_P75_VALUES[$scenario]="${SCENARIO_P75_VALUES[$scenario]}${p75}"$'\n'
      SCENARIO_P99_VALUES[$scenario]="${SCENARIO_P99_VALUES[$scenario]}${p99}"$'\n'
      SCENARIO_OK_TOTAL[$scenario]=$(( ${SCENARIO_OK_TOTAL[$scenario]} + ok ))
      SCENARIO_FAIL_TOTAL[$scenario]=$(( ${SCENARIO_FAIL_TOTAL[$scenario]} + fail ))
    done
  done

  # Compute median P95/P50/P25/P75/P99 per scenario
  declare -A MED_P95 MED_P50 MED_P25 MED_P75 MED_P99

  for scenario in $SCENARIOS; do
    MED_P95[$scenario]=$(echo -e "${SCENARIO_P95_VALUES[$scenario]}" | grep -v '^$' | median)
    MED_P50[$scenario]=$(echo -e "${SCENARIO_P50_VALUES[$scenario]}" | grep -v '^$' | median)
    MED_P25[$scenario]=$(echo -e "${SCENARIO_P25_VALUES[$scenario]}" | grep -v '^$' | median)
    MED_P75[$scenario]=$(echo -e "${SCENARIO_P75_VALUES[$scenario]}" | grep -v '^$' | median)
    MED_P99[$scenario]=$(echo -e "${SCENARIO_P99_VALUES[$scenario]}" | grep -v '^$' | median)

    # Log per-scenario stats
    p50_ms=$(awk "BEGIN{printf \"%.2f\", ${MED_P50[$scenario]}*1000}")
    p95_ms=$(awk "BEGIN{printf \"%.2f\", ${MED_P95[$scenario]}*1000}")
    p99_ms=$(awk "BEGIN{printf \"%.2f\", ${MED_P99[$scenario]}*1000}")
    ok=${SCENARIO_OK_TOTAL[$scenario]}
    fail=${SCENARIO_FAIL_TOTAL[$scenario]}
    log_json "{\"gateway\":\"$GW_NAME\",\"scenario\":\"$scenario\",\"ok\":$ok,\"fail\":$fail,\"p50_ms\":$p50_ms,\"p95_ms\":$p95_ms,\"p99_ms\":$p99_ms}"

    # Write percentile gauges
    echo "gateway_arena_p50_seconds{gateway=\"$GW_NAME\",scenario=\"$scenario\"} ${MED_P50[$scenario]}" >> "$METRICS_FILE"
    echo "gateway_arena_p95_seconds{gateway=\"$GW_NAME\",scenario=\"$scenario\"} ${MED_P95[$scenario]}" >> "$METRICS_FILE"
    echo "gateway_arena_p99_seconds{gateway=\"$GW_NAME\",scenario=\"$scenario\"} ${MED_P99[$scenario]}" >> "$METRICS_FILE"

    # Write request counts
    echo "gateway_arena_requests_total{gateway=\"$GW_NAME\",scenario=\"$scenario\",status=\"200\"} $ok" >> "$METRICS_FILE"
    if [ "$fail" -gt 0 ]; then
      echo "gateway_arena_requests_total{gateway=\"$GW_NAME\",scenario=\"$scenario\",status=\"error\"} $fail" >> "$METRICS_FILE"
    fi
  done

  # ---------------------------------------------------------------------------
  # Composite score (same formula as Python version)
  # ---------------------------------------------------------------------------
  BASE_SCORE=$(latency_score "${MED_P95[sequential]}" "$CAP_BASE")
  BURST50_SCORE=$(latency_score "${MED_P95[burst_50]}" "$CAP_BURST50")
  BURST100_SCORE=$(latency_score "${MED_P95[burst_100]}" "$CAP_BURST100")

  # Availability + Error rate
  TOTAL_OK=0
  TOTAL_REQUESTS=0
  for scenario in $SCENARIOS; do
    TOTAL_OK=$(( TOTAL_OK + ${SCENARIO_OK_TOTAL[$scenario]} ))
    TOTAL_REQUESTS=$(( TOTAL_REQUESTS + ${SCENARIO_OK_TOTAL[$scenario]} + ${SCENARIO_FAIL_TOTAL[$scenario]} ))
  done

  if [ "$TOTAL_REQUESTS" -gt 0 ]; then
    AVAIL_SCORE=$(awk "BEGIN{printf \"%.4f\", 100*$TOTAL_OK/$TOTAL_REQUESTS}")
    ERROR_SCORE=$(awk "BEGIN{printf \"%.4f\", 100*$TOTAL_OK/$TOTAL_REQUESTS}")
  else
    AVAIL_SCORE="50.0000"
    ERROR_SCORE="50.0000"
  fi

  # Consistency (IQR-based CV on sustained latencies)
  SUSTAINED_P25="${MED_P25[sustained]}"
  SUSTAINED_P50="${MED_P50[sustained]}"
  SUSTAINED_P75="${MED_P75[sustained]}"
  CONSIST_SCORE=$(awk "BEGIN{
    p25=$SUSTAINED_P25; p50=$SUSTAINED_P50; p75=$SUSTAINED_P75;
    if(p50>0) {iqr_cv=(p75-p25)/p50; s=100*(1-iqr_cv)} else {s=100};
    if(s<0)s=0; if(s>100)s=100; printf \"%.4f\",s
  }")

  # Weighted composite
  SCORE=$(awk "BEGIN{
    s=$W_BASE*$BASE_SCORE + $W_BURST50*$BURST50_SCORE + $W_BURST100*$BURST100_SCORE + $W_AVAIL*$AVAIL_SCORE + $W_ERROR*$ERROR_SCORE + $W_CONSIST*$CONSIST_SCORE;
    if(s<0)s=0; if(s>100)s=100; printf \"%.2f\",s
  }")

  # Compute per-run scores for stddev
  for run in $(seq 1 "$RUNS"); do
    if [ "$run" -le "$DISCARD_FIRST" ]; then
      continue
    fi
    run_seq_p95=$(extract_pct "$WORK_DIR/$GW_NAME/run-$run/sequential.json" "p(95)")
    run_b50_p95=$(extract_pct "$WORK_DIR/$GW_NAME/run-$run/burst_50.json" "p(95)")
    run_b100_p95=$(extract_pct "$WORK_DIR/$GW_NAME/run-$run/burst_100.json" "p(95)")
    run_bs=$(latency_score "$run_seq_p95" "$CAP_BASE")
    run_b5=$(latency_score "$run_b50_p95" "$CAP_BURST50")
    run_b1=$(latency_score "$run_b100_p95" "$CAP_BURST100")
    run_score=$(awk "BEGIN{
      s=$W_BASE*$run_bs + $W_BURST50*$run_b5 + $W_BURST100*$run_b1 + $W_AVAIL*$AVAIL_SCORE + $W_ERROR*$ERROR_SCORE + $W_CONSIST*$CONSIST_SCORE;
      if(s<0)s=0; if(s>100)s=100; printf \"%.4f\",s
    }")
    RUN_SCORES="${RUN_SCORES}${run_score}"$'\n'
  done

  # Stddev of run scores
  STDDEV=$(echo -e "$RUN_SCORES" | grep -v '^$' | awk '{
    sum+=$1; sumsq+=$1*$1; n++
  } END{
    if(n>1){mean=sum/n; var=(sumsq-n*mean*mean)/(n-1); if(var<0)var=0; printf "%.4f",sqrt(var)}
    else{printf "0.0000"}
  }')

  # Health availability
  HEALTH_OK=${SCENARIO_OK_TOTAL[health]}
  HEALTH_TOTAL=$(( ${SCENARIO_OK_TOTAL[health]} + ${SCENARIO_FAIL_TOTAL[health]} ))
  if [ "$HEALTH_TOTAL" -gt 0 ]; then
    HEALTH_AVAIL=$(awk "BEGIN{printf \"%.4f\", $HEALTH_OK/$HEALTH_TOTAL}")
  else
    HEALTH_AVAIL="0.0000"
  fi

  # Write composite metrics
  echo "gateway_arena_score{gateway=\"$GW_NAME\"} $SCORE" >> "$METRICS_FILE"
  echo "gateway_arena_availability{gateway=\"$GW_NAME\"} $HEALTH_AVAIL" >> "$METRICS_FILE"
  echo "gateway_arena_score_stddev{gateway=\"$GW_NAME\"} $STDDEV" >> "$METRICS_FILE"
  echo "gateway_arena_runs{gateway=\"$GW_NAME\"} $VALID_RUNS" >> "$METRICS_FILE"

  LEADERBOARD=$(echo "$LEADERBOARD" | jq ". + [{\"gateway\":\"$GW_NAME\",\"score\":$SCORE,\"availability\":$HEALTH_AVAIL,\"stddev\":$STDDEV}]")
  log_json "\"Gateway $GW_NAME: score=$SCORE, availability=$HEALTH_AVAIL, stddev=$STDDEV\""

  # Clean up associative arrays for next gateway
  unset MED_P95 MED_P50 MED_P25 MED_P75 MED_P99
  unset SCENARIO_P95_VALUES SCENARIO_P50_VALUES SCENARIO_P25_VALUES SCENARIO_P75_VALUES SCENARIO_P99_VALUES
  unset SCENARIO_OK_TOTAL SCENARIO_FAIL_TOTAL
done

# ---------------------------------------------------------------------------
# Push to Pushgateway
# ---------------------------------------------------------------------------
PUSH_URL="${PUSHGATEWAY_URL}/metrics/job/gateway_arena"
HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" -X PUT --data-binary @"$METRICS_FILE" \
  -H "Content-Type: text/plain" "$PUSH_URL" 2>/dev/null || echo "000")

if [ "$HTTP_CODE" -lt 300 ] && [ "$HTTP_CODE" != "000" ]; then
  METRIC_LINES=$(wc -l < "$METRICS_FILE" | tr -d ' ')
  log_json "\"Pushed $METRIC_LINES metric lines to $PUSH_URL\""
else
  log_json "\"WARNING: Pushgateway returned HTTP $HTTP_CODE\""
fi

# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------
SORTED_LEADERBOARD=$(echo "$LEADERBOARD" | jq 'sort_by(-.score)')
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
log_json "{\"event\":\"leaderboard\",\"ranking\":$SORTED_LEADERBOARD,\"timestamp\":\"$TS\"}"

# Cleanup
rm -rf "$WORK_DIR"

log_json "\"Arena k6 orchestrator finished\""
