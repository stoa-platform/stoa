#!/bin/bash
# PreToolUse hook: run quality gates BEFORE git push
# Detects which components changed vs main, runs the matching checks.
# Exit 0 = allow push, Exit 2 = block with message
#
# Kill switch: DISABLE_PRE_PUSH_GATE=1
# Skip for specific push: SKIP_QUALITY_GATE=1 git push ...
# Council S3 kill-switch: DISABLE_COUNCIL_GATE=1 (skip council-review.sh only)
# Council S3 threshold: COUNCIL_MIN_DIFF_LINES=20 (below = CI-only)

set -euo pipefail

[ "${DISABLE_PRE_PUSH_GATE:-}" = "1" ] && exit 0

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
[ "$TOOL_NAME" != "Bash" ] && exit 0

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')
[ -z "$COMMAND" ] && exit 0

# Only trigger on git push commands (not force push — that's already blocked)
if ! echo "$COMMAND" | grep -qE '^\s*git\s+push\b'; then
  exit 0
fi

# Skip if env flag set (for re-push after fix)
if echo "$COMMAND" | grep -q "SKIP_QUALITY_GATE"; then
  exit 0
fi

# Instance guard: skip if too many Claude processes
MAX_INSTANCES="${CLAUDE_MAX_HOOK_INSTANCES:-8}"
INSTANCE_COUNT=$(pgrep -fc "claude" 2>/dev/null || echo 0)
[ "$INSTANCE_COUNT" -gt "$MAX_INSTANCES" ] && exit 0

# --- Detect changed components vs main ---
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "")
[ -z "$REPO_ROOT" ] && exit 0
cd "$REPO_ROOT"

MERGE_BASE=$(git merge-base HEAD origin/main 2>/dev/null || echo "HEAD~1")
CHANGED_FILES=$(git diff --name-only "$MERGE_BASE"...HEAD 2>/dev/null || git diff --name-only HEAD~1 HEAD 2>/dev/null || echo "")
[ -z "$CHANGED_FILES" ] && exit 0

# Classify changes
HAS_PYTHON_API=false
HAS_CONSOLE=false
HAS_PORTAL=false
HAS_GATEWAY=false
HAS_E2E=false
ONLY_DOCS=true

