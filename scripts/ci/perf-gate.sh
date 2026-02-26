#!/usr/bin/env bash
# =============================================================================
# Performance Regression Gate — stoa-gateway
# =============================================================================
# Compares current k6 benchmark results against a stored baseline.
# Regression thresholds:
#   - p95 > 20% worse = FAIL
#   - p50 > 15% worse = WARN
#   - error_rate > 1%  = FAIL
#
# Usage:
#   scripts/ci/perf-gate.sh [--baseline FILE] [--current FILE]
#
# Exit codes:
#   0 = PASS (no regressions)
#   1 = FAIL (regression detected)
#
# If baseline is missing, the gate passes with a warning (non-blocking).
# =============================================================================
set -euo pipefail

BASELINE_FILE="${1:-.perf-baseline/gateway.json}"
CURRENT_FILE="${2:-/tmp/perf-gate-current.json}"
GATEWAY_URL="${GATEWAY_URL:-http://localhost:8080}"
K6_SCRIPT="${K6_SCRIPT:-scripts/traffic/arena/benchmark.js}"
RUNS="${RUNS:-3}"

# Thresholds (percentage increase that triggers)
P95_FAIL_THRESHOLD=20
P50_WARN_THRESHOLD=15
ERROR_RATE_FAIL=1.0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log() { echo "[perf-gate] $*"; }

pct_change() {
  local baseline="$1" current="$2"
  if [ "$baseline" = "0" ] || [ -z "$baseline" ]; then
    echo "0"
    return
  fi
  echo "$current $baseline" | awk '{printf "%.1f", (($1 - $2) / $2) * 100}'
}

is_gt() {
  echo "$1 $2" | awk '{exit ($1 > $2) ? 0 : 1}'
}

# ---------------------------------------------------------------------------
# Check baseline exists
# ---------------------------------------------------------------------------
if [ ! -f "$BASELINE_FILE" ]; then
  log "WARNING: No baseline found at $BASELINE_FILE — skipping perf gate"
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    cat >> "$GITHUB_STEP_SUMMARY" <<'EOFMD'
## Performance Gate: SKIPPED

No baseline file found. Run `scripts/ci/perf-baseline.sh` to generate one.
EOFMD
  fi
  exit 0
fi

# ---------------------------------------------------------------------------
# Run benchmark if no current file provided or it does not exist
# ---------------------------------------------------------------------------
if [ ! -f "$CURRENT_FILE" ]; then
  log "Running k6 benchmark (health + sequential, $RUNS runs)..."

  WORK_DIR=$(mktemp -d)
  trap 'rm -rf "$WORK_DIR"' EXIT

  for run in $(seq 1 "$RUNS"); do
    for scenario in health sequential; do
      SUMMARY="$WORK_DIR/run-${run}-${scenario}.json"
      k6 run \
        --env SCENARIO="$scenario" \
        --env TARGET_URL="$GATEWAY_URL/health" \
        --env HEALTH_URL="$GATEWAY_URL/health" \
        --env TIMEOUT=5 \
        --env SUMMARY_FILE="$SUMMARY" \
        --quiet \
        "$K6_SCRIPT" 2>/dev/null || true
    done
  done

  # Aggregate results: compute median p50, p95, error rate
  # Extract metrics from k6 JSON summary format
  CURRENT_FILE=$(mktemp)
  python3 -c "
import json, glob, os, sys

work_dir = '$WORK_DIR'
runs = int('$RUNS')

health_p50s, health_p95s = [], []
seq_p50s, seq_p95s = [], []
error_counts, total_counts = 0, 0

for run in range(1, runs + 1):
    for scenario in ['health', 'sequential']:
        fpath = os.path.join(work_dir, f'run-{run}-{scenario}.json')
        if not os.path.exists(fpath):
            continue
        try:
            with open(fpath) as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        metrics = data.get('metrics', {})
        http_dur = metrics.get('http_req_duration', {})
        vals = http_dur.get('values', {})
        p50 = vals.get('p(50)', vals.get('med', 0))
        p95 = vals.get('p(95)', 0)

        checks = metrics.get('checks', {})
        check_vals = checks.get('values', {})
        passes = check_vals.get('passes', 0)
        fails = check_vals.get('fails', 0)

        if scenario == 'health':
            health_p50s.append(p50)
            health_p95s.append(p95)
        else:
            seq_p50s.append(p50)
            seq_p95s.append(p95)

        error_counts += fails
        total_counts += passes + fails

