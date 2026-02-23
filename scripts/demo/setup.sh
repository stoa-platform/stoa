#!/bin/bash
# Demo Scenario Setup — thin wrapper around scenario-manager.py
#
# Usage:
#   ./scripts/demo/setup.sh --scenario=citadelle
#   ./scripts/demo/setup.sh --scenario=citadelle --dry-run
#   ./scripts/demo/setup.sh --list
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Forward to scenario-manager.py
if [[ "$1" == "--list" ]] || [[ "$1" == "-l" ]]; then
    exec python3 "$SCRIPT_DIR/scenario-manager.py" list
fi

exec python3 "$SCRIPT_DIR/scenario-manager.py" setup "$@"
