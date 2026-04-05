#!/bin/bash
# PreToolUse hook: run quality gates BEFORE git push
# Detects which components changed vs main, runs the matching checks.
# Exit 0 = allow push, Exit 2 = block with message
#
# Kill switch: DISABLE_PRE_PUSH_GATE=1
# Skip for specific push: SKIP_QUALITY_GATE=1 git push ...

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

# Docs-only changes skip quality gates
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
  run_check "api:ruff" "cd $REPO_ROOT/control-plane-api && ruff check ."
  run_check "api:black" "cd $REPO_ROOT/control-plane-api && black --check ."
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
exit 0