def median(lst):
    if not lst:
        return 0
    s = sorted(lst)
    n = len(s)
    if n % 2 == 0:
        return (s[n//2 - 1] + s[n//2]) / 2
    return s[n//2]

error_rate = (error_counts / total_counts * 100) if total_counts > 0 else 0

result = {
    'version': '1.0',
    'metrics': {
        'health_p50_ms': round(median(health_p50s), 2),
        'health_p95_ms': round(median(health_p95s), 2),
        'sequential_p50_ms': round(median(seq_p50s), 2),
        'sequential_p95_ms': round(median(seq_p95s), 2),
        'error_rate': round(error_rate, 2)
    }
}
json.dump(result, sys.stdout, indent=2)
print()
" > "$CURRENT_FILE"

  log "Benchmark complete. Results: $CURRENT_FILE"
fi

# ---------------------------------------------------------------------------
# Compare baseline vs current
# ---------------------------------------------------------------------------
log "Comparing baseline ($BASELINE_FILE) vs current ($CURRENT_FILE)..."

VERDICT="PASS"
DETAILS=""

compare_metric() {
  local name="$1" threshold="$2" level="$3"
  local baseline_val current_val pct

  baseline_val=$(jq -r ".metrics.${name} // 0" "$BASELINE_FILE")
  current_val=$(jq -r ".metrics.${name} // 0" "$CURRENT_FILE")
  pct=$(pct_change "$baseline_val" "$current_val")

  local status="ok"
  if is_gt "$pct" "$threshold"; then
    if [ "$level" = "FAIL" ]; then
      VERDICT="FAIL"
      status="REGRESSION"
    else
      status="WARNING"
    fi
  fi

  DETAILS="${DETAILS}| ${name} | ${baseline_val} | ${current_val} | ${pct}% | ${status} |\n"
}

# Compare latency metrics (higher = worse)
compare_metric "health_p50_ms"      "$P50_WARN_THRESHOLD" "WARN"
compare_metric "health_p95_ms"      "$P95_FAIL_THRESHOLD" "FAIL"
compare_metric "sequential_p50_ms"  "$P50_WARN_THRESHOLD" "WARN"
compare_metric "sequential_p95_ms"  "$P95_FAIL_THRESHOLD" "FAIL"

# Compare error rate separately
BASELINE_ERR=$(jq -r '.metrics.error_rate // 0' "$BASELINE_FILE")
CURRENT_ERR=$(jq -r '.metrics.error_rate // 0' "$CURRENT_FILE")
ERR_STATUS="ok"
if is_gt "$CURRENT_ERR" "$ERROR_RATE_FAIL"; then
  VERDICT="FAIL"
  ERR_STATUS="REGRESSION"
fi
DETAILS="${DETAILS}| error_rate | ${BASELINE_ERR}% | ${CURRENT_ERR}% | — | ${ERR_STATUS} |\n"

# ---------------------------------------------------------------------------
# Output results
# ---------------------------------------------------------------------------
ICON="pass"
[ "$VERDICT" = "FAIL" ] && ICON="fail"

SUMMARY=$(cat <<EOFMD
## Performance Gate: ${VERDICT}

| Metric | Baseline | Current | Change | Status |
|--------|----------|---------|--------|--------|
$(echo -e "$DETAILS")

**Thresholds**: p95 regression > ${P95_FAIL_THRESHOLD}% = FAIL, p50 regression > ${P50_WARN_THRESHOLD}% = WARN, error rate > ${ERROR_RATE_FAIL}% = FAIL
EOFMD
)

echo "$SUMMARY"

if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  echo "$SUMMARY" >> "$GITHUB_STEP_SUMMARY"
fi

if [ "$VERDICT" = "FAIL" ]; then
  log "REGRESSION DETECTED — gate FAILED"
  exit 1
else
  log "No regressions — gate PASSED"
  exit 0
fi
