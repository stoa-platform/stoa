#!/usr/bin/env bash
# coverage-ratchet.sh — Auto-bump coverage thresholds when coverage increases >= 2%
# Designed for CI: detects current coverage, compares to threshold, bumps if improved.
# Usage: ./scripts/ai-ops/coverage-ratchet.sh [--dry-run]
# Exits 0 on success, 1 on error. Outputs proposed changes to stdout.
set -euo pipefail

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
RATCHET_THRESHOLD=2  # minimum % improvement to trigger a bump

# --- Python (control-plane-api) ---
ratchet_python() {
  local component="control-plane-api"
  local config_file="${REPO_ROOT}/${component}/pyproject.toml"

  if [[ ! -f "$config_file" ]]; then
    echo "SKIP: ${config_file} not found"
    return
  fi

  # Extract current fail_under from pyproject.toml
  local current_threshold
  current_threshold=$(grep -oP 'fail_under\s*=\s*\K[0-9]+' "$config_file" 2>/dev/null | head -1) || true
  if [[ -z "$current_threshold" ]]; then
    echo "SKIP: no fail_under found in ${config_file}"
    return
  fi

  # Run pytest to get actual coverage (quiet, just the percentage)
  local actual_coverage
  actual_coverage=$(cd "${REPO_ROOT}/${component}" && \
    python3 -m pytest tests/ --cov=src --cov-report=term --ignore=tests/test_opensearch.py -q 2>/dev/null \
    | grep -oP 'TOTAL\s+\S+\s+\S+\s+\K[0-9]+(?=%)' | head -1) || true

  if [[ -z "$actual_coverage" ]]; then
    echo "SKIP: could not determine ${component} coverage"
    return
  fi

  local diff=$((actual_coverage - current_threshold))
  echo "${component}: threshold=${current_threshold}% actual=${actual_coverage}% diff=+${diff}%"

  if [[ "$diff" -ge "$RATCHET_THRESHOLD" ]]; then
    local new_threshold=$((actual_coverage))
    echo "  RATCHET: ${current_threshold}% → ${new_threshold}%"
    if [[ "$DRY_RUN" == "false" ]]; then
      sed -i.bak "s/fail_under = ${current_threshold}/fail_under = ${new_threshold}/" "$config_file"
      rm -f "${config_file}.bak"
      echo "  UPDATED: ${config_file}"
    else
      echo "  DRY-RUN: would update ${config_file}"
    fi
  else
    echo "  OK: improvement < ${RATCHET_THRESHOLD}%, no ratchet needed"
  fi
}

# --- TypeScript (control-plane-ui, portal) ---
ratchet_typescript() {
  local component="$1"
  local config_file="${REPO_ROOT}/${component}/vitest.config.ts"

  # Also check vitest.config.mts
  if [[ ! -f "$config_file" ]]; then
    config_file="${REPO_ROOT}/${component}/vitest.config.mts"
  fi
  if [[ ! -f "$config_file" ]]; then
    echo "SKIP: no vitest config found for ${component}"
    return
  fi

  # Extract coverage threshold (lines or statements)
  local current_threshold
  current_threshold=$(grep -oP '(lines|statements)\s*:\s*\K[0-9]+' "$config_file" 2>/dev/null | head -1) || true
  if [[ -z "$current_threshold" ]]; then
    echo "SKIP: no coverage threshold found in ${config_file}"
    return
  fi

  # Run vitest coverage to get actual %
  local actual_coverage
  actual_coverage=$(cd "${REPO_ROOT}/${component}" && \
    npx vitest run --coverage --reporter=verbose 2>/dev/null \
    | grep -oP 'All files\s*\|\s*\K[0-9.]+' | head -1 | cut -d. -f1) || true

  if [[ -z "$actual_coverage" ]]; then
    echo "SKIP: could not determine ${component} coverage"
    return
  fi

  local diff=$((actual_coverage - current_threshold))
  echo "${component}: threshold=${current_threshold}% actual=${actual_coverage}% diff=+${diff}%"

  if [[ "$diff" -ge "$RATCHET_THRESHOLD" ]]; then
    local new_threshold=$((actual_coverage))
    echo "  RATCHET: ${current_threshold}% → ${new_threshold}%"
    if [[ "$DRY_RUN" == "false" ]]; then
      # Replace the first occurrence of the threshold value in coverage config
      sed -i.bak "0,/\(lines\|statements\)\s*:\s*${current_threshold}/s//${component_key}: ${new_threshold}/" "$config_file" 2>/dev/null || \
        sed -i.bak "s/lines: ${current_threshold}/lines: ${new_threshold}/" "$config_file"
      rm -f "${config_file}.bak"
      echo "  UPDATED: ${config_file}"
    else
      echo "  DRY-RUN: would update ${config_file}"
    fi
  else
    echo "  OK: improvement < ${RATCHET_THRESHOLD}%, no ratchet needed"
  fi
}

# --- Main ---
echo "=== Coverage Ratchet $(date -u +%Y-%m-%d) ==="
echo "Mode: $( [[ "$DRY_RUN" == "true" ]] && echo 'DRY-RUN' || echo 'LIVE' )"
echo ""

ratchet_python
echo ""
ratchet_typescript "control-plane-ui"
echo ""
ratchet_typescript "portal"

echo ""
echo "Done."
