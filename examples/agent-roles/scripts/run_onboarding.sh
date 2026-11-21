#!/usr/bin/env bash
set +x
set -euo pipefail
umask 077

# Sauvegarde des descripteurs initiaux : sous Bash 3.2 macOS, une commande en erreur
# redirigée vers /dev/null peut sinon masquer la sortie du trap EXIT.
exec 3>&1 4>&2

# Recette locale isolée du smoke d'onboarding (hôte Mac, même UID, données 100% synthétiques).
# Aucun profil utilisateur réel n'est lu ni modifié ; aucune dépendance réseau externe.

usage() {
  printf 'Usage : %s [--prepare] [--client cursor|claude|codex] [--codex-bin /abs/path] [--debug]\n' "$0"
  printf '  --prepare               Construit les images locales Gateway + fixtures, sans démarrage.\n'
  printf '  --client <nom>          Copie synthétique cible : cursor (défaut), claude ou codex.\n'
  printf '  --codex-bin <chemin>    Chemin absolu optionnel transmis à stoactl pour le client codex.\n'
  printf '  --debug                 Affiche un extrait borné et expurgé du journal broker en sortie.\n'
  printf 'Env requis (hors --prepare) :\n'
  printf '  STOA_POC_STOACTL_BIN    Chemin absolu vers le binaire stoactl Mac déjà compilé.\n'
}

