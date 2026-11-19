#!/usr/bin/env bash
# Regenerate the hash-locked Python requirements files from their versioned .in
# inputs using the hash-pinned uv release in .github/workflows/requirements/uv.txt.
set -euo pipefail
export LC_ALL=C

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UV_REQ="$ROOT/.github/workflows/requirements/uv.txt"
LOCK_OUT="$ROOT/control-plane-api/requirements-lock.txt"
BENCH_OUT="$ROOT/.github/workflows/requirements/stoa-bench.txt"

PINNED_UV="$(sed -nE 's/^uv==([^[:space:]\\]+).*/\1/p' "$UV_REQ" | head -n 1)"
if [[ -z "$PINNED_UV" ]]; then
  echo "error: could not parse pinned uv version from $UV_REQ" >&2
  exit 1
fi

TMPDIR_WORK="$(mktemp -d)"
cleanup() { rm -rf "$TMPDIR_WORK"; }
trap cleanup EXIT

resolve_uv() {
  if [[ -n "${UV_BIN:-}" ]]; then
    printf '%s\n' "$UV_BIN"
    return 0
  fi
  if command -v uv >/dev/null 2>&1; then
    local found_version
    found_version="$(uv --version 2>/dev/null | awk '{print $2}')"
    if [[ "$found_version" == "$PINNED_UV" ]]; then
      command -v uv
      return 0
    fi
  fi
  local venv="$TMPDIR_WORK/uv-venv"
  python3 -m venv "$venv"
  "$venv/bin/python" -m pip install --quiet --disable-pip-version-check --require-hashes -r "$UV_REQ"
  printf '%s\n' "$venv/bin/uv"
}

UV="$(resolve_uv)"

compile_lock() {
  local workdir="$1"
  local input="$2"
  local output="$3"
  local header="$4"
  local tmp_out
  tmp_out="$TMPDIR_WORK/$(basename "$output")"

  (cd "$workdir" && "$UV" pip compile "$input" \
    --universal \
    --python-version 3.11 \
    --generate-hashes \
    --no-build \
    --no-header \
    --quiet \
    -o "$output")

  {
    printf '%s\n' "$header"
    cat "$output"
  } > "$tmp_out"
  cp "$tmp_out" "$output"
}

LOCK_HEADER="# Hash-locked install set of the control-plane-api image (pip install --require-hashes).
# Source of truth: control-plane-api/requirements.txt + requirements-lock.in.
# Regenerate with: scripts/ci/regenerate-requirements-locks.sh
# scripts/ci/tests/test_regression_requirements_lock.py checks that it still satisfies requirements.txt."

BENCH_HEADER="# Hash-locked install set of stoa-bench.yml: control-plane-api/requirements.txt plus locust.
# Source of truth: control-plane-api/requirements.txt + .github/workflows/requirements/stoa-bench.in.
# Regenerate with: scripts/ci/regenerate-requirements-locks.sh
# scripts/ci/tests/test_regression_requirements_lock.py checks that it still satisfies requirements.txt."

compile_lock "$ROOT/control-plane-api" "requirements-lock.in" "$LOCK_OUT" "$LOCK_HEADER"
compile_lock "$ROOT/.github/workflows/requirements" "stoa-bench.in" "$BENCH_OUT" "$BENCH_HEADER"
