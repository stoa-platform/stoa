#!/bin/bash
# Demo Scenario Teardown — thin wrapper around scenario-manager.py
#
# Usage:
#   ./scripts/demo/teardown.sh --scenario=citadelle
#   ./scripts/demo/teardown.sh --scenario=citadelle --dry-run
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

exec python3 "$SCRIPT_DIR/scenario-manager.py" teardown "$@"
