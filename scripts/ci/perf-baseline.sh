#!/usr/bin/env bash
# =============================================================================
# Performance Baseline Generator — stoa-gateway
# =============================================================================
# Runs a minimal k6 benchmark (health + sequential, 3 runs) and saves the
# results as the baseline for the perf-gate CI check.
#
# Usage:
#   scripts/ci/perf-baseline.sh [--output FILE]
#
# Prerequisites:
#   - k6 installed
#   - stoa-gateway running on GATEWAY_URL (default: http://localhost:8080)
# =============================================================================
set -euo pipefail

OUTPUT="${1:-.perf-baseline/gateway.json}"
GATEWAY_URL="${GATEWAY_URL:-http://localhost:8080}"
K6_SCRIPT="${K6_SCRIPT:-scripts/traffic/arena/benchmark.js}"
RUNS="${RUNS:-3}"

log() { echo "[perf-baseline] $*"; }

# ---------------------------------------------------------------------------
# Verify gateway is reachable
# ---------------------------------------------------------------------------
log "Checking gateway at $GATEWAY_URL/health..."
if ! curl -sf --max-time 5 "$GATEWAY_URL/health" > /dev/null 2>&1; then
  log "ERROR: Gateway not reachable at $GATEWAY_URL/health"
  exit 1
fi

# ---------------------------------------------------------------------------
# Run benchmark
# ---------------------------------------------------------------------------
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

log "Running $RUNS benchmark runs (health + sequential scenarios)..."

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
  log "Run $run/$RUNS complete"
done

# ---------------------------------------------------------------------------
# Aggregate and save baseline
# ---------------------------------------------------------------------------
log "Computing baseline metrics (median of $RUNS runs)..."

mkdir -p "$(dirname "$OUTPUT")"

python3 -c "
import json, os, sys
from datetime import date

work_dir = '$WORK_DIR'
runs = int('$RUNS')

health_p50s, health_p95s = [], []
seq_p50s, seq_p95s = [], []
error_counts, total_counts = 0, 0
rps_values = []

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

        iters = metrics.get('iterations', {})
        iter_vals = iters.get('values', {})
        rate = iter_vals.get('rate', 0)

        if scenario == 'health':
            health_p50s.append(p50)
            health_p95s.append(p95)
        else:
            seq_p50s.append(p50)
            seq_p95s.append(p95)
            if rate > 0:
                rps_values.append(rate)

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
rps = median(rps_values) if rps_values else 0

result = {
    'version': '1.0',
    'created': str(date.today()),
    'gateway_version': '0.1.0',
    'metrics': {
        'health_p50_ms': round(median(health_p50s), 2),
        'health_p95_ms': round(median(health_p95s), 2),
        'sequential_p50_ms': round(median(seq_p50s), 2),
        'sequential_p95_ms': round(median(seq_p95s), 2),
        'error_rate': round(error_rate, 2),
        'rps_sustained': round(rps, 1)
    }
}

with open('$OUTPUT', 'w') as f:
    json.dump(result, f, indent=2)
    f.write('\n')

print(json.dumps(result, indent=2))
"

log "Baseline saved to $OUTPUT"
log "Commit this file to track performance over time."
