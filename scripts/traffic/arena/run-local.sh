#!/usr/bin/env bash
# run-local.sh — Quick local benchmark for a single gateway
#
# Prerequisites: k6 (v0.54+), Docker
#
# Usage:
#   ./scripts/traffic/arena/run-local.sh http://localhost:8080
#   ./scripts/traffic/arena/run-local.sh http://localhost:8080 /health /echo/get
#
# Arguments:
#   $1 — Gateway base URL (required)
#   $2 — Health endpoint path (default: /health)
#   $3 — Proxy endpoint path (default: /echo/get)
#
# This script:
#   1. Starts a local echo backend (nginx, port 8888)
#   2. Runs 3 key scenarios: health, sequential, burst_50
#   3. Prints summary results
#   4. Stops the echo backend

set -euo pipefail

GATEWAY_URL="${1:?Usage: run-local.sh <gateway-url> [health-path] [proxy-path]}"
HEALTH_PATH="${2:-/health}"
PROXY_PATH="${3:-/echo/get}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ECHO_CONTAINER="arena-echo-local"
ECHO_PORT=8888
RESULTS_DIR=$(mktemp -d)

cleanup() {
    echo ""
    echo "=== Cleanup ==="
    docker rm -f "$ECHO_CONTAINER" 2>/dev/null || true
    rm -rf "$RESULTS_DIR"
}
trap cleanup EXIT

# --- 1. Start echo backend ---
echo "=== Starting echo backend on port $ECHO_PORT ==="
docker rm -f "$ECHO_CONTAINER" 2>/dev/null || true
docker run -d --name "$ECHO_CONTAINER" -p "$ECHO_PORT:8888" \
    nginx:alpine \
    sh -c 'mkdir -p /etc/nginx/conf.d && cat > /etc/nginx/conf.d/default.conf << "CONF"
server {
    listen 8888;
    location / {
        default_type application/json;
        return 200 "{\"status\":\"ok\",\"source\":\"echo-local\"}";
    }
}
CONF
nginx -g "daemon off;"' >/dev/null

# Wait for echo to be ready
for i in $(seq 1 10); do
    if curl -sf "http://localhost:$ECHO_PORT/" >/dev/null 2>&1; then
        echo "Echo backend ready."
        break
    fi
    if [ "$i" -eq 10 ]; then
        echo "ERROR: Echo backend did not start in time."
        exit 1
    fi
    sleep 0.5
done

# --- 2. Verify gateway is reachable ---
echo ""
echo "=== Checking gateway at ${GATEWAY_URL}${HEALTH_PATH} ==="
if ! curl -sf "${GATEWAY_URL}${HEALTH_PATH}" >/dev/null 2>&1; then
    echo "WARNING: Gateway health check failed. Continuing anyway..."
else
    echo "Gateway is reachable."
fi

# --- 3. Run scenarios ---
HEALTH_URL="${GATEWAY_URL}${HEALTH_PATH}"
TARGET_URL="${GATEWAY_URL}${PROXY_PATH}"

SCENARIOS=("health" "sequential" "burst_50")

echo ""
echo "=== Running benchmark ==="
echo "  Gateway: $GATEWAY_URL"
echo "  Health:  $HEALTH_URL"
echo "  Target:  $TARGET_URL"
echo "  Scenarios: ${SCENARIOS[*]}"
echo ""

for scenario in "${SCENARIOS[@]}"; do
    echo "--- Scenario: $scenario ---"
    k6 run \
        --env "TARGET_URL=$TARGET_URL" \
        --env "HEALTH_URL=$HEALTH_URL" \
        --env "SCENARIO=$scenario" \
        --env "TIMEOUT=5s" \
        --summary-export "$RESULTS_DIR/${scenario}.json" \
        --quiet \
        "$SCRIPT_DIR/benchmark.js" 2>&1 | tail -5
    echo ""
done

# --- 4. Print summary ---
echo "=== Results Summary ==="
echo ""

for scenario in "${SCENARIOS[@]}"; do
    result_file="$RESULTS_DIR/${scenario}.json"
    if [ -f "$result_file" ]; then
        # Extract key metrics from k6 JSON summary
        avg=$(python3 -c "
import json, sys
try:
    d = json.load(open('$result_file'))
    m = d.get('metrics', {})
    dur = m.get('http_req_duration', {}).get('values', {})
    reqs = m.get('http_reqs', {}).get('values', {}).get('count', 0)
    fails = m.get('http_req_failed', {}).get('values', {}).get('passes', 0)
    p95 = dur.get('p(95)', 0)
    avg = dur.get('avg', 0)
    print(f'  Requests: {int(reqs):>6}  |  Avg: {avg:>8.1f}ms  |  P95: {p95:>8.1f}ms  |  Errors: {int(fails)}')
except Exception as e:
    print(f'  (parse error: {e})')
" 2>&1)
        echo "$scenario:"
        echo "$avg"
    else
        echo "$scenario: (no results)"
    fi
done

echo ""
echo "Raw JSON results saved to: $RESULTS_DIR/"
echo "For full scoring, use: python3 $SCRIPT_DIR/run-arena.py"
