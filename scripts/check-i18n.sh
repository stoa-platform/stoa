#!/usr/bin/env bash
# check-i18n.sh — Top-level i18n validation for all UI components
#
# Runs component-specific i18n checks and validates the shared glossary.
# Referenced by scripts/check-i18n.sh in CI or locally.
#
# Usage:
#   bash scripts/check-i18n.sh          # Warning mode (non-blocking)
#   bash scripts/check-i18n.sh --strict  # Fail on any missing key
#
# Exit codes:
#   0 — All checks passed
#   1 — Missing keys detected (strict mode only)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STRICT=""
EXIT_CODE=0

if [[ "${1:-}" == "--strict" ]]; then
  STRICT="--fail-on-missing"
fi

echo "=== STOA i18n Validation ==="
echo ""

# -- 1. Console (control-plane-ui) -------------------------------------------

CONSOLE_SCRIPT="$REPO_ROOT/control-plane-ui/scripts/i18n-check.mjs"
if [[ -f "$CONSOLE_SCRIPT" ]]; then
  echo "[1/3] Console (control-plane-ui)"
  if ! node "$CONSOLE_SCRIPT" $STRICT; then
    EXIT_CODE=1
  fi
  echo ""
else
  echo "[1/3] Console — SKIPPED (no scripts/i18n-check.mjs)"
  echo ""
fi

# -- 2. Portal ----------------------------------------------------------------

PORTAL_SCRIPT="$REPO_ROOT/portal/scripts/i18n-check.mjs"
if [[ -f "$PORTAL_SCRIPT" ]]; then
  echo "[2/3] Portal"
  if ! node "$PORTAL_SCRIPT" $STRICT; then
    EXIT_CODE=1
  fi
  echo ""
else
  echo "[2/3] Portal — SKIPPED (no scripts/i18n-check.mjs)"
  echo ""
fi

# -- 3. Shared Glossary Validation --------------------------------------------

GLOSSARY="$REPO_ROOT/shared/i18n/glossary.json"
echo "[3/3] Shared Glossary"

if [[ ! -f "$GLOSSARY" ]]; then
  echo "  ERROR: Glossary not found at shared/i18n/glossary.json"
  EXIT_CODE=1
else
  # Validate JSON is well-formed
  if ! node -e "JSON.parse(require('fs').readFileSync('$GLOSSARY', 'utf-8'))" 2>/dev/null; then
    echo "  ERROR: Glossary is not valid JSON"
    EXIT_CODE=1
  else
    # Count terms and validate structure
    TERM_COUNT=$(node -e "
      const g = JSON.parse(require('fs').readFileSync('$GLOSSARY', 'utf-8'));
      const terms = Object.keys(g.terms || {});
      const langs = g._meta?.languages || [];
      let missing = 0;
      for (const [key, val] of Object.entries(g.terms || {})) {
        for (const lang of langs) {
          if (!val[lang]) {
            console.error('  MISSING: term \"' + key + '\" has no \"' + lang + '\" translation');
            missing++;
          }
        }
      }
      console.log('  Terms: ' + terms.length);
      console.log('  Languages: ' + langs.join(', '));
      if (missing > 0) {
        console.error('  ' + missing + ' missing translation(s)');
        process.exit(1);
      } else {
        console.log('  Status: All terms have translations for all languages');
      }
    " 2>&1)

    echo "$TERM_COUNT"
    if [[ $? -ne 0 ]]; then
      EXIT_CODE=1
    fi
  fi
fi

echo ""
echo "=== i18n Validation Complete ==="

if [[ $EXIT_CODE -ne 0 ]]; then
  echo "  Result: Issues detected"
  if [[ -n "$STRICT" ]]; then
    exit 1
  fi
else
  echo "  Result: All checks passed"
fi

exit 0
