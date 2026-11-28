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
  rm -rf ./.runtime
}
trap cleanup EXIT

echo "=== [1/5] Generating ephemeral signed Jalon 2 fixtures ==="
python3 ./scripts/gen_fixtures.py ./.runtime --refusal-role-v2-out ./.runtime/acme.refusal.v2.jws

echo "=== [2/5] Starting isolated 4-container Docker Compose stack ==="
docker compose up -d --build --wait

MOCK_IP="$(docker compose exec -T upstream-mock python3 -c 'import socket; print(socket.gethostbyname(socket.gethostname()))' | tr -d '\r\n')"
echo "upstream-mock isolated IP on upstream-net: ${MOCK_IP}"

echo "=== [3/5] Verifying persisted 0600 anti-rollback floor inside stoa-gateway ==="
FLOOR_MODE="$(docker compose exec -T stoa-gateway stat -c '%a' /tmp/stoa-poc-floors/acme.floor.json | tr -d '\r\n')"
if [[ "${FLOOR_MODE}" != "600" ]]; then
  echo "FAIL: expected floor permissions 600, got ${FLOOR_MODE}" >&2
  exit 1
fi
echo "PASS: /tmp/stoa-poc-floors/acme.floor.json persisted with mode ${FLOOR_MODE}"

echo "=== [4/5] Running agent-parent and agent-child vertical proof checks ==="
python3 -B ./jalon12.py host jalon2 "${MOCK_IP}"

echo "=== [5/5] Verifying upstream-mock counters ==="
STATS="$(docker compose exec -T upstream-mock cat /tmp/upstream_stats.json)"
echo "$STATS"
echo "$STATS" | python3 -c '
import json, sys
s = json.load(sys.stdin)
assert s["upstream_calls"] == 2, f"expected exactly 2 authorized /payments calls (1 parent + 1 child), got {s}"
assert s["valid_api_key_calls"] == 2, f"expected 2 valid API key calls, got {s}"
assert s["forbidden_calls"] == 0, f"payments_hidden (/forbidden) was reached: {s}"
assert s["caller_auth_headers_seen"] == 0, f"caller Authorization header leaked upstream: {s}"
assert s["redirect_target_calls"] == 0, f"3xx redirect was followed: {s}"
assert s["oauth2_calls"] == 0, f"unexpected oauth2 calls: {s}"
print("PASS: upstream-mock saw exactly 2 backend-key-authenticated calls (parent + child), 0 caller tokens, 0 redirects followed")
'

echo "=== JALON 2 DOCKER COMPOSE VERTICAL PROOF PASSED ==="
