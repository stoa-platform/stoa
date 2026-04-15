#!/usr/bin/env bash
set -euo pipefail

# AI-Verified UI Validation metrics (CAB-1989 P5)
# Usage: scripts/e2e/measure-ai-ui-validation.sh [--json]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

JSON_OUT="${1:-}"

cross_val_specs=$(find e2e/tests/cross-validation -name '*.spec.ts' 2>/dev/null | wc -l | tr -d ' ')
a11y_specs=$(find e2e/tests/a11y -name '*.spec.ts' 2>/dev/null | wc -l | tr -d ' ')
fixtures=$(ls e2e/fixtures/{data-seeder,aria-helpers,seeded-test,a11y}.ts 2>/dev/null | wc -l | tr -d ' ')

testid_console=$(grep -rhoE 'data-testid="[^"]+"' control-plane-ui/src 2>/dev/null | sort -u | wc -l | tr -d ' ')
testid_portal=$(grep -rhoE 'data-testid="[^"]+"' portal/src 2>/dev/null | sort -u | wc -l | tr -d ' ')

# a11y coverage: pages with axe assertion
a11y_pages=$(grep -rhoE 'assertNoA11yViolations|auditA11y' e2e/tests 2>/dev/null | wc -l | tr -d ' ')

if [[ "$JSON_OUT" == "--json" ]]; then
  cat <<EOF
{
  "cross_validation_specs": $cross_val_specs,
  "a11y_specs": $a11y_specs,
  "fixtures_installed": $fixtures,
  "testids_console": $testid_console,
  "testids_portal": $testid_portal,
  "a11y_assertions": $a11y_pages
}
EOF
else
  cat <<EOF
AI-Verified UI Validation — coverage snapshot
=============================================
Cross-validation specs (API↔UI)  : $cross_val_specs
A11y specs                        : $a11y_specs
Fixtures installed (4 expected)   : $fixtures
data-testid count (Console)       : $testid_console
data-testid count (Portal)        : $testid_portal
A11y assertion call sites         : $a11y_pages
EOF
fi
