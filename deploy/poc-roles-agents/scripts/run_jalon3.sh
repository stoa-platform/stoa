#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

export STOA_POC_BOOTSTRAP_SECRET="${STOA_POC_BOOTSTRAP_SECRET:-poc-parent-boot-$(openssl rand -hex 12)}"
export STOA_POC_UPSTREAM_API_KEY="${STOA_POC_UPSTREAM_API_KEY:-poc-vault-key-$(openssl rand -hex 12)}"
export STOA_POC_CHAIN_BUDGET=5
export STOA_POC_CALLER_BUDGET=8
export STOA_POC_MAX_REVOKED_CHAINS=100

cleanup() {
  docker compose down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "=== [1/8] Generating ephemeral signed Jalon 3 fixtures ==="
python3 ./scripts/gen_fixtures.py ./.runtime

echo "=== [2/8] Starting isolated 4-container Docker Compose stack (chain_budget=5, caller_budget=8) ==="
docker compose up -d --build --wait

MOCK_IP="$(docker compose exec -T upstream-mock python3 -c 'import socket; print(socket.gethostbyname(socket.gethostname()))' | tr -d '\r\n')"
echo "upstream-mock isolated IP on upstream-net: ${MOCK_IP}"

echo "=== [3/8] Generating child DPoP keypair inside agent-child ==="
CHILD_JWK="$(docker compose exec -T agent-child python3 /app/agent_harness.py child-init-key | tr -d '\r\n')"

echo "=== [4/8] Running agent-parent phase 1 (filtered tools/list, poc/subcalls, fallback, delegation) ==="
PARENT_OUT="$(docker compose exec -T agent-parent python3 /app/agent_harness.py jalon3-parent-phase1 "${MOCK_IP}" "${CHILD_JWK}")"
echo "$PARENT_OUT" | grep -Ev "^CHILD_TOKEN_DELEGATED="
CHILD_TOK="$(echo "$PARENT_OUT" | sed -n 's/^CHILD_TOKEN_DELEGATED=//p')"

echo "=== [5/8] Running agent-child delegated call on chain A ==="
docker compose exec -T agent-child python3 /app/agent_harness.py jalon3-child-use "${MOCK_IP}" "${CHILD_TOK}"

echo "=== [6/8] Revoking chain A + running 16-way concurrent HTTP budget races (caller cap & chain cap) ==="
docker compose exec -T agent-parent python3 /app/agent_harness.py jalon3-parent-revoke-and-race
docker compose exec -T agent-child python3 /app/agent_harness.py jalon3-child-post-revoke

echo "=== [7/8] Restarting stoa-gateway and verifying pre-restart token invalidation ==="
docker compose restart stoa-gateway
for _ in $(seq 1 30); do
  if docker compose exec -T stoa-gateway curl -sf http://127.0.0.1:8080/ready >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker compose exec -T agent-parent python3 /app/agent_harness.py jalon3-post-restart

echo "=== [8/8] Verifying exact upstream-mock counters ==="
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
print("PASS: upstream-mock saw exact 11 vault-authenticated /payments calls, 2 /fail calls, 0 /forbidden calls, 0 caller tokens")
'

echo "=== JALON 3 DOCKER COMPOSE VERIFICATION PASSED ==="
