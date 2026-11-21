#!/usr/bin/env bash
# Export PoC decision journal and health snapshot from stoa-gateway into an
# existing private (0700) non-symlink directory using no-clobber publication.
set +x
set -euo pipefail
umask 077

if [[ $# -ne 1 || -z "$1" ]]; then
  printf 'Usage: %s <export-dir>\n' "$0" >&2
  exit 2
fi

raw_dir="$1"

export_dir="$(python3 -c '
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
' "$raw_dir" 2>/dev/null)" || {
  printf 'FAIL: export directory must be an existing private (0700) non-symlink directory owned by current user\n' >&2
  exit 1
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

readonly REMOTE_DIR="/tmp/stoa-poc-floors/decisions"
readonly FILES=("decisions.ndjson" "decisions.health.json")
readonly LOCK_TIMEOUT_SECS="${STOA_POC_EXPORT_LOCK_TIMEOUT_SECS:-10}"
readonly TAR_TIMEOUT_SECS="${STOA_POC_EXPORT_TAR_TIMEOUT_SECS:-8}"

if [[ ! "$LOCK_TIMEOUT_SECS" =~ ^[1-9][0-9]*$ ]] || (( LOCK_TIMEOUT_SECS > 300 )); then
  printf 'FAIL: STOA_POC_EXPORT_LOCK_TIMEOUT_SECS must be an integer between 1 and 300\n' >&2
  exit 2
fi
if [[ ! "$TAR_TIMEOUT_SECS" =~ ^[1-9][0-9]*$ ]] || (( TAR_TIMEOUT_SECS > 300 )); then
  printf 'FAIL: STOA_POC_EXPORT_TAR_TIMEOUT_SECS must be an integer between 1 and 300\n' >&2
  exit 2
fi

tmp_files=()
published_files=()
cleanup() {
  local status="$1"
  local f
  if [[ ${#tmp_files[@]} -gt 0 ]]; then
    for f in "${tmp_files[@]}"; do
      [[ -n "$f" && -e "$f" ]] && rm -f -- "$f"
    done
  fi
  if [[ "$status" != 0 && ${#published_files[@]} -gt 0 ]]; then
    for f in "${published_files[@]}"; do
      [[ -n "$f" && -e "$f" ]] && rm -f -- "$f"
    done
  fi
}
trap 'cleanup $?' EXIT

# Refuse any pre-existing destination before staging.
for name in "${FILES[@]}"; do
  dest="$export_dir/$name"
  if [[ -e "$dest" || -L "$dest" ]]; then
    printf 'FAIL: export destination %s already exists (overwrite refused)\n' "$name" >&2
    exit 1
  fi
done

# Stage only the two published outputs into unique 0600 temp files.
staged_ndjson="$(mktemp "$export_dir/.decisions.ndjson.tmp.XXXXXXXX")"
staged_health="$(mktemp "$export_dir/.decisions.health.json.tmp.XXXXXXXX")"
remote_err="$(mktemp "$export_dir/.export.remote.err.XXXXXXXX")"
tmp_files+=("$staged_ndjson" "$staged_health" "$remote_err")
staged_paths=("$staged_ndjson" "$staged_health")

# Take a single coherent tar snapshot inside stoa-gateway under a shared flock on
# decisions.snapshot.lock, allowing only canonical journal/segment, manifest, and
# health regular files (never symlinks, keys, secrets, or lock files).
remote_script='
set -eu
LC_ALL=C
export LC_ALL
d="$1"
lock_timeout="$2"
tar_timeout="$3"
lock="$d/decisions.snapshot.lock"

if [ -L "$lock" ] || [ ! -f "$lock" ]; then
  printf "LOCK_MISSING\n" >&2
  exit 10
fi

{
  if ! flock -s -w "$lock_timeout" 9; then
    printf "LOCK_TIMEOUT\n" >&2
    exit 11
  fi

  set --
  if [ -L "$d/decisions.health.json" ] || [ ! -f "$d/decisions.health.json" ]; then
    printf "HEALTH_MISSING\n" >&2
    exit 12
  fi
  set -- "$@" "decisions.health.json"

  if [ -e "$d/decisions.manifest.json" ] || [ -L "$d/decisions.manifest.json" ]; then
    if [ -L "$d/decisions.manifest.json" ] || [ ! -f "$d/decisions.manifest.json" ]; then
      printf "INVALID_FILE\n" >&2
      exit 13
    fi
    set -- "$@" "decisions.manifest.json"
  fi

  if [ -e "$d/decisions.ndjson" ] || [ -L "$d/decisions.ndjson" ]; then
    if [ -L "$d/decisions.ndjson" ] || [ ! -f "$d/decisions.ndjson" ]; then
      printf "INVALID_FILE\n" >&2
      exit 13
    fi
    set -- "$@" "decisions.ndjson"
  fi

  for p in "$d"/decisions.[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].ndjson; do
    [ -e "$p" ] || [ -L "$p" ] || continue
    if [ -L "$p" ] || [ ! -f "$p" ]; then
      printf "INVALID_FILE\n" >&2
      exit 13
    fi
    set -- "$@" "${p##*/}"
  done

  set +e
  timeout -k 2 "$tar_timeout" tar -cf - -C "$d" -- "$@"
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    if [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; then
      printf "TAR_TIMEOUT\n" >&2
      exit 14
    fi
    printf "TAR_FAILED\n" >&2
    exit 15
  fi
} 9< "$lock"
'

set +e
docker compose exec -T stoa-gateway sh -c "$remote_script" _ "$REMOTE_DIR" "$LOCK_TIMEOUT_SECS" "$TAR_TIMEOUT_SECS" 2>"$remote_err" \
  | python3 -B "$script_dir/export_decisions_archive.py" "$staged_ndjson" "$staged_health"
pipe_statuses=("${PIPESTATUS[@]}")
set -e

remote_status="${pipe_statuses[0]:-1}"
py_status="${pipe_statuses[1]:-1}"

if [[ "$remote_status" != 0 ]]; then
  err_token="$(head -n 1 "$remote_err" 2>/dev/null | tr -d '\r\n' || true)"
  case "$err_token" in
    LOCK_MISSING)
      printf 'FAIL: decisions.snapshot.lock is missing in stoa-gateway; refusing unlocked export\n' >&2
      ;;
    LOCK_TIMEOUT)
      printf 'FAIL: timed out waiting for shared decisions.snapshot.lock in stoa-gateway\n' >&2
      ;;
    HEALTH_MISSING)
      printf 'FAIL: decisions.health.json is missing or invalid in stoa-gateway\n' >&2
      ;;
    INVALID_FILE)
      printf 'FAIL: non-regular or symlink file encountered in stoa-gateway decision spool\n' >&2
      ;;
    TAR_TIMEOUT)
      printf 'FAIL: timed out while streaming snapshot tar under shared lock in stoa-gateway\n' >&2
      ;;
    TAR_FAILED)
      printf 'FAIL: tar snapshot failed in stoa-gateway\n' >&2
      ;;
    *)
      if [[ "$py_status" == 0 ]]; then
        printf 'FAIL: unable to snapshot decisions from stoa-gateway\n' >&2
      fi
      ;;
  esac
  exit 1
fi

if [[ "$py_status" != 0 ]]; then
  exit 1
fi

for tmp_file in "${staged_paths[@]}"; do
  if [[ ! -s "$tmp_file" ]]; then
    printf 'FAIL: staged export file is empty\n' >&2
    exit 1
  fi
done

# Publish atomically with no-clobber hard links (link(2) fails with EEXIST if target exists).
for i in "${!FILES[@]}"; do
  name="${FILES[$i]}"
  dest="$export_dir/$name"
  if ! ln -- "${staged_paths[$i]}" "$dest" 2>/dev/null; then
    printf 'FAIL: unable to publish %s without clobbering existing destination\n' "$name" >&2
    exit 1
  fi
  published_files+=("$dest")
done

# Remove staging temp links now that both destinations are published.
for f in "${tmp_files[@]}"; do
  rm -f -- "$f"
done
tmp_files=()
published_files=()
