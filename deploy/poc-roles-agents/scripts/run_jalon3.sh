#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

export STOA_POC_BOOTSTRAP_SECRET="${STOA_POC_BOOTSTRAP_SECRET:-poc-parent-boot-$(openssl rand -hex 12)}"
export STOA_POC_UPSTREAM_API_KEY="${STOA_POC_UPSTREAM_API_KEY:-poc-backend-key-$(openssl rand -hex 12)}"
export STOA_POC_CHAIN_BUDGET=5
export STOA_POC_CALLER_BUDGET=8
export STOA_POC_MAX_REVOKED_CHAINS=100

cleanup() {
  docker compose down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "=== [1/4] Generating ephemeral signed Jalon 3 fixtures ==="
python3 ./scripts/gen_fixtures.py ./.runtime

echo "=== [2/4] Starting isolated 4-container Docker Compose stack (chain_budget=5, caller_budget=8) ==="
docker compose up -d --build --wait

MOCK_IP="$(docker compose exec -T upstream-mock python3 -c 'import socket; print(socket.gethostbyname(socket.gethostname()))' | tr -d '\r\n')"
echo "upstream-mock isolated IP on upstream-net: ${MOCK_IP}"

echo "=== [3/4] Running tool, budget, revocation, and restart checks ==="
python3 -B ./jalon3.py host "$MOCK_IP"

echo "=== [4/4] Verifying exact upstream-mock counters ==="
STATS="$(docker compose exec -T upstream-mock cat /tmp/upstream_stats.json)"
echo "$STATS"
echo "$STATS" | python3 -c '
import json, sys
s = json.load(sys.stdin)
assert s["upstream_calls"] == 11, f"expected exact 11 /payments calls (1 subcall + 1 fallback + 1 child + 3 chainB + 5 chainC), got {s}"
assert s["valid_api_key_calls"] == 11, f"expected 11 valid API key calls, got {s}"
assert s["fail_calls"] == 2, f"expected 2 /fail calls, got {s}"
assert s["forbidden_calls"] == 0, f"payments_hidden (/forbidden) was reached: {s}"
assert s["caller_auth_headers_seen"] == 0, f"caller Authorization header leaked upstream: {s}"
assert s["redirect_target_calls"] == 0, f"redirect target reached: {s}"
assert s["oauth2_calls"] == 0, f"unexpected oauth2 calls: {s}"
print("PASS: upstream-mock saw exact 11 backend-key-authenticated /payments calls, 2 /fail calls, 0 /forbidden calls, 0 caller tokens")
'

echo "=== JALON 3 DOCKER COMPOSE VERIFICATION PASSED ==="
