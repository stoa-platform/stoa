#!/usr/bin/env bash
set +x
set -euo pipefail

if ! command -v python3 >/dev/null 2>&1; then
  printf 'error: python3 is required to run the agent demo.\n' >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 -B "$SCRIPT_DIR/agent_demo.py" "$@"