while IFS= read -r f; do
  case "$f" in
    control-plane-api/*) HAS_PYTHON_API=true; ONLY_DOCS=false ;;
    control-plane-ui/*) HAS_CONSOLE=true; ONLY_DOCS=false ;;
    portal/*) HAS_PORTAL=true; ONLY_DOCS=false ;;
    stoa-gateway/*) HAS_GATEWAY=true; ONLY_DOCS=false ;;
    e2e/*) HAS_E2E=true; ONLY_DOCS=false ;;
    *.md|.claude/*|docs/*) ;; # docs-only, keep ONLY_DOCS=true
    *) ONLY_DOCS=false ;;
  esac
done <<< "$CHANGED_FILES"

# --- OpSec scan (ALWAYS runs, even docs-only — sensitive content can be in .md) ---
if [ -x "$REPO_ROOT/scripts/opsec-scan.sh" ] && [ "${DISABLE_OPSEC_SCAN:-}" != "1" ]; then
  echo "⏳ [opsec] scanning for sensitive content..." >&2
  if ! "$REPO_ROOT/scripts/opsec-scan.sh" 2>&1 >&2; then
    echo "" >&2
    echo "🚫 OpSec scan BLOCKED push — fix findings above" >&2
    echo "Kill switch: DISABLE_OPSEC_SCAN=1" >&2
    exit 2
  fi
  echo "✅ [opsec] clean" >&2
fi

# Docs-only changes skip quality gates (but NOT opsec — already ran above)
if [ "$ONLY_DOCS" = "true" ]; then
  exit 0
fi

# --- Run quality gates ---
FAILURES=""
CHECKS_RUN=0

run_check() {
  local label="$1"
  shift
  CHECKS_RUN=$((CHECKS_RUN + 1))
  echo "⏳ [$label] running..." >&2
  if eval "$@" >/dev/null 2>&1; then
    echo "✅ [$label] passed" >&2
  else
    echo "❌ [$label] FAILED" >&2
    FAILURES="${FAILURES}\n  - $label"
  fi
}

# Python (control-plane-api)
if [ "$HAS_PYTHON_API" = "true" ]; then
  # Scope: src/ only — matches CI exactly (reusable-python-ci.yml runs ruff check src/).
  # tests/ has pre-existing violations out of CI scope; linting them here blocked pushes
  # on unrelated legacy debt (CAB-2053 Phase 2 bug class #7).
  # black removed: CI does NOT run black (reusable-python-ci.yml only runs ruff + mypy).
  # src/ has 83 pre-existing black violations that CI tolerates — hook should not be
  # stricter than CI.
  run_check "api:ruff" "cd $REPO_ROOT/control-plane-api && ruff check src/"
fi

# Console (control-plane-ui)
if [ "$HAS_CONSOLE" = "true" ]; then
  run_check "ui:lint" "cd $REPO_ROOT/control-plane-ui && npm run lint 2>&1"
  run_check "ui:format" "cd $REPO_ROOT/control-plane-ui && npm run format:check 2>&1"
  run_check "ui:tsc" "cd $REPO_ROOT/control-plane-ui && npx tsc -p tsconfig.app.json --noEmit 2>&1"
fi

# Portal
if [ "$HAS_PORTAL" = "true" ]; then
  run_check "portal:lint" "cd $REPO_ROOT/portal && npm run lint 2>&1"
  run_check "portal:format" "cd $REPO_ROOT/portal && npm run format:check 2>&1"
  run_check "portal:tsc" "cd $REPO_ROOT/portal && npx tsc -p tsconfig.app.json --noEmit 2>&1"
fi

# Rust (stoa-gateway)
if [ "$HAS_GATEWAY" = "true" ]; then
  run_check "gateway:fmt" "cd $REPO_ROOT/stoa-gateway && cargo fmt --check 2>&1"
  run_check "gateway:clippy" "cd $REPO_ROOT/stoa-gateway && RUSTFLAGS=-Dwarnings cargo clippy --all-targets --all-features -- -D warnings 2>&1"
fi

# E2E / UI: axe-core smoke (only if Console changed, fast ~10s)
if [ "$HAS_CONSOLE" = "true" ] || [ "$HAS_E2E" = "true" ]; then
  if [ -f "$REPO_ROOT/e2e/smoke-mock/a11y-axe.smoke.ts" ]; then
    run_check "a11y:axe" "cd $REPO_ROOT/e2e && npx playwright test --config=smoke-mock/playwright.config.ts a11y-axe --reporter=null 2>&1"
  fi
fi

# --- Report ---
if [ -n "$FAILURES" ]; then
  echo "" >&2
  echo "🚫 Pre-push quality gate FAILED ($CHECKS_RUN checks run):" >&2
  echo -e "$FAILURES" >&2
  echo "" >&2
  echo "Fix the issues above, then push again." >&2
  echo "To bypass (emergency): SKIP_QUALITY_GATE=1 in the push command" >&2
  exit 2
fi

if [ "$CHECKS_RUN" -gt 0 ]; then
  echo "✅ Pre-push quality gate passed ($CHECKS_RUN checks)" >&2
fi

# --- Council Stage 3 (CAB-2046 / CAB-2048) ---
# Conditional on diff size: small diffs go through CI (council-gate.yml) only.
COUNCIL_HISTORY_FILE="${COUNCIL_HISTORY_FILE:-${REPO_ROOT}/council-history.jsonl}"
COUNCIL_MIN_DIFF_LINES="${COUNCIL_MIN_DIFF_LINES:-20}"
COUNCIL_DIFF_LINES=$(git diff --numstat "${MERGE_BASE}" HEAD 2>/dev/null \
  | awk '{sum+=$1+$2} END {print sum+0}')

if [ "${DISABLE_COUNCIL_GATE:-}" = "1" ]; then
  echo "⏭️  Council S3 BYPASSED (DISABLE_COUNCIL_GATE=1)" >&2
  printf '{"timestamp":"%s","status":"BYPASSED","reason":"local_kill_switch","diff_lines":%s}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$COUNCIL_DIFF_LINES" >> "$COUNCIL_HISTORY_FILE"
elif [ "$COUNCIL_DIFF_LINES" -lt "$COUNCIL_MIN_DIFF_LINES" ]; then
  echo "⏭️  Council S3 SKIPPED (diff $COUNCIL_DIFF_LINES lines < $COUNCIL_MIN_DIFF_LINES — CI-only)" >&2
elif [ ! -x "$REPO_ROOT/scripts/council-review.sh" ]; then
  echo "⏭️  Council S3 SKIPPED (scripts/council-review.sh missing or not executable)" >&2
else
  echo "⏳ [council:s3] running ($COUNCIL_DIFF_LINES diff lines)..." >&2
  if ! "$REPO_ROOT/scripts/council-review.sh" --diff "${MERGE_BASE}..HEAD" 1>&2; then
    echo "" >&2
    echo "🚫 Council S3 REWORK — address blockers above, then push again" >&2
    echo "To bypass (emergency): DISABLE_COUNCIL_GATE=1 git push ..." >&2
    exit 2
  fi
  echo "✅ [council:s3] APPROVED" >&2
fi

exit 0
