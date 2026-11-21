#!/usr/bin/env bash
set +x
set -euo pipefail
umask 077

# Preuve Compose locale du chantier relais (hôte Mac, même UID).
# Limites Mac même UID : le broker Go et les processus agents partagent le même UID
# macOS (permissions POSIX 0700/0600 uniquement, sans isolation noyau/namespace) ;
# l'isolation conteneur Linux complète fait l'objet du chantier ultérieur.
# Aucun profil utilisateur réel n'est lu ni modifié.

usage() {
  printf 'Usage : %s [--prepare] [--debug]\n' "$0"
  printf '  --prepare   Construit les images locales Gateway + mock, hors temps de preuve.\n'
  printf '  --debug     Affiche un extrait borné et expurgé du journal broker.\n'
  printf 'Env requis (hors --prepare) :\n'
  printf '  STOA_POC_STOACTL_BIN  Chemin absolu vers le binaire stoactl Mac déjà compilé.\n'
}

prepare_only=0
debug_mode=0
if [[ "${STOA_POC_RELAY_DEBUG:-0}" == "1" ]]; then
  debug_mode=1
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prepare)
      prepare_only=1
      ;;
    --debug)
      debug_mode=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
  shift
done

SECONDS=0
relay_limit=145
dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$dir"

runtime_root="$(mktemp -d /tmp/stoa-poc-relay.XXXXXXXX)"
chmod 0700 "$runtime_root"
runtime_root="$(cd "$runtime_root" && pwd -P)"

started_compose=0
broker_pid=""
stage="préparation"

bounded() {
  python3 -c '
import os
import signal
import subprocess
import sys

timeout = float(sys.argv[1])
try:
    process = subprocess.Popen(sys.argv[2:], start_new_session=True)
except OSError:
    sys.exit(126)

try:
    status = process.wait(timeout=timeout)
except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()
    status = 130 if isinstance(error, KeyboardInterrupt) else 124
sys.exit(status if status >= 0 else 128 - status)
' "$@"
}

step() {
  local remaining=$((relay_limit - SECONDS))
  ((remaining > 0)) || return 124
  bounded "$remaining" "$@"
}

stop_broker() {
  if [[ -n "$broker_pid" ]]; then
    if kill -0 "$broker_pid" 2>/dev/null; then
      kill -TERM "$broker_pid" 2>/dev/null || true
      local waited=0
      while kill -0 "$broker_pid" 2>/dev/null && ((waited < 30)); do
        python3 -c 'import time; time.sleep(0.1)'
        waited=$((waited + 1))
      done
      if kill -0 "$broker_pid" 2>/dev/null; then
        kill -KILL "$broker_pid" 2>/dev/null || true
      fi
    fi
    wait "$broker_pid" 2>/dev/null || true
    broker_pid=""
  fi
}

cleanup() {
  local status="$1"
  trap - EXIT
  stop_broker
  if [[ "$debug_mode" == 1 && -f "$runtime_root/op/broker.log" ]]; then
    python3 -B ./scripts/relay_smoke.py redact-log "$runtime_root/op/broker.log" --max-lines 20 || true
  fi
  if [[ "$started_compose" == 1 ]]; then
    if ! bounded 25 docker compose down -v --remove-orphans >/dev/null 2>&1; then
      printf 'ÉCHEC · nettoyage de la pile Compose incomplet.\n' >&2
      [[ "$status" != 0 ]] || status=1
    fi
  fi
  rm -rf -- "$runtime_root"
  if [[ "$status" != 0 ]]; then
    printf 'ÉCHEC · %s (sortie %s, %ss).\n' "$stage" "$status" "$SECONDS" >&2
  fi
  exit "$status"
}
trap 'cleanup $?' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

