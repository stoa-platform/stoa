#!/usr/bin/env bash
# dev-down.sh — stop Tilt workloads + stateful services.
# Does NOT delete the k3d cluster (use `k3d cluster delete stoa-dev` to nuke).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INFRA_TILT="$REPO_ROOT/../stoa-infra/deploy/tilt"
ENVFILE="$REPO_ROOT/deploy/docker-compose/.env"

step() { printf "\n\033[1;34m==>\033[0m \033[1m%s\033[0m\n" "$1"; }

step "Tilt workloads"
if command -v tilt >/dev/null 2>&1 && (cd "$REPO_ROOT" && tilt get session >/dev/null 2>&1); then
  (cd "$REPO_ROOT" && tilt down)
else
  echo "   Tilt session not active — skipping"
fi

step "stoa-proxy (nginx)"
if docker inspect stoa-proxy >/dev/null 2>&1; then
  docker rm -f stoa-proxy >/dev/null
  echo "   removed"
else
  echo "   not running"
fi

step "Stateful services"
if [[ -f "$ENVFILE" && -f "$INFRA_TILT/docker-compose-stateful.yml" ]]; then
  docker compose \
    -f "$INFRA_TILT/docker-compose-stateful.yml" \
    --env-file "$ENVFILE" \
    down
else
  echo "   compose files missing — skipping"
fi

echo ""
echo "k3d cluster 'stoa-dev' preserved. Run 'k3d cluster delete stoa-dev' to remove it."