prepare_only=0
client="cursor"
codex_bin=""
debug_mode=0
if [[ "${STOA_POC_ONBOARDING_DEBUG:-0}" == "1" ]]; then
  debug_mode=1
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prepare)
      prepare_only=1
      ;;
    --client)
      shift
      if [[ $# -eq 0 ]]; then
        usage >&2
        exit 2
      fi
      client="$1"
      ;;
    --codex-bin)
      shift
      if [[ $# -eq 0 ]]; then
        usage >&2
        exit 2
      fi
      codex_bin="$1"
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

case "$client" in
  cursor|claude|codex) ;;
  *)
    printf 'FAIL · --client doit être cursor, claude ou codex.\n' >&2
    exit 2
    ;;
esac

if [[ -n "$codex_bin" && "$codex_bin" != /* ]]; then
  printf 'FAIL · --codex-bin doit être un chemin absolu.\n' >&2
  exit 2
fi

SECONDS=0
onboarding_limit=180
dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$dir"

runtime_root="$(mktemp -d /tmp/stoa-poc-onboarding.XXXXXXXX)"
chmod 0700 "$runtime_root"
runtime_root="$(cd "$runtime_root" && pwd -P)"

started_compose=0
broker_pid=""
stage="préparation"
last_reason=""

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
  local remaining=$((onboarding_limit - SECONDS))
  ((remaining > 0)) || return 124
  bounded "$remaining" "$@"
}

# Exécute une étape silencieuse sans redirection directe sur une commande `set -e`
# (compatibilité Bash 3.2 macOS) et capture une raison bornée/expurgée en cas d'échec.
run_step_logged() {
  local log_file="$runtime_root/last-step.log"
  : > "$log_file"
  chmod 0600 "$log_file"
  local rc=0
  if step "$@" >"$log_file" 2>&1; then
    rc=0
  else
    rc=$?
  fi
  if [[ "$rc" -ne 0 ]]; then
    last_reason="$(python3 -B ./scripts/onboarding_smoke.py summarize-log "$log_file" --runtime-root "$runtime_root" 2>/dev/null || true)"
    return "$rc"
  fi
  return 0
}

run_step_logged_stdin() {
  local stdin_file="$1"
  shift
  local log_file="$runtime_root/last-step.log"
  : > "$log_file"
  chmod 0600 "$log_file"
  local rc=0
  if step "$@" <"$stdin_file" >"$log_file" 2>&1; then
    rc=0
  else
    rc=$?
  fi
  if [[ "$rc" -ne 0 ]]; then
    last_reason="$(python3 -B ./scripts/onboarding_smoke.py summarize-log "$log_file" --runtime-root "$runtime_root" 2>/dev/null || true)"
    return "$rc"
  fi
  return 0
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

start_broker() {
  local log_file="$runtime_root/op/broker.log"
  : >> "$log_file"
  chmod 0600 "$log_file"
  rm -f -- "$runtime_root/mcp/parent.sock" "$runtime_root/op/control.sock"
  env -i \
    PATH="$PATH" \
    LC_ALL="C" \
    "$stoactl_bin" relay serve --config "$runtime_root/op/relay-config.json" \
    >>"$log_file" 2>&1 &
  broker_pid=$!

  step python3 -c '
import os, stat, sys, time
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
}

wait_gateway_ready() {
  local url="$1"
  step python3 -c '
import sys, time, urllib.request
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
url = sys.argv[1] + "/ready"
deadline = time.monotonic() + 20.0
while time.monotonic() < deadline:
    try:
        with opener.open(url, timeout=2) as resp:
            if resp.status == 200 and resp.read().decode("utf-8", errors="replace").strip() == "READY":
                sys.exit(0)
    except Exception:
        pass
    time.sleep(0.2)
sys.exit(1)
' "$url"
}

wait_vault_ready() {
  local url="$1"
  local cacert="$2"
  step python3 -c '
import ssl, sys, time, urllib.request
ssl_ctx = ssl.create_default_context(cafile=sys.argv[2])
opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    urllib.request.HTTPSHandler(context=ssl_ctx),
)
url = sys.argv[1] + "/v1/sys/health"
deadline = time.monotonic() + 15.0
while time.monotonic() < deadline:
    try:
        with opener.open(url, timeout=2) as resp:
            if resp.status == 200:
                sys.exit(0)
    except Exception:
        pass
    time.sleep(0.2)
sys.exit(1)
' "$url" "$cacert"
}

cleanup() {
  local status="$1"
  trap - EXIT
  stop_broker
  if [[ "$status" -ne 0 && "$started_compose" == 1 && -f "$runtime_root/onboarding-compose.json" ]]; then
    local gw_log="$runtime_root/gateway-diag.log"
    : > "$gw_log"
    chmod 0600 "$gw_log"
    if bounded 8 docker compose logs --no-color --tail=10 stoa-gateway >"$gw_log" 2>&1; then
      local gw_reason=""
      gw_reason="$(python3 -B ./scripts/onboarding_smoke.py summarize-log "$gw_log" --runtime-root "$runtime_root" 2>/dev/null || true)"
      if [[ -n "$gw_reason" ]]; then
        last_reason="$gw_reason"
      fi
    fi
  fi
  if [[ "$debug_mode" == 1 && -f "$runtime_root/op/broker.log" ]]; then
    python3 -B ./scripts/onboarding_smoke.py redact-log "$runtime_root/op/broker.log" --max-lines 25 >&4 2>&4 || true
  fi
  if [[ "$started_compose" == 1 ]]; then
    if ! bounded 25 docker compose down -v --remove-orphans >/dev/null 2>&1; then
      printf 'FAIL · nettoyage de la pile Compose incomplet.\n' >&4
      [[ "$status" != 0 ]] || status=1
    fi
  fi
  rm -rf -- "$runtime_root"
  if [[ "$status" != 0 ]]; then
    if [[ -n "$last_reason" ]]; then
      printf 'FAIL · %s (sortie %s, %ss) · %s\n' "$stage" "$status" "$SECONDS" "$last_reason" >&4
    else
      printf 'FAIL · %s (sortie %s, %ss).\n' "$stage" "$status" "$SECONDS" >&4
    fi
  fi
  exit "$status"
}
trap 'cleanup $?' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

suffix="$(printf '%s' "${runtime_root##*.}" | tr '[:upper:]' '[:lower:]')"
export COMPOSE_PROJECT_NAME="stoa-roles-onboarding-$suffix"
export STOA_POC_RUNTIME_DIR="$runtime_root/fixtures"
export STOA_POC_BOOTSTRAP_SECRET="prepare-only"

if [[ "$prepare_only" == 1 ]]; then
  stage="construction des images onboarding"
  cat > "$runtime_root/prepare-compose.json" <<JSON
{
  "services": {
    "stoa-gateway": {
      "image": "stoa-roles-onboarding-local/gateway:onboarding",
      "build": {
        "context": "$(cd "$dir/../../stoa-gateway" && pwd -P)",
        "dockerfile": "Dockerfile",
        "target": "runtime-debian"
      }
    },
    "onboarding-mcp": {
      "image": "stoa-roles-onboarding-local/fixture:onboarding",
      "build": {
        "context": "$dir",
        "dockerfile": "Dockerfile.agent"
      }
    }
  }
}
JSON
  export COMPOSE_FILE="$runtime_root/prepare-compose.json"
  docker compose build stoa-gateway onboarding-mcp
  printf 'PASS · Images locales Gateway + fixtures onboarding prêtes. Lancez %s sans --prepare.\n' "$0"
  exit 0
fi

stage="validation du binaire stoactl"
stoactl_bin="${STOA_POC_STOACTL_BIN:-}"
if [[ -z "$stoactl_bin" || "$stoactl_bin" != /* || ! -f "$stoactl_bin" || ! -x "$stoactl_bin" ]]; then
  last_reason="STOA_POC_STOACTL_BIN doit être un chemin absolu vers un binaire exécutable"
  exit 2
fi

stage="génération des fixtures signées (--onboarding-demo)"
STOA_POC_BOOTSTRAP_SECRET="$(step python3 -c 'import secrets; print(secrets.token_hex(24))')"
run_step_logged python3 -B ./scripts/gen_fixtures.py "$STOA_POC_RUNTIME_DIR" --onboarding-demo

stage="préparation des répertoires privés, ports loopback et config synthétique"
prep_args=(prepare "$runtime_root" --repo-dir "$dir" --client "$client")
if [[ -n "${STOA_POC_ONBOARDING_GATEWAY_PORT:-}" ]]; then
  prep_args+=(--gateway-port "$STOA_POC_ONBOARDING_GATEWAY_PORT")
fi
if [[ -n "${STOA_POC_ONBOARDING_VAULT_PORT:-}" ]]; then
  prep_args+=(--vault-port "$STOA_POC_ONBOARDING_VAULT_PORT")
fi
read -r gateway_port vault_port <<<"$(step python3 -B ./scripts/onboarding_smoke.py "${prep_args[@]}")"
gateway_url="http://127.0.0.1:${gateway_port}"
vault_url="https://127.0.0.1:${vault_port}"
vault_tls_dir="$runtime_root/op/tls"
vault_cacert="$vault_tls_dir/ca.crt"
export COMPOSE_FILE="$runtime_root/onboarding-compose.json"

stage="génération identité TLS éphémère Vault (SAN IP:127.0.0.1, LibreSSL)"
run_step_logged openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 1 \
  -config "$vault_tls_dir/ca.cnf" \
  -keyout "$vault_tls_dir/ca.key" \
  -out "$vault_tls_dir/ca.crt"
run_step_logged openssl req -new -newkey rsa:2048 -nodes \
  -config "$vault_tls_dir/server.cnf" \
  -keyout "$vault_tls_dir/server.key" \
  -out "$vault_tls_dir/server.csr"
run_step_logged openssl x509 -req -sha256 -days 1 \
  -in "$vault_tls_dir/server.csr" \
  -CA "$vault_tls_dir/ca.crt" \
  -CAkey "$vault_tls_dir/ca.key" \
  -CAcreateserial \
  -extfile "$vault_tls_dir/server.ext" \
  -out "$vault_tls_dir/server.crt"
chmod 0600 "$vault_tls_dir/ca.crt" "$vault_tls_dir/server.crt" "$vault_tls_dir/server.key"
rm -f -- "$vault_tls_dir/ca.key" "$vault_tls_dir/server.csr" "$vault_tls_dir/ca.srl"

stage="staging one-shot du jeton Vault (0600), TLS Vault (UID 1000) et /tmp/stoa-poc-floors/imports (0700)"
started_compose=1
run_step_logged_stdin "$runtime_root/op/vault-gateway.token" \
  docker compose \
  -f "$runtime_root/onboarding-compose.json" \
  -f "$runtime_root/staging-override.json" \
  run --rm -T --no-deps --user 0 --entrypoint sh stoa-gateway-stage -c \
  'umask 077 && mkdir -p /run/stoa-vault /tmp/stoa-poc-floors/imports && cat > /run/stoa-vault/gateway.token && chmod 0700 /run/stoa-vault /tmp/stoa-poc-floors/imports && chmod 0600 /run/stoa-vault/gateway.token && chown stoa:stoa /tmp/stoa-poc-floors && chown -R stoa:stoa /run/stoa-vault /tmp/stoa-poc-floors/imports && test -s /run/stoa-vault/gateway.token && test "$(stat -c "%U:%G %a" /run/stoa-vault/gateway.token)" = "stoa:stoa 600" && test -d /tmp/stoa-poc-floors/imports && test "$(stat -c "%U:%G %a" /tmp/stoa-poc-floors/imports)" = "stoa:stoa 700"'

run_step_logged_stdin "$vault_tls_dir/server.crt" \
  docker compose \
  -f "$runtime_root/onboarding-compose.json" \
  -f "$runtime_root/staging-override.json" \
  run --rm -T --no-deps --user 0 --entrypoint sh onboarding-vault-stage -c \
  'umask 077 && mkdir -p /run/vault-tls && cat > /run/vault-tls/server.crt && chmod 0700 /run/vault-tls && chmod 0600 /run/vault-tls/server.crt && chown -R 1000:1000 /run/vault-tls && test -s /run/vault-tls/server.crt'

run_step_logged_stdin "$vault_tls_dir/server.key" \
  docker compose \
  -f "$runtime_root/onboarding-compose.json" \
  -f "$runtime_root/staging-override.json" \
  run --rm -T --no-deps --user 0 --entrypoint sh onboarding-vault-stage -c \
  'umask 077 && cat > /run/vault-tls/server.key && chmod 0600 /run/vault-tls/server.key && chown 1000:1000 /run/vault-tls/server.key && test -s /run/vault-tls/server.key && test "$(stat -c "%u:%g %a" /run/vault-tls/server.key)" = "1000:1000 600" && test "$(stat -c "%u:%g %a" /run/vault-tls/server.crt)" = "1000:1000 600"'

stage="démarrage Compose loopback (préparez les images avec --prepare)"
run_step_logged docker compose up -d --no-build --pull never --wait --wait-timeout 45 \
  onboarding-mcp onboarding-vault stoa-gateway

stage="vérification /ready Gateway et /v1/sys/health Vault TLS"
wait_vault_ready "$vault_url" "$vault_cacert"
wait_gateway_ready "$gateway_url"

stage="démarrage du broker local stoactl relay serve"
start_broker

printf 'STOA · Smoke local d’onboarding (client=%s, copie synthétique isolée)\n' "$client"
printf '       Gateway=%s · Vault=%s\n\n' "$gateway_url" "$vault_url"

stage="onboarding (plan-only + confirm + smoke MCP)"
onboard_args=(onboard --stoactl "$stoactl_bin" --runtime-root "$runtime_root")
if [[ -n "$codex_bin" ]]; then
  onboard_args+=(--codex-bin "$codex_bin")
fi
step python3 -B ./scripts/onboarding_smoke.py "${onboard_args[@]}"

stage="persistance après redémarrage Gateway + broker"
stop_broker
run_step_logged docker compose restart stoa-gateway
wait_gateway_ready "$gateway_url"
start_broker
step python3 -B ./scripts/onboarding_smoke.py post-restart \
  --stoactl "$stoactl_bin" \
  --runtime-root "$runtime_root"

stage="vérification doctor sur copie séparée et restore exact"
restore_args=(doctor-restore --stoactl "$stoactl_bin" --runtime-root "$runtime_root")
if [[ -n "$codex_bin" ]]; then
  restore_args+=(--codex-bin "$codex_bin")
fi
step python3 -B ./scripts/onboarding_smoke.py "${restore_args[@]}"

stage="vérification des compteurs MCP et Vault"
mcp_stats="$(step docker compose exec -T onboarding-mcp python3 -c \
  'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:9000/stats", timeout=5).read().decode())')"
printf '%s\n' "$mcp_stats" | step python3 -B ./scripts/onboarding_smoke.py verify-stats \
  --runtime-root "$runtime_root" \
  --vault-url "$vault_url" \
  --min-mcp-calls 2

printf '\nLimites Mac  · copie synthétique isolée, même UID hôte (0700/0600), aucun profil utilisateur réel touché\n'
printf 'Durée totale · %ss\n' "$SECONDS"