suffix="$(printf '%s' "${runtime_root##*.}" | tr '[:upper:]' '[:lower:]')"
export COMPOSE_PROJECT_NAME="stoa-roles-relay-$suffix"
export STOA_POC_RUNTIME_DIR="$runtime_root/fixtures"
export STOA_POC_BOOTSTRAP_SECRET="prepare-only"
export STOA_POC_UPSTREAM_API_KEY="refund-demo-backend-marker"
export STOA_POC_EXPECTED_SKILL_CONTEXT="Refunds are simulated in EUR."
export STOA_POC_CHAIN_BUDGET=2
export STOA_POC_CALLER_BUDGET=3
export STOA_POC_MAX_REVOKED_CHAINS=100

if [[ "$prepare_only" == 1 ]]; then
  stage="construction des images"
  cat > "$runtime_root/images.json" <<'JSON'
{
  "services": {
    "stoa-gateway": {"image": "stoa-roles-relay-local/gateway:relay"},
    "upstream-mock": {"image": "stoa-roles-relay-local/mock:relay"}
  }
}
JSON
  export COMPOSE_FILE="$dir/docker-compose.yml:$runtime_root/images.json"
  docker compose build stoa-gateway upstream-mock
  printf 'Images locales Gateway + mock prêtes. Lancez %s sans --prepare.\n' "$0"
  exit 0
fi

stage="validation du binaire stoactl"
stoactl_bin="${STOA_POC_STOACTL_BIN:-}"
if [[ -z "$stoactl_bin" || "$stoactl_bin" != /* || ! -f "$stoactl_bin" || ! -x "$stoactl_bin" ]]; then
  printf 'ÉCHEC · STOA_POC_STOACTL_BIN doit être un chemin absolu vers un binaire exécutable.\n' >&2
  exit 2
fi

stage="génération des fixtures et configuration relais"
STOA_POC_BOOTSTRAP_SECRET="$(step openssl rand -hex 24)"
step python3 -B ./scripts/gen_fixtures.py "$STOA_POC_RUNTIME_DIR" --refund-demo >/dev/null 2>&1

if [[ -n "${STOA_POC_RELAY_PORT:-}" ]]; then
  gateway_port="$(step python3 -B ./scripts/relay_smoke.py prepare "$runtime_root" --port "$STOA_POC_RELAY_PORT")"
else
  gateway_port="$(step python3 -B ./scripts/relay_smoke.py prepare "$runtime_root")"
fi
gateway_url="http://127.0.0.1:${gateway_port}"
export COMPOSE_FILE="$dir/docker-compose.yml:$runtime_root/relay-override.json"

stage="démarrage Compose loopback (préparez les images avec --prepare)"
started_compose=1
step docker compose up -d --no-build --pull never --wait --wait-timeout 45 stoa-gateway upstream-mock >/dev/null 2>&1

stage="vérification /ready loopback Gateway"
step python3 -c '
import sys, time, urllib.request
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
url = sys.argv[1] + "/ready"
deadline = time.monotonic() + 15.0
while time.monotonic() < deadline:
    try:
        with opener.open(url, timeout=2) as resp:
            if resp.status == 200 and resp.read().decode("utf-8", errors="replace").strip() == "READY":
                sys.exit(0)
    except Exception:
        pass
    time.sleep(0.2)
sys.exit(1)
' "$gateway_url"

stage="démarrage du broker local stoactl relay serve"
: > "$runtime_root/op/broker.log"
chmod 0600 "$runtime_root/op/broker.log"
env -i \
  PATH="$PATH" \
  HOME="$runtime_root/op/home" \
  LC_ALL="C" \
  "$stoactl_bin" relay serve --config "$runtime_root/op/relay-config.json" \
  >"$runtime_root/op/broker.log" 2>&1 &
broker_pid=$!

step python3 -c '
import os, socket, stat, sys, time
pid = int(sys.argv[1])
sockets = sys.argv[2:]
deadline = time.monotonic() + 15.0
while time.monotonic() < deadline:
    try:
        os.kill(pid, 0)
    except OSError:
        sys.exit(1)
    ready = True
    for path in sockets:
        try:
            if not stat.S_ISSOCK(os.stat(path).st_mode):
                ready = False
                break
        except OSError:
            ready = False
            break
    if ready:
        sys.exit(0)
    time.sleep(0.1)
sys.exit(1)
' "$broker_pid" "$runtime_root/mcp/parent.sock" "$runtime_root/op/control.sock"

stage="scénario relais MCP"
printf 'STOA · Preuve locale du relais (Gateway %s)\n\n' "$gateway_url"
step env -i \
  PATH="$PATH" \
  HOME="$runtime_root/agent-home" \
  LC_ALL="C" \
  python3 -B ./scripts/relay_smoke.py run \
  --stoactl "$stoactl_bin" \
  --runtime-root "$runtime_root" \
  --gateway-url "$gateway_url"

stage="vérification des compteurs amont"
stats="$(step docker compose exec -T upstream-mock cat /tmp/upstream_stats.json 2>/dev/null)"
printf '%s\n' "$stats" | step python3 -c '
import json
import sys

expected = {
    "upstream_calls": 2,
    "refund_calls": 2,
    "valid_api_key_calls": 2,
    "accepted_skill_context_calls": 2,
    "caller_auth_headers_seen": 0,
    "fail_calls": 0,
    "forbidden_calls": 0,
    "redirect_target_calls": 0,
    "oauth2_calls": 0,
}
try:
    actual = json.load(sys.stdin)
except ValueError:
    sys.exit(1)
if actual != expected:
    sys.exit(1)

print()
print("Amont        · 2 remboursements simulés authentifiés, 0 en-tête Authorization de l’appelant reçu")
'

stage="vérification du journal de décisions"
decisions_dir="$runtime_root/op/decisions"
mkdir -m 0700 "$decisions_dir"
step bash ./scripts/export_decisions.sh "$decisions_dir" >/dev/null
step python3 -B ./scripts/relay_smoke.py verify-decisions "$decisions_dir"

printf 'Limites Mac  · broker et agents sous le même UID hôte (permissions 0700/0600, isolation conteneur Linux ultérieure, aucun profil utilisateur touché)\n'
printf 'Durée totale · %ss\n' "$SECONDS"
