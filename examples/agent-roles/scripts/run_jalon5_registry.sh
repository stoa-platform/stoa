#!/usr/bin/env bash
set +x
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

export COMPOSE_FILE="$DIR/docker-compose.yml:$DIR/docker-compose.registry.yml"
export COMPOSE_PROJECT_NAME="poc-roles-agents-registry-$(openssl rand -hex 6)"
export STOA_POC_BOOTSTRAP_SECRET="$(openssl rand -hex 24)"
# Public marker used only by the local backend fixture.
export STOA_POC_UPSTREAM_API_KEY="registry-example-backend-marker"
export STOA_POC_EXPECTED_SKILL_CONTEXT="Every payment lookup uses a currency."
export STOA_POC_CHAIN_BUDGET=3
export STOA_POC_CALLER_BUDGET=3

runtime_root="$(mktemp -d /tmp/stoa-poc-registry.XXXXXXXX)"
runtime_root="$(cd "$runtime_root" && pwd -P)"
export STOA_POC_RUNTIME_DIR="$runtime_root/accepted"

cleanup() {
  local status=$?
  trap - EXIT
  if ! docker compose down -v --remove-orphans >/dev/null 2>&1; then
    echo 'FAIL: could not clean up the registry test project' >&2
    status=1
  fi
  rm -rf -- "$runtime_root"
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo '=== Building the registry scenario with both MCP surfaces ==='
python3 ./scripts/gen_fixtures.py "$STOA_POC_RUNTIME_DIR" --jalon4 accepted
python3 -B ./registry_isolation.py fixtures "$STOA_POC_RUNTIME_DIR"
docker compose build stoa-gateway upstream-mock agent-parent control-plane-mock
docker compose up -d --no-build --wait --wait-timeout 45 agent-parent

echo '=== Checking startup discovery and Control Plane refresh ==='
docker compose exec -T control-plane-mock python3 -B /app/registry_isolation.py token |
  docker compose exec -T agent-parent python3 -B /app/registry_isolation.py prove

echo '=== Checking mock counters ==='
control_plane_stats="$(docker compose exec -T control-plane-mock python3 -B /app/registry_isolation.py stats)"
upstream_stats="$(docker compose exec -T upstream-mock cat /tmp/upstream_stats.json)"
printf '%s\n%s\n' "$control_plane_stats" "$upstream_stats" |
  python3 -B ./registry_isolation.py counters

echo '=== JALON 5 REGISTRY VERIFICATION PASSED ==='
