#!/usr/bin/env bash
# =============================================================================
# Tests for perf-gate.sh
# =============================================================================
# Validates the perf gate logic using synthetic baseline and current data.
# No k6 or gateway needed — tests the comparison logic only.
#
# Usage: scripts/ci/test-perf-gate.sh
# Exit: 0 = all tests pass, 1 = test failure
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PERF_GATE="$SCRIPT_DIR/perf-gate.sh"
PASS=0
FAIL=0
TEST_DIR=$(mktemp -d)
trap 'rm -rf "$TEST_DIR"' EXIT

log() { echo "[test] $*"; }

assert_exit() {
  local test_name="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    log "PASS: $test_name"
    PASS=$((PASS + 1))
  else
    log "FAIL: $test_name (expected exit $expected, got $actual)"
    FAIL=$((FAIL + 1))
  fi
}

# ---------------------------------------------------------------------------
# Test 1: Passing result (no regression)
# ---------------------------------------------------------------------------
log "--- Test 1: No regression → exit 0 ---"

cat > "$TEST_DIR/baseline.json" <<'EOF'
{
  "version": "1.0",
  "metrics": {
    "health_p50_ms": 2.0,
    "health_p95_ms": 5.0,
    "sequential_p50_ms": 10.0,
    "sequential_p95_ms": 25.0,
    "error_rate": 0.0
  }
}
EOF

cat > "$TEST_DIR/current-pass.json" <<'EOF'
{
  "version": "1.0",
  "metrics": {
    "health_p50_ms": 2.1,
    "health_p95_ms": 5.2,
    "sequential_p50_ms": 10.5,
    "sequential_p95_ms": 26.0,
    "error_rate": 0.0
  }
}
EOF

EXIT_CODE=0
"$PERF_GATE" "$TEST_DIR/baseline.json" "$TEST_DIR/current-pass.json" > /dev/null 2>&1 || EXIT_CODE=$?
assert_exit "no regression" 0 "$EXIT_CODE"

# ---------------------------------------------------------------------------
# Test 2: p95 regression → exit 1
# ---------------------------------------------------------------------------
log "--- Test 2: p95 regression → exit 1 ---"

cat > "$TEST_DIR/current-regress.json" <<'EOF'
{
  "version": "1.0",
  "metrics": {
    "health_p50_ms": 2.0,
    "health_p95_ms": 5.0,
    "sequential_p50_ms": 10.0,
    "sequential_p95_ms": 35.0,
    "error_rate": 0.0
  }
}
EOF

EXIT_CODE=0
"$PERF_GATE" "$TEST_DIR/baseline.json" "$TEST_DIR/current-regress.json" > /dev/null 2>&1 || EXIT_CODE=$?
assert_exit "p95 regression detected" 1 "$EXIT_CODE"

# ---------------------------------------------------------------------------
# Test 3: Error rate regression → exit 1
# ---------------------------------------------------------------------------
log "--- Test 3: Error rate regression → exit 1 ---"

cat > "$TEST_DIR/current-errors.json" <<'EOF'
{
  "version": "1.0",
  "metrics": {
    "health_p50_ms": 2.0,
    "health_p95_ms": 5.0,
    "sequential_p50_ms": 10.0,
    "sequential_p95_ms": 25.0,
    "error_rate": 2.5
  }
}
EOF

EXIT_CODE=0
"$PERF_GATE" "$TEST_DIR/baseline.json" "$TEST_DIR/current-errors.json" > /dev/null 2>&1 || EXIT_CODE=$?
assert_exit "error rate regression detected" 1 "$EXIT_CODE"

# ---------------------------------------------------------------------------
# Test 4: Missing baseline → exit 0 (skip, non-blocking)
# ---------------------------------------------------------------------------
log "--- Test 4: Missing baseline → exit 0 ---"

EXIT_CODE=0
"$PERF_GATE" "$TEST_DIR/nonexistent.json" "$TEST_DIR/current-pass.json" > /dev/null 2>&1 || EXIT_CODE=$?
assert_exit "missing baseline skips gracefully" 0 "$EXIT_CODE"

# ---------------------------------------------------------------------------
# Test 5: p50 warning (within threshold, no fail)
# ---------------------------------------------------------------------------
log "--- Test 5: p50 warning but under p95 threshold → exit 0 ---"

cat > "$TEST_DIR/current-warn.json" <<'EOF'
{
  "version": "1.0",
  "metrics": {
    "health_p50_ms": 2.4,
    "health_p95_ms": 5.5,
    "sequential_p50_ms": 11.8,
    "sequential_p95_ms": 29.0,
    "error_rate": 0.0
  }
}
EOF

EXIT_CODE=0
"$PERF_GATE" "$TEST_DIR/baseline.json" "$TEST_DIR/current-warn.json" > /dev/null 2>&1 || EXIT_CODE=$?
assert_exit "p50 warn but p95 within threshold" 0 "$EXIT_CODE"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "================================"
echo "Results: $PASS passed, $FAIL failed"
echo "================================"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
