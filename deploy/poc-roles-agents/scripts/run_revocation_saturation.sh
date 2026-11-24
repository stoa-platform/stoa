#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

bootstrap_rand="$(openssl rand -hex 24)"
upstream_rand="$(openssl rand -hex 24)"
STOA_POC_BOOTSTRAP_SECRET="${bootstrap_rand}"
STOA_POC_UPSTREAM_API_KEY="${upstream_rand}"
export STOA_POC_BOOTSTRAP_SECRET STOA_POC_UPSTREAM_API_KEY
export STOA_POC_MAX_REVOKED_CHAINS=2

cleanup() {
  docker compose down -v --remove-orphans >/dev/null 2>&1 || true
  rm -rf ./.runtime
}
trap cleanup EXIT

echo "=== [1/4] Generating ephemeral signed revocation saturation fixtures ==="
python3 ./scripts/gen_fixtures.py ./.runtime

echo "=== [2/4] Starting isolated 4-container Docker Compose stack (max_revoked_chains=2) ==="
docker compose up -d --build --wait

MOCK_IP="$(docker compose exec -T upstream-mock python3 -c 'import socket; print(socket.gethostbyname(socket.gethostname()))' | tr -d '\r\n')"
echo "upstream-mock isolated IP on upstream-net: ${MOCK_IP}"

echo "=== [3/4] Running revocation table saturation fail-closed checks ==="
python3 -B ./revocation_saturation.py host "$MOCK_IP"

echo "=== [4/4] Verifying exact upstream-mock counters ==="
STATS="$(docker compose exec -T upstream-mock cat /tmp/upstream_stats.json)"
echo "$STATS"
echo "$STATS" | python3 -c '
import json, sys
s = json.load(sys.stdin)
assert s["upstream_calls"] == 1, f"expected exact 1 pre-saturation /payments call and 0 refused calls, got {s}"
assert s["valid_api_key_calls"] == 1, f"expected 1 valid API key call, got {s}"
assert s["fail_calls"] == 0, f"unexpected /fail calls: {s}"
assert s["forbidden_calls"] == 0, f"unexpected /forbidden calls: {s}"
assert s["caller_auth_headers_seen"] == 0, f"caller Authorization header leaked upstream: {s}"
assert s["redirect_target_calls"] == 0, f"redirect target reached: {s}"
assert s["oauth2_calls"] == 0, f"unexpected oauth2 calls: {s}"
print("PASS: upstream-mock saw exact 1 pre-saturation call, 0 calls for refused requests, and 0 caller tokens")
'

echo "=== REVOCATION SATURATION DOCKER COMPOSE VERIFICATION PASSED ==="
