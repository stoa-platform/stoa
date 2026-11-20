#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

bootstrap_rand="$(openssl rand -hex 24)"
upstream_rand="$(openssl rand -hex 24)"
STOA_POC_BOOTSTRAP_SECRET="${bootstrap_rand}"
STOA_POC_UPSTREAM_API_KEY="${upstream_rand}"
export STOA_POC_BOOTSTRAP_SECRET STOA_POC_UPSTREAM_API_KEY

cleanup() {
  docker compose down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "=== [1/5] Generating ephemeral signed Jalon 1 fixtures ==="
python3 ./scripts/gen_fixtures.py ./.runtime

echo "=== [2/5] Starting isolated 4-container Docker Compose stack ==="
docker compose up -d --build --wait

MOCK_IP="$(docker compose exec -T upstream-mock python3 -c 'import socket; print(socket.gethostbyname(socket.gethostname()))' | tr -d '\r\n')"
echo "upstream-mock isolated IP on upstream-net: ${MOCK_IP}"

echo "=== [3/5] Running agent-parent container checks ==="
PARENT_OUT="$(docker compose exec -T agent-parent python3 /app/agent_harness.py parent "${MOCK_IP}")"
echo "$PARENT_OUT" | grep -v "^PARENT_TOKEN_FOR_NEGATIVE_TEST="
PARENT_TOK="$(echo "$PARENT_OUT" | sed -n 's/^PARENT_TOKEN_FOR_NEGATIVE_TEST=//p')"

echo "=== [4/5] Running agent-child container checks ==="
docker compose exec -T agent-child python3 /app/agent_harness.py child "${MOCK_IP}" "${PARENT_TOK}"

echo "=== [5/5] Verifying upstream-mock counters ==="
STATS="$(docker compose exec -T upstream-mock cat /tmp/upstream_stats.json)"
echo "$STATS"
echo "$STATS" | python3 -c '
import json, sys
s = json.load(sys.stdin)
assert s["upstream_calls"] == 1, f"expected exactly 1 upstream call, got {s}"
assert s["valid_api_key_calls"] == 1, f"expected 1 valid API key call, got {s}"
assert s["caller_auth_headers_seen"] == 0, f"caller Authorization header leaked upstream: {s}"
assert s["oauth2_calls"] == 0, f"unexpected oauth2 calls: {s}"
print("PASS: upstream-mock saw exactly 1 authorized vault-authenticated call and 0 caller tokens")
'

echo "=== JALON 1 DOCKER COMPOSE VERIFICATION PASSED ==="
