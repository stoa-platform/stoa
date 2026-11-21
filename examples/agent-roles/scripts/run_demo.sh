#!/usr/bin/env bash
set +x
set -euo pipefail

usage() {
  printf 'Usage : %s [--prepare | --show | --preview]\n' "${0##*/}"
  printf '  --prepare   Build local images outside demo execution.\n'
  printf '  --show      Run the full parent+child demo and print live HTTP and journal decisions.\n'
  printf '  --preview   Build local images, run the public preview scenario, verify exact decision_id correlation, and clean up.\n'
}

if [[ $# -gt 1 || ( $# -eq 1 && "$1" != "--prepare" && "$1" != "--show" && "$1" != "--preview" ) ]]; then
  usage >&2
  exit 2
fi

show_mode=0
preview_mode=0
if [[ "${1:-}" == "--show" ]]; then
  show_mode=1
  exec 3>&2 2>/dev/null
elif [[ "${1:-}" == "--preview" ]]; then
  preview_mode=1
  exec 3>&2
  if [[ "${STOA_DEMO_VERBOSE:-0}" != "1" ]]; then
    exec 2>/dev/null
  fi
fi

SECONDS=0
demo_limit=145
build_limit="${STOA_DEMO_BUILD_TIMEOUT:-1800}"
dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$dir"
runtime_root="$(mktemp -d /tmp/stoa-poc-demo.XXXXXXXX)"
runtime_root="$(cd "$runtime_root" && pwd -P)"
chmod 0700 "$runtime_root"
started=0
built_isolated=0
stage="préparation"
[[ "$show_mode" == 0 && "$preview_mode" == 0 ]] || stage="preparation"

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
  local remaining=$((demo_limit - SECONDS))
  ((remaining > 0)) || return 124
  bounded "$remaining" "$@"
}

cleanup() {
  local status="$1"
  trap - EXIT
  if [[ "$started" == 1 || "$built_isolated" == 1 ]]; then
    local down_args=(docker compose down -v --remove-orphans)
    if [[ "$preview_mode" == 1 && "${STOA_DEMO_KEEP_IMAGES:-0}" != "1" ]]; then
      down_args=(docker compose down -v --rmi all --remove-orphans)
    fi
    if ! bounded 40 "${down_args[@]}" >/dev/null 2>&1; then
      if [[ "$show_mode" == 1 || "$preview_mode" == 1 ]]; then
        printf 'FAILED · incomplete Compose stack cleanup.\n' >&3
      else
        printf 'ÉCHEC · nettoyage de la pile Compose incomplet.\n' >&2
      fi
      [[ "$status" != 0 ]] || status=1
    fi
  fi
  rm -rf -- "$runtime_root"
  if [[ "$status" != 0 ]]; then
    if [[ "$show_mode" == 1 || "$preview_mode" == 1 ]]; then
      printf 'FAILED · %s (exit %s).\n' "$stage" "$status" >&3
    else
      printf 'ÉCHEC · %s (sortie %s).\n' "$stage" "$status" >&2
    fi
  fi
  exit "$status"
}
trap 'cleanup $?' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

suffix="$(printf '%s' "${runtime_root##*.}" | tr '[:upper:]' '[:lower:]')"
if [[ "$show_mode" == 1 || "$preview_mode" == 1 ]]; then
  export COMPOSE_PROJECT_NAME="stoa-roles-demo-$suffix"
else
  export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-stoa-roles-demo-$suffix}"
fi
export COMPOSE_FILE="$dir/docker-compose.yml:$runtime_root/images.json"
export STOA_POC_RUNTIME_DIR="$runtime_root/fixtures"
export STOA_POC_BOOTSTRAP_SECRET="prepare-only"
export STOA_POC_UPSTREAM_API_KEY="refund-demo-backend-marker"
export STOA_POC_EXPECTED_SKILL_CONTEXT="Refunds are simulated in EUR."
export STOA_POC_CHAIN_BUDGET=2
export STOA_POC_CALLER_BUDGET=3
export STOA_POC_MAX_REVOKED_CHAINS=100

image_tag="demo"
if [[ "$preview_mode" == 1 ]]; then
  image_tag="$suffix"
fi

cat > "$runtime_root/images.json" <<JSON
{
  "services": {
    "stoa-gateway": {"image": "stoa-roles-demo-local/gateway:${image_tag}"},
    "upstream-mock": {"image": "stoa-roles-demo-local/mock:${image_tag}"},
    "agent-parent": {"image": "stoa-roles-demo-local/parent:${image_tag}"},
    "agent-child": {"image": "stoa-roles-demo-local/child:${image_tag}"}
  }
}
JSON

if [[ "$show_mode" == 1 || "$preview_mode" == 1 ]]; then
  python3 -c '
import json, sys
mount = {"type": "bind", "source": sys.argv[1], "target": "/app/demo.py", "read_only": True}
with open(sys.argv[2], "w", encoding="utf-8") as f:
    json.dump({"services": {"agent-parent": {"volumes": [mount]}, "agent-child": {"volumes": [mount]}}}, f)
' "$dir/demo.py" "$runtime_root/show.json"
  export COMPOSE_FILE="$COMPOSE_FILE:$runtime_root/show.json"
fi

if [[ "${1:-}" == "--prepare" ]]; then
  stage="construction des images"
  docker compose build
  printf 'Images locales prêtes. Lancez %s sans option.\n' "$0"
  exit 0
fi

if [[ "$preview_mode" == 1 ]]; then
  stage="Docker image build"
  built_isolated=1
  build_cmd=(docker compose build)
  if [[ "${STOA_DEMO_NO_CACHE:-0}" == "1" ]]; then
    build_cmd+=(--no-cache --pull)
  fi
  printf 'Building isolated local gateway and agent images...\n'
  if [[ "${STOA_DEMO_VERBOSE:-0}" == "1" ]]; then
    bounded "$build_limit" "${build_cmd[@]}"
  else
    bounded "$build_limit" "${build_cmd[@]}" >/dev/null 2>&1
  fi
  SECONDS=0
fi

stage="génération des fixtures de démo"
[[ "$show_mode" == 0 && "$preview_mode" == 0 ]] || stage="fixture generation"
STOA_POC_BOOTSTRAP_SECRET="$(step openssl rand -hex 24)"
if [[ "$preview_mode" == 1 ]]; then
  mkdir -m 0755 -p "$STOA_POC_RUNTIME_DIR"
  fixture_image="stoa-roles-demo-local/parent:${image_tag}"
  fixture_run=(
    docker
    run
    --rm
    --network none
    --user "$(id -u):$(id -g)"
    -e STOA_POC_UPSTREAM_API_KEY
    -e STOA_POC_EXPECTED_SKILL_CONTEXT
    -v "$dir/scripts/gen_fixtures.py:/tmp/gen_fixtures.py:ro"
    -v "$STOA_POC_RUNTIME_DIR:/tmp/poc-fixtures"
    "$fixture_image"
    python3 -B /tmp/gen_fixtures.py /tmp/poc-fixtures --refund-demo
  )
  step "${fixture_run[@]}" >/dev/null 2>&1
else
  step python3 ./scripts/gen_fixtures.py "$STOA_POC_RUNTIME_DIR" --refund-demo >/dev/null 2>&1
fi

stage="démarrage Compose (préparez les images avec --prepare)"
[[ "$show_mode" == 0 && "$preview_mode" == 0 ]] || stage="Compose startup"
started=1
step docker compose up -d --no-build --pull never --wait --wait-timeout 45 >/dev/null 2>&1

if [[ "$preview_mode" == 1 ]]; then
  stage="MCP preview scenario"
  step python3 -B ./demo.py host preview > "$runtime_root/trace.json" 2>/dev/null
elif [[ "$show_mode" == 1 ]]; then
  stage="MCP scenario"
  step python3 -B ./demo.py host show > "$runtime_root/trace.json" 2>/dev/null
else
  stage="scénario MCP"
  printf 'STOA · Remboursements simulés\n\n'
  step python3 -B ./demo.py host
fi

stage="vérification des compteurs amont"
[[ "$show_mode" == 0 && "$preview_mode" == 0 ]] || stage="upstream mock check"
stats="$(step docker compose exec -T upstream-mock cat /tmp/upstream_stats.json 2>/dev/null)"
expected_refunds=2
if [[ "$preview_mode" == 1 ]]; then
  expected_refunds=1
fi
caller_auth_seen="$(printf '%s\n' "$stats" | step python3 -c '
import json
import sys

expected_count = int(sys.argv[1])
expected = {
    "upstream_calls": expected_count,
    "refund_calls": expected_count,
    "valid_api_key_calls": expected_count,
    "accepted_skill_context_calls": expected_count,
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
if actual != expected or type(actual["caller_auth_headers_seen"]) is not int:
    sys.exit(1)
print(actual["caller_auth_headers_seen"])
' "$expected_refunds")"

if [[ "$preview_mode" == 1 ]]; then
  stage="decision journal export"
  show_export_dir="$runtime_root/decisions"
  mkdir -m 0700 "$show_export_dir"
  step bash ./scripts/export_decisions.sh "$show_export_dir" >/dev/null 2>&1

  if [[ -n "${STOA_POC_DECISIONS_EXPORT_DIR:-}" ]]; then
    stage="optional decision journal export"
    step bash ./scripts/export_decisions.sh "$STOA_POC_DECISIONS_EXPORT_DIR" >/dev/null 2>&1
  fi

  stage="preview report verification"
  step python3 -B ./scripts/preview_demo.py --preview "$runtime_root/trace.json" "$show_export_dir" "$caller_auth_seen"
elif [[ "$show_mode" == 1 ]]; then
  stage="decision journal export"
  show_export_dir="$runtime_root/decisions"
  mkdir -m 0700 "$show_export_dir"
  step bash ./scripts/export_decisions.sh "$show_export_dir" >/dev/null 2>&1

  if [[ -n "${STOA_POC_DECISIONS_EXPORT_DIR:-}" ]]; then
    stage="optional decision journal export"
    step bash ./scripts/export_decisions.sh "$STOA_POC_DECISIONS_EXPORT_DIR" >/dev/null 2>&1
  fi

  stage="show report verification"
  step python3 -B ./scripts/show_demo.py "$runtime_root/trace.json" "$show_export_dir" "$caller_auth_seen"
else
  printf '\nAmont        · 2 remboursements simulés authentifiés, 0 en-tête Authorization de l’appelant reçu\n'
  if [[ -n "${STOA_POC_DECISIONS_EXPORT_DIR:-}" ]]; then
    stage="export du journal de décisions"
    step bash ./scripts/export_decisions.sh "$STOA_POC_DECISIONS_EXPORT_DIR"
  fi
fi
