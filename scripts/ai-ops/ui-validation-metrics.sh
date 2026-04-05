#!/usr/bin/env bash
# ui-validation-metrics.sh — Baseline metrics for AI-verified UI testing (CAB-1992)
#
# Measures:
#   - data-testid count per component (Console, Portal)
#   - ARIA role count per component
#   - axe-core violation count (placeholder — requires live scan)
#   - Visual regression baseline count (placeholder — requires golden images)
#
# Output: JSON to stdout for tracking over time.
# Usage: ./scripts/ai-ops/ui-validation-metrics.sh [--json | --table]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

FORMAT="${1:---json}"

# ---------------------------------------------------------------------------
# Count data-testid attributes
# ---------------------------------------------------------------------------
count_testids() {
  local dir="$1"
  local label="$2"
  if [[ ! -d "$dir" ]]; then
    echo "0"
    return
  fi
  grep -r 'data-testid' "$dir" --include='*.tsx' --include='*.ts' -l 2>/dev/null | wc -l | tr -d ' '
}

count_testid_attrs() {
  local dir="$1"
  if [[ ! -d "$dir" ]]; then
    echo "0"
    return
  fi
  grep -ro 'data-testid=' "$dir" --include='*.tsx' --include='*.ts' 2>/dev/null | wc -l | tr -d ' '
}

# ---------------------------------------------------------------------------
# Count ARIA roles
# ---------------------------------------------------------------------------
count_aria_roles() {
  local dir="$1"
  if [[ ! -d "$dir" ]]; then
    echo "0"
    return
  fi
  grep -rE '(role="|aria-label="|aria-selected=)' "$dir" --include='*.tsx' --include='*.ts' 2>/dev/null | wc -l | tr -d ' '
}

# ---------------------------------------------------------------------------
# Gather metrics
# ---------------------------------------------------------------------------

CONSOLE_SRC="$REPO_ROOT/control-plane-ui/src"
PORTAL_SRC="$REPO_ROOT/portal/src"
E2E_DIR="$REPO_ROOT/e2e"

console_testid_files=$(count_testids "$CONSOLE_SRC" "console")
console_testid_attrs=$(count_testid_attrs "$CONSOLE_SRC")
console_aria=$(count_aria_roles "$CONSOLE_SRC")

portal_testid_files=$(count_testids "$PORTAL_SRC" "portal")
portal_testid_attrs=$(count_testid_attrs "$PORTAL_SRC")
portal_aria=$(count_aria_roles "$PORTAL_SRC")

# E2E fixture count
e2e_fixtures=0
if [[ -d "$E2E_DIR/fixtures" ]]; then
  e2e_fixtures=$(find "$E2E_DIR/fixtures" -name '*.ts' -not -name '*.d.ts' | wc -l | tr -d ' ')
fi

# axe-core installed?
axe_installed="false"
if grep -q '@axe-core/playwright' "$E2E_DIR/package.json" 2>/dev/null; then
  axe_installed="true"
fi

# Visual regression baselines (placeholder)
visual_baselines=0
if [[ -d "$E2E_DIR/golden" ]]; then
  visual_baselines=$(find "$E2E_DIR/golden" -name '*.png' 2>/dev/null | wc -l | tr -d ' ')
fi

# a11y violations (placeholder — requires live axe-core scan)
a11y_violations="null"

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

if [[ "$FORMAT" == "--table" ]]; then
  echo "=== UI Validation Metrics ($TIMESTAMP) ==="
  echo ""
  printf "%-25s %10s %10s %10s\n" "Component" "testid-files" "testid-attrs" "aria-attrs"
  printf "%-25s %10s %10s %10s\n" "-------------------------" "----------" "----------" "----------"
  printf "%-25s %10s %10s %10s\n" "Console (control-plane-ui)" "$console_testid_files" "$console_testid_attrs" "$console_aria"
  printf "%-25s %10s %10s %10s\n" "Portal" "$portal_testid_files" "$portal_testid_attrs" "$portal_aria"
  echo ""
  echo "E2E fixtures:           $e2e_fixtures"
  echo "axe-core installed:     $axe_installed"
  echo "Visual baselines:       $visual_baselines"
  echo "a11y violations:        ${a11y_violations:-not scanned}"
else
  cat <<ENDJSON
{
  "timestamp": "$TIMESTAMP",
  "console": {
    "testid_files": $console_testid_files,
    "testid_attrs": $console_testid_attrs,
    "aria_attrs": $console_aria
  },
  "portal": {
    "testid_files": $portal_testid_files,
    "testid_attrs": $portal_testid_attrs,
    "aria_attrs": $portal_aria
  },
  "e2e": {
    "fixture_count": $e2e_fixtures,
    "axe_core_installed": $axe_installed,
    "visual_baselines": $visual_baselines,
    "a11y_violations": $a11y_violations
  }
}
ENDJSON
fi
