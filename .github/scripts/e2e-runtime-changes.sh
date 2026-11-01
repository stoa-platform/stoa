#!/usr/bin/env bash
# CAB-2343: only application/test changes justify live E2E on push.
set -euo pipefail
if [[ $# -ne 2 ]]; then
  echo "usage: e2e-runtime-changes.sh BASE HEAD" >&2
  exit 2
fi
changed="$(mktemp)"
trap 'rm -f "$changed"' EXIT
git diff -z --no-renames --name-only "$1" "$2" > "$changed"
runtime=false
while IFS= read -r -d '' path; do
  case "$path" in
    e2e/*.md|portal/*.md|control-plane-ui/*.md) ;;
    portal/k8s/*|control-plane-ui/k8s/*) ;;
    e2e/*|portal/*|control-plane-ui/*) runtime=true ;;
  esac
done < "$changed"
printf 'runtime=%s\n' "$runtime"
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  printf 'runtime=%s\n' "$runtime" >> "$GITHUB_OUTPUT"
fi
