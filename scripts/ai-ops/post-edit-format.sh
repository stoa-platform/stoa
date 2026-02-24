#!/usr/bin/env bash
# PostToolUse hook: auto-format files after Edit/Write operations.
# Runs the appropriate formatter based on file extension.
# Non-blocking: exits 0 even if formatter fails (best-effort).

set -euo pipefail

FILE="${CLAUDE_FILE:-}"
[ -z "$FILE" ] && exit 0
[ ! -f "$FILE" ] && exit 0

EXT="${FILE##*.}"
DIR=$(dirname "$FILE")

# Find project root (closest directory with pyproject.toml, package.json, or Cargo.toml)
find_root() {
  local check_file="$1"
  local d="$DIR"
  while [ "$d" != "/" ]; do
    [ -f "$d/$check_file" ] && echo "$d" && return 0
    d=$(dirname "$d")
  done
  return 1
}

case "$EXT" in
  py)
    ROOT=$(find_root "pyproject.toml") || exit 0
    cd "$ROOT"
    ruff check --fix --quiet "$FILE" 2>/dev/null || true
    ruff format --quiet "$FILE" 2>/dev/null || true
    ;;
  rs)
    ROOT=$(find_root "Cargo.toml") || exit 0
    cd "$ROOT"
    rustfmt "$FILE" 2>/dev/null || true
    ;;
  ts|tsx|js|jsx)
    ROOT=$(find_root "package.json") || exit 0
    cd "$ROOT"
    npx prettier --write "$FILE" 2>/dev/null || true
    ;;
  json)
    # Only format if inside a project with package.json (skip standalone JSON)
    ROOT=$(find_root "package.json") || exit 0
    cd "$ROOT"
    npx prettier --write "$FILE" 2>/dev/null || true
    ;;
esac

exit 0
