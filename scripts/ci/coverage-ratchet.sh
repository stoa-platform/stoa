#!/usr/bin/env bash
# =============================================================================
# Coverage Ratchet — Auto-raise coverage thresholds (never lower)
# =============================================================================
# Usage: ./scripts/ci/coverage-ratchet.sh <component> <actual_coverage>
#
# Components: control-plane-api, control-plane-ui, portal
#
# Ratchet logic:
#   If actual_coverage > current_threshold + MARGIN → raise threshold
#   Threshold = floor(actual_coverage) - BUFFER
#   BUFFER prevents flaky failures from minor test timing differences
#
# This script only PRINTS the proposed change. Pass --apply to update the file.
# =============================================================================
set -euo pipefail

MARGIN=2    # Only ratchet if coverage exceeds threshold by this margin
BUFFER=1    # New threshold = floor(actual) - buffer (safety margin)

COMPONENT="${1:-}"
ACTUAL="${2:-}"
APPLY="${3:-}"

if [ -z "$COMPONENT" ] || [ -z "$ACTUAL" ]; then
  echo "Usage: $0 <component> <actual_coverage> [--apply]"
  echo "  component: control-plane-api | control-plane-ui | portal"
  echo "  actual_coverage: current coverage percentage (e.g., 78.5)"
  exit 1
fi

ACTUAL_INT=$(echo "$ACTUAL" | awk '{printf "%d", $1}')

ratchet_python() {
  local config="$1/pyproject.toml"
  if [ ! -f "$config" ]; then
    echo "ERROR: $config not found"
    exit 1
  fi

  local current
  current=$(grep -E '^fail_under\s*=' "$config" | head -1 | sed 's/[^0-9]//g')
  if [ -z "$current" ]; then
    echo "ERROR: fail_under not found in $config"
    exit 1
  fi

  local new_threshold=$((ACTUAL_INT - BUFFER))
  local diff=$((ACTUAL_INT - current))

  echo "Component: $1"
  echo "  Current threshold: ${current}%"
  echo "  Actual coverage:   ${ACTUAL}%"
  echo "  Margin required:   ${MARGIN}%"
  echo "  Diff:              ${diff}%"

  if [ "$diff" -lt "$MARGIN" ]; then
    echo "  Status: NO CHANGE (coverage not ${MARGIN}%+ above threshold)"
    return 0
  fi

  echo "  New threshold:     ${new_threshold}%"
  echo "  Status: RATCHET UP (+$((new_threshold - current))%)"

  if [ "$APPLY" = "--apply" ]; then
    sed -i.bak "s/^fail_under = ${current}/fail_under = ${new_threshold}/" "$config"
    rm -f "${config}.bak"
    echo "  Applied to $config"
  else
    echo "  (dry-run — pass --apply to update)"
  fi
}

ratchet_vitest() {
  local config="$1/vitest.config.ts"
  if [ ! -f "$config" ]; then
    echo "ERROR: $config not found"
    exit 1
  fi

  # For vitest, we ratchet the 'lines' threshold as the primary metric
  local current
  current=$(grep -E '^\s*lines:\s*[0-9]+' "$config" | head -1 | sed 's/[^0-9]//g')
  if [ -z "$current" ]; then
    echo "ERROR: lines threshold not found in $config"
    exit 1
  fi

  local new_threshold=$((ACTUAL_INT - BUFFER))
  local diff=$((ACTUAL_INT - current))

  echo "Component: $1"
  echo "  Current threshold (lines): ${current}%"
  echo "  Actual coverage:           ${ACTUAL}%"
  echo "  Margin required:           ${MARGIN}%"
  echo "  Diff:                      ${diff}%"

  if [ "$diff" -lt "$MARGIN" ]; then
    echo "  Status: NO CHANGE (coverage not ${MARGIN}%+ above threshold)"
    return 0
  fi

  echo "  New threshold:             ${new_threshold}%"
  echo "  Status: RATCHET UP (+$((new_threshold - current))%)"

  if [ "$APPLY" = "--apply" ]; then
    # Update lines threshold (primary metric for ratchet)
    sed -i.bak "s/lines: ${current}/lines: ${new_threshold}/" "$config"
    rm -f "${config}.bak"
    echo "  Applied lines threshold to $config"
  else
    echo "  (dry-run — pass --apply to update)"
  fi
}

case "$COMPONENT" in
  control-plane-api)
    ratchet_python "control-plane-api"
    ;;
  control-plane-ui)
    ratchet_vitest "control-plane-ui"
    ;;
  portal)
    ratchet_vitest "portal"
    ;;
  *)
    echo "ERROR: Unknown component '$COMPONENT'"
    echo "Valid: control-plane-api, control-plane-ui, portal"
    exit 1
    ;;
esac
