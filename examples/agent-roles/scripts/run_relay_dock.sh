#!/usr/bin/env bash
set +x
set -euo pipefail
umask 077

# Preuve locale d'isolation conteneur Linux Compose du relais stoactl.
# Portée : prouve l'isolation réseau/FS/capabilities entre conteneurs Linux Compose
# (broker en network_mode:service:stoa-gateway, agents parent et enfant en
# network_mode:none avec volumes socket dédiés) ; ne prouve pas l'isolation
# d'agents exécutés nus sur l'hôte macOS.
# Aucun profil utilisateur réel n'est lu ni modifié.

usage() {
  printf 'Usage : %s [--prepare] [--debug]\n' "$0"
  printf '  --prepare   Construit les images locales dédiées (Gateway, mock, agent), hors temps de preuve.\n'
  printf '  --debug     Affiche un extrait borné et expurgé du journal broker.\n'
  printf 'Env requis (hors --prepare) :\n'
  printf '  STOA_POC_STOACTL_LINUX_BIN  Chemin absolu vers le binaire stoactl Linux (monté RO).\n'
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
dock_limit=145
dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$dir"

runtime_root="$(mktemp -d /tmp/stoa-poc-dock.XXXXXXXX)"
chmod 0700 "$runtime_root"
runtime_root="$(cd "$runtime_root" && pwd -P)"

started_compose=0
broker_exec_pid=""
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
  local remaining=$((dock_limit - SECONDS))
  ((remaining > 0)) || return 124
  bounded "$remaining" "$@"
}

stop_broker_exec() {
  if [[ -n "$broker_exec_pid" ]]; then
    if kill -0 "$broker_exec_pid" 2>/dev/null; then
      kill -TERM "$broker_exec_pid" 2>/dev/null || true
      local waited=0
      while kill -0 "$broker_exec_pid" 2>/dev/null && ((waited < 20)); do
        python3 -c 'import time; time.sleep(0.1)'
        waited=$((waited + 1))
      done
      if kill -0 "$broker_exec_pid" 2>/dev/null; then
        kill -KILL "$broker_exec_pid" 2>/dev/null || true
      fi
    fi
    wait "$broker_exec_pid" 2>/dev/null || true
    broker_exec_pid=""
  fi
}

