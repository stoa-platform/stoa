#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

export COMPOSE_PROJECT_NAME="poc-roles-agents-jalon4-$$"
export STOA_POC_BOOTSTRAP_SECRET="$(openssl rand -hex 24)"
# This public fixture value is used solely to recognize mock requests.
export STOA_POC_UPSTREAM_API_KEY="jalon4-example-backend-marker"
export STOA_POC_EXPECTED_SKILL_CONTEXT="Every payment lookup uses a currency."
export STOA_POC_CHAIN_BUDGET=2
export STOA_POC_CALLER_BUDGET=3

runtime_root="$(mktemp -d /tmp/stoa-poc-jalon4.XXXXXXXX)"
runtime_root="$(cd "$runtime_root" && pwd -P)"
export STOA_POC_RUNTIME_DIR="$runtime_root/accepted"

cleanup() {
  docker compose down -v --remove-orphans >/dev/null 2>&1 || true
  rm -rf -- "$runtime_root"
}
trap cleanup EXIT

echo "=== [1/4] Building the four-container stack with the signed skill ==="
python3 ./scripts/gen_fixtures.py "$runtime_root" --jalon4-suite
docker compose up -d --build --wait

echo "=== [2/4] Checking access projection over isolated MCP ==="
mock_ip="$(docker compose exec -T upstream-mock python3 -c 'import socket; print(socket.gethostbyname(socket.gethostname()))')"
python3 -B ./jalon4.py host "$mock_ip"

check_refused() {
  local variant="$1" reason="$2" gateway_id state logs
  export STOA_POC_RUNTIME_DIR="$runtime_root/$variant"
  docker compose up -d --no-deps --force-recreate stoa-gateway
  gateway_id="$(docker compose ps --all -q stoa-gateway)"
  for _ in $(seq 1 20); do
    state="$(docker inspect -f '{{.State.Status}}:{{.State.ExitCode}}' "$gateway_id")"
    case "$state" in
      exited:* | dead:*) break ;;
    esac
    sleep 1
  done
  logs="$(docker compose logs --no-color --no-log-prefix stoa-gateway 2>&1)"
  if [[ "$state" != 'exited:1' || "$logs" != *"$reason"* ]]; then
    echo "FAIL: $variant did not produce its expected admission decision (state: $state)" >&2
    return 1
  fi
  printf 'PASS: skill %s refused before readiness\n' "$variant"
}

echo "=== [3/4] Checking all three skill admission decisions ==="
check_refused signature 'skill signature was not accepted'
check_refused manifest 'skill manifest schema was not accepted'
check_refused drift 'skill tool schema differs from the registry'

echo "=== [4/4] Checking exact upstream-mock counters ==="
stats="$(docker compose exec -T upstream-mock cat /tmp/upstream_stats.json)"
printf '%s\n' "$stats"
printf '%s\n' "$stats" | python3 -c '
import json
import sys

actual = json.load(sys.stdin)
expected = {
    "upstream_calls": 2,
    "valid_api_key_calls": 2,
    "accepted_skill_context_calls": 2,
    "fail_calls": 0,
    "forbidden_calls": 0,
    "caller_auth_headers_seen": 0,
    "redirect_target_calls": 0,
    "oauth2_calls": 0,
}
assert actual == expected, "unexpected upstream mock counters"
print("PASS: mock received only two authorized calls, both with the admitted skill context")
'

echo "=== JALON 4 DOCKER COMPOSE VERIFICATION PASSED ==="
