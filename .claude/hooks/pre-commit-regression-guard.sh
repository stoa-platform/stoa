#!/usr/bin/env bash
# Pre-commit regression guard — blocks fix() commits without regression tests.
# Runs as a PreToolUse hook on Bash commands containing "git commit".
#
# Mirrors the CI regression-guard.yml logic locally so Claude catches it
# before pushing, not after CI fails remotely.

set -euo pipefail

# Only intercept git commit commands
TOOL_INPUT="${TOOL_INPUT:-}"
if [[ "$TOOL_INPUT" != *"git commit"* ]]; then
  exit 0
fi

# Get the current branch name
BRANCH=$(git branch --show-current 2>/dev/null || echo "")
if [[ -z "$BRANCH" ]]; then
  exit 0
fi

# Only enforce on fix/ branches
if [[ "$BRANCH" != fix/* && "$BRANCH" != hotfix/* ]]; then
  exit 0
fi

# Check if skip-regression label would apply (check for label file marker)
if [[ -f ".skip-regression" ]]; then
  exit 0
fi

# Get staged files
STAGED=$(git diff --cached --name-only 2>/dev/null || echo "")
if [[ -z "$STAGED" ]]; then
  exit 0
fi

# Check for regression test patterns in staged files
HAS_REGRESSION=false

# Python: test_regression_* files
if echo "$STAGED" | grep -qE "test_regression_"; then
  HAS_REGRESSION=true
fi

# TypeScript: regression/*.test.ts(x) files
if echo "$STAGED" | grep -qE "regression/.*\.test\.tsx?"; then
  HAS_REGRESSION=true
fi

# Rust: check for fn regression_ in staged .rs files
if echo "$STAGED" | grep -qE "\.rs$"; then
  for f in $(echo "$STAGED" | grep -E "\.rs$"); do
    if git diff --cached -- "$f" 2>/dev/null | grep -qE "fn regression_"; then
      HAS_REGRESSION=true
      break
    fi
  done
fi

# E2E: @regression tag in .feature files
if echo "$STAGED" | grep -qE "\.feature$"; then
  for f in $(echo "$STAGED" | grep -E "\.feature$"); do
    if git diff --cached -- "$f" 2>/dev/null | grep -qE "@regression"; then
      HAS_REGRESSION=true
      break
    fi
  done
fi

# Docs-only changes auto-pass (same as CI guard)
NON_DOC_FILES=$(echo "$STAGED" | grep -vE '\.(md|yml|yaml|json|toml)$' | grep -vE '\.claude/|\.github/' || true)
if [[ -z "$NON_DOC_FILES" ]]; then
  exit 0
fi

if [[ "$HAS_REGRESSION" == "false" ]]; then
  echo "REGRESSION GUARD: fix() branch detected ($BRANCH) but no regression test found in staged files."
  echo ""
  echo "Required patterns (at least one):"
  echo "  Python:     test_regression_*.py"
  echo "  TypeScript: src/__tests__/regression/*.test.ts(x)"
  echo "  Rust:       fn regression_* in .rs diff"
  echo "  E2E:        @regression tag in .feature diff"
  echo ""
  echo "Add a regression test that reproduces the bug, then commit again."
  exit 2
fi