cleanup() {
  local status="$1"
  trap - EXIT
  stop_broker_exec
  if [[ "$debug_mode" == 1 && -f "$runtime_root/op/broker.log" ]]; then
    python3 -B ./scripts/relay_smoke.py redact-log "$runtime_root/op/broker.log" --max-lines 20 || true
  fi
  if [[ "$started_compose" == 1 ]]; then
    if ! bounded 30 docker compose down -v --remove-orphans >/dev/null 2>&1; then
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
export COMPOSE_PROJECT_NAME="stoa-roles-dock-$suffix"
export COMPOSE_FILE="$dir/docker-compose.yml:$dir/docker-compose.relay-dock.yml"
export STOA_POC_RUNTIME_DIR="$runtime_root/fixtures"
export STOA_POC_DOCK_ENROLLMENTS_FILE="$runtime_root/gateway/relay-enrollments.json"
export STOA_POC_EXPECTED_SKILL_CONTEXT="Refunds are simulated in EUR."
export STOA_POC_CHAIN_BUDGET=2
export STOA_POC_CALLER_BUDGET=3
export STOA_POC_MAX_REVOKED_CHAINS=100

if [[ "$prepare_only" == 1 ]]; then
  stage="construction des images dédiées"
  export STOA_POC_BOOTSTRAP_SECRET=""
  export STOA_POC_UPSTREAM_API_KEY=""
  docker compose build stoa-gateway upstream-mock relay-broker
  printf 'Images locales dédiées prêtes (Gateway, mock, agent). Lancez %s sans --prepare.\n' "$0"
  exit 0
fi

stage="validation du binaire stoactl Linux"
stoactl_linux_bin="${STOA_POC_STOACTL_LINUX_BIN:-}"
if [[ -z "$stoactl_linux_bin" || "$stoactl_linux_bin" != /* || ! -f "$stoactl_linux_bin" || ! -x "$stoactl_linux_bin" ]]; then
  printf 'ÉCHEC · STOA_POC_STOACTL_LINUX_BIN doit être un chemin absolu vers un binaire Linux exécutable.\n' >&2
  exit 2
fi
step python3 -c '
import sys
with open(sys.argv[1], "rb") as handle:
    magic = handle.read(4)
if magic != b"\x7fELF":
    sys.exit(1)
' "$stoactl_linux_bin" || {
  printf 'ÉCHEC · STOA_POC_STOACTL_LINUX_BIN ne semble pas être un binaire ELF Linux.\n' >&2
  exit 2
}
export STOA_POC_STOACTL_LINUX_BIN="$stoactl_linux_bin"

stage="génération des fixtures et secrets runtime isolés"
STOA_POC_BOOTSTRAP_SECRET="$(step openssl rand -hex 24)"
STOA_POC_UPSTREAM_API_KEY="$(step openssl rand -hex 24)"
export STOA_POC_BOOTSTRAP_SECRET STOA_POC_UPSTREAM_API_KEY
step python3 -B ./scripts/gen_fixtures.py "$STOA_POC_RUNTIME_DIR" --refund-demo >/dev/null 2>&1
step python3 -B ./scripts/relay_dock_smoke.py prepare "$runtime_root"

stage="démarrage Compose isolé (préparez les images avec --prepare)"
started_compose=1
step docker compose up -d --no-build --pull never --wait --wait-timeout 45 \
  stoa-gateway upstream-mock relay-init relay-broker relay-parent relay-child >/dev/null 2>&1

stage="résolution de l'adresse IP privée du mock amont"
mock_ip="$(step docker compose exec -T upstream-mock python3 -c '
import socket
print(socket.gethostbyname(socket.gethostname()))
')"

stage="initialisation privée du broker"
step python3 -c '
import json, pathlib, sys
proof = pathlib.Path(sys.argv[1]).read_text(encoding="ascii").strip()
sys.stdout.write(json.dumps({"proof": proof}, separators=(",", ":")))
' "$runtime_root/op/proof" | step docker compose exec -T relay-broker \
  python3 -B /opt/stoa-proof/relay_dock_smoke.py init-broker
rm -f -- "$runtime_root/op/proof"

stage="démarrage du broker stoactl relay serve dans relay-broker"
: > "$runtime_root/op/broker.log"
chmod 0600 "$runtime_root/op/broker.log"
docker compose exec -T relay-broker \
  env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/run/stoa-relay/op/home LC_ALL=C \
  /usr/local/bin/stoactl relay serve --config /run/stoa-relay/op/relay-config.json \
  >"$runtime_root/op/broker.log" 2>&1 &
broker_exec_pid=$!

printf 'STOA · Preuve locale d’isolation Docker Compose du relais (Gateway interne http://127.0.0.1:8080)\n\n'

stage="vérification docker inspect (NetworkMode=none, ReadonlyRootfs, CapDrop=ALL, sans docker.sock)"
gateway_cid="$(step docker compose ps -q stoa-gateway)"
broker_cid="$(step docker compose ps -q relay-broker)"
parent_cid="$(step docker compose ps -q relay-parent)"
child_cid="$(step docker compose ps -q relay-child)"
step docker inspect "$gateway_cid" "$broker_cid" "$parent_cid" "$child_cid" | \
  step python3 -B ./scripts/relay_dock_smoke.py verify-inspect \
    --gateway-id "$gateway_cid" \
    --broker-id "$broker_cid" \
    --parent-id "$parent_cid" \
    --child-id "$child_cid"

stage="vérification broker + refus direct sans DPoP"
broker_netns="$(step docker compose exec -T relay-broker \
  python3 -B /opt/stoa-proof/relay_dock_smoke.py wait-broker --timeout 15)"
printf '1/6  Broker       · sockets 0600 (root/ctrl) prêts, appel direct sans DPoP refusé (HTTP 401), inspect OK (%ss)\n' "$SECONDS"

stage="scénario et isolation agent parent (network_mode:none)"
parent_netns="$(step docker compose exec -T relay-parent \
  python3 -B /opt/stoa-proof/relay_dock_smoke.py parent-check \
    --mock-ip "$mock_ip" \
    --disallowed-netns "$broker_netns")"
printf '2/6  Parent       · netns distinct + lo seul UP + 0 IP/route externe + refus DNS/IP/docker.sock/op/enfant, 501 € refusé, 500 € accepté (%ss)\n' "$SECONDS"

stage="délégation /v1/delegate sur socket contrôle depuis relay-broker"
delegated_json="$(step docker compose exec -T relay-broker \
  python3 -B /opt/stoa-proof/relay_dock_smoke.py delegate)"
child_socket="$(printf '%s\n' "$delegated_json" | python3 -c 'import json, sys; print(json.load(sys.stdin)["socket_path"])')"
child_ttl="$(printf '%s\n' "$delegated_json" | python3 -c 'import json, sys; print(json.load(sys.stdin)["expires_in"])')"
printf '3/6  Délégation   · socket enfant dédié créé (max_children=1, TTL %ss, C-1042, plafond 50 €) (%ss)\n' "$child_ttl" "$SECONDS"

stage="vérification séparation parent après délégation"
step docker compose exec -T relay-parent \
  python3 -B /opt/stoa-proof/relay_dock_smoke.py parent-probe-child --child-socket "$child_socket"
printf '4/6  Séparation   · socket enfant invisible et inaccessible au conteneur parent (%ss)\n' "$SECONDS"

stage="scénario et isolation agent enfant (network_mode:none)"
step docker compose exec -T relay-child \
  python3 -B /opt/stoa-proof/relay_dock_smoke.py child-check \
    --mock-ip "$mock_ip" \
    --socket "$child_socket" \
    --disallowed-netns "$broker_netns" \
    --disallowed-netns "$parent_netns" >/dev/null
printf '5/6  Enfant       · netns distinct + lo seul UP + 0 IP/route externe + refus DNS/IP/docker.sock/op/parent, 80 € et C-2077 refusés, 25 € accepté (%ss)\n' "$SECONDS"

stage="vérification des compteurs amont"
stats="$(step docker compose exec -T upstream-mock cat /tmp/upstream_stats.json 2>/dev/null)"
printf '%s\n' "$stats" | step python3 -B ./scripts/relay_dock_smoke.py verify-upstream
printf '6/6  Amont        · 2 remboursements simulés authentifiés, 0 en-tête Authorization appelant reçu (%ss)\n' "$SECONDS"

stage="vérification du journal de décisions"
decisions_dir="$runtime_root/op/decisions"
mkdir -m 0700 "$decisions_dir"
step bash ./scripts/export_decisions.sh "$decisions_dir" >/dev/null
printf '\n'
step python3 -B ./scripts/relay_smoke.py verify-decisions "$decisions_dir"

printf 'Portée       · isolation vérifiée entre conteneurs Linux Compose (network_mode:none, cap_drop:ALL, volumes socket dédiés) ; ne prouve pas l’isolation d’agents nus sur macOS\n'
printf 'Durée totale · %ss\n' "$SECONDS"
