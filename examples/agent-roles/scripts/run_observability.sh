#!/usr/bin/env bash
# End-to-end Compose observability v1 proof reusing Jalon 3 and Demo recipes.
set +x
set -euo pipefail
umask 077

rotation_proof=0
if [[ "${STOA_POC_OBSERVABILITY_ROTATION_PROOF:-0}" == "1" ]]; then
  rotation_proof=1
fi

if [[ $# -gt 1 ]]; then
  printf 'Usage: %s [--rotation-proof]\n' "$0" >&2
  exit 2
fi
if [[ $# -eq 1 ]]; then
  if [[ "$1" == "--rotation-proof" ]]; then
    rotation_proof=1
  else
    printf 'Usage: %s [--rotation-proof]\n' "$0" >&2
    exit 2
  fi
fi

dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$dir"

keep_evidence=0
cleanup_dir=""
run_root=""
stage="préparation"

if [[ -n "${STOA_POC_OBSERVABILITY_EVIDENCE_DIR:-}" ]]; then
  raw_ev="$STOA_POC_OBSERVABILITY_EVIDENCE_DIR"
  trimmed_ev="$raw_ev"
  while [[ "$trimmed_ev" != "/" && "$trimmed_ev" == */ ]]; do
    trimmed_ev="${trimmed_ev%/}"
  done

  if [[ ! -e "$trimmed_ev" && ! -L "$trimmed_ev" ]]; then
    mkdir -m 0700 -- "$trimmed_ev"
  fi

  evidence_base="$(python3 -c '
import os
import stat
import sys

p = sys.argv[1]
trimmed = p.rstrip("/") or "/"
st = os.lstat(trimmed)
if not stat.S_ISDIR(st.st_mode):
    sys.exit(1)
if st.st_uid != os.geteuid():
    sys.exit(1)
if (stat.S_IMODE(st.st_mode) & 0o077) != 0:
    sys.exit(1)
print(os.path.realpath(trimmed))
' "$trimmed_ev" 2>/dev/null)" || {
    printf 'ÉCHEC · STOA_POC_OBSERVABILITY_EVIDENCE_DIR doit être un répertoire privé (0700), non lien symbolique, détenu par l’utilisateur courant.\n' >&2
    exit 1
  }

  # Create a unique per-run subdirectory so all prior evidence is preserved untouched.
  run_root="$(mktemp -d "$evidence_base/run.XXXXXXXX")"
  keep_evidence=1
else
  run_root="$(mktemp -d /tmp/stoa-poc-observability.XXXXXXXX)"
  run_root="$(cd "$run_root" && pwd -P)"
  cleanup_dir="$run_root"
fi

cleanup() {
  local status="$1"
  trap - EXIT
  if [[ -n "$cleanup_dir" && -d "$cleanup_dir" ]]; then
    rm -rf -- "$cleanup_dir"
  fi
  if [[ "$status" != 0 ]]; then
    printf 'ÉCHEC · %s (sortie %s).\n' "$stage" "$status" >&2
  fi
  exit "$status"
}
trap 'cleanup $?' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

j3_export="$run_root/jalon3"
demo_export="$run_root/demo"
logs_dir="$run_root/logs"
draft_dir="$run_root/stoactl-drafts"

mkdir -m 0700 -- "$j3_export" "$demo_export" "$logs_dir" "$draft_dir"

suffix="$(python3 -c 'import secrets; print(secrets.token_hex(4))')"

printf 'STOA · Preuve observabilité v1 (Compose)\n\n'

stage="recette Jalon 3"
(
  unset STOA_POC_RUNTIME_DIR || true
  export COMPOSE_PROJECT_NAME="stoa-obs-j3-$suffix"
  export STOA_POC_DECISIONS_EXPORT_DIR="$j3_export"
  if [[ "$rotation_proof" == 1 ]]; then
    export STOA_POC_DECISIONS_MAX_BYTES="${STOA_POC_ROTATION_PROOF_MAX_BYTES:-4096}"
    export STOA_POC_DECISIONS_MAX_FILES="${STOA_POC_ROTATION_PROOF_MAX_FILES:-32}"
  fi
  bash ./scripts/run_jalon3.sh >"$logs_dir/jalon3.log" 2>&1
)

stage="préparation images démo"
(
  export COMPOSE_PROJECT_NAME="stoa-obs-demo-prep-$suffix"
  unset STOA_POC_DECISIONS_EXPORT_DIR || true
  bash ./scripts/run_demo.sh --prepare >"$logs_dir/demo-prepare.log" 2>&1
)

stage="recette démo"
(
  export COMPOSE_PROJECT_NAME="stoa-obs-demo-$suffix"
  export STOA_POC_DECISIONS_EXPORT_DIR="$demo_export"
  bash ./scripts/run_demo.sh >"$logs_dir/demo.log" 2>&1
)

stage="vérification journaux NDJSON et CLI"
verify_args=()
if [[ "$rotation_proof" == 1 ]]; then
  verify_args+=(--require-rotation)
fi
if [[ -n "${STOA_POC_STOACTL_BIN:-}" ]]; then
  if [[ "$STOA_POC_STOACTL_BIN" != /* ]]; then
    printf 'ÉCHEC · STOA_POC_STOACTL_BIN doit être un chemin absolu.\n' >&2
    exit 1
  fi
  python3 -B ./scripts/verify_observability.py \
    ${verify_args[@]+"${verify_args[@]}"} "$j3_export" "$demo_export" "$STOA_POC_STOACTL_BIN" "$draft_dir"
else
  python3 -B ./scripts/verify_observability.py ${verify_args[@]+"${verify_args[@]}"} "$j3_export" "$demo_export"
fi

if [[ "$keep_evidence" == 1 ]]; then
  printf '\nPreuve       · conservée dans %s (fichiers 0600)\n' "$run_root"
fi
printf 'Résultat     · PASS\n'
