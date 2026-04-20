#!/usr/bin/env bash
# dev-up.sh — one-shot local dev bring-up (k3d + stateful + Tilt).
# Idempotent: safe to re-run. Invoked by `make dev-up`.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INFRA_TILT="$REPO_ROOT/../stoa-infra/deploy/tilt"
ENVFILE="$REPO_ROOT/deploy/docker-compose/.env"

step() { printf "\n\033[1;34m==>\033[0m \033[1m%s\033[0m\n" "$1"; }
die()  { printf "\033[31mERROR:\033[0m %s\n" "$1" >&2; exit 1; }

[[ -d "$INFRA_TILT" ]] || die "stoa-infra not at ../stoa-infra — git clone it as a sibling of stoa/"
[[ -f "$ENVFILE" ]]    || die ".env missing — cp deploy/docker-compose/.env.example $ENVFILE"

for bin in tilt k3d docker; do
  command -v "$bin" >/dev/null 2>&1 || die "$bin not installed (brew install $bin)"
done

step "k3d cluster 'stoa-dev'"
if k3d cluster list 2>/dev/null | awk 'NR>1 {print $1}' | grep -qx stoa-dev; then
  echo "   already exists — skipping create"
else
  k3d cluster create --config "$INFRA_TILT/k3d-config.yaml"
fi

step "Stateful services (postgres, keycloak, redpanda)"
docker compose \
  -f "$INFRA_TILT/docker-compose-stateful.yml" \
  --env-file "$ENVFILE" \
  up -d

step "Tilt (k3d workloads + nginx proxy on :443)"
echo "   Ctrl+C to detach (Tilt keeps running — use 'make dev-down' to stop everything)"
cd "$REPO_ROOT"
exec tilt up
