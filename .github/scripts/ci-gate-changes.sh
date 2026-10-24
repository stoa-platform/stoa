#!/usr/bin/env bash
# Print component flags for BASE..HEAD.
# Paths are read with `git diff -z --no-renames --name-only`:
# NUL-separated, with a rename reported as a deletion plus an addition.
set -euo pipefail
export LC_ALL=C

if [[ $# -ne 2 ]]; then
  echo "usage: ci-gate-changes.sh BASE HEAD" >&2
  exit 2
fi

base="$1"
head="$2"
changed="$(mktemp)"
trap 'rm -f "$changed"' EXIT
git diff -z --no-renames --name-only "$base" "$head" > "$changed"

check() {
  local name="$1"
  local pattern="$2"
  local value="false"
  local status=0
  # grep: 0 = match, 1 = no match. Any other status is an error, not "unchanged".
  grep -z -qE -- "$pattern" "$changed" || status=$?
  if [[ "$status" -eq 0 ]]; then
    value="true"
  elif [[ "$status" -ne 1 ]]; then
    printf 'ci-gate-changes: grep exited %s for %s\n' "$status" "$name" >&2
    exit "$status"
  fi
  printf '%s=%s\n' "$name" "$value"
  if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    printf '%s=%s\n' "$name" "$value" >> "$GITHUB_OUTPUT"
  fi
  printf '%s: %s\n' "$name" "$value" >&2
}

common='^\.github/workflows/ci-gate\.yml$|^\.github/actions/'
check control-plane-api "^control-plane-api/|^\.github/workflows/(control-plane-api-ci|reusable-python-ci)\.yml$|${common}"
check stoa-gateway "^stoa-gateway/|^\.github/workflows/(stoa-gateway-ci|reusable-rust-ci)\.yml$|${common}"
check control-plane-ui "^control-plane-ui/|^shared/|^\.github/workflows/(control-plane-ui-ci|reusable-node-ci)\.yml$|${common}"
check portal "^portal/|^shared/|^\.github/workflows/(stoa-portal-ci|reusable-node-ci)\.yml$|${common}"
check stoa-go "^stoa-go/|^\.github/workflows/stoa-go-ci\.yml$|^\.github/workflows/ci-gate\.yml$"
check stoa-operator "^stoa-operator/|^\.github/workflows/(stoa-operator-ci|reusable-python-ci)\.yml$|^\.github/workflows/ci-gate\.yml$|^\.github/actions/"
check helm "^charts/|^\.github/workflows/helm-lint\.yml$|^\.github/workflows/ci-gate\.yml$"
check gate-contract '^\.github/scripts/ci-gate-.*\.sh$|^scripts/ci/tests/test_ci_gate_contract\.py$'
