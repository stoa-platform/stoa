#!/bin/bash
# PostToolUse hook: auto-track lifecycle events in HEGEMON State Store.
# Detects git checkout -b, gh pr create, gh pr merge, git push → calls heg-state.
#
# Fires on every Bash tool call. Fast early-exit (<1ms) for non-lifecycle commands.
# Requires: heg-state CLI installed (~/.local/bin/heg-state via setup.sh)
# Graceful degradation: no heg-state = silent skip, never blocks Claude.

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)
[ "$TOOL_NAME" != "Bash" ] && exit 0

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
[ -z "$COMMAND" ] && exit 0

# Fast early exit for non-lifecycle commands (99% of calls)
case "$COMMAND" in
  git\ checkout\ -b*|gh\ pr\ create*|gh\ pr\ merge*|git\ push*)
    ;; # lifecycle event — continue
  *)
    exit 0 ;;
esac

# Locate heg-state: direct path first (hook subprocess lacks ~/.local/bin on PATH)
HEG_STATE=""
if [ -x "${HOME}/.local/bin/heg-state" ]; then
  HEG_STATE="${HOME}/.local/bin/heg-state"
elif command -v heg-state &>/dev/null; then
  HEG_STATE="heg-state"
elif [ -f "${CLAUDE_PROJECT_DIR}/hegemon/tools/state/heg_state.py" ]; then
  HEG_STATE="python3 ${CLAUDE_PROJECT_DIR}/hegemon/tools/state/heg_state.py"
fi
[ -z "$HEG_STATE" ] && exit 0

# Check state.db exists (setup was run)
[ ! -f "${HOME}/.hegemon/state.db" ] && exit 0

# Instance guard: skip if too many Claude processes (prevents hook storms)
MAX_INSTANCES="${CLAUDE_MAX_HOOK_INSTANCES:-8}"
INSTANCE_COUNT=$(pgrep -fc "claude" 2>/dev/null || echo 0)
[ "$INSTANCE_COUNT" -gt "$MAX_INSTANCES" ] && exit 0

# Get project dir for branch detection
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$PROJECT_DIR" 2>/dev/null || exit 0

# Extract ticket ID from branch name (CAB-XXXX pattern)
extract_ticket() {
  local branch="${1:-$(git branch --show-current 2>/dev/null)}"
  echo "$branch" | grep -oiE 'cab-[0-9]+' | head -1 | tr '[:lower:]' '[:upper:]'
}

# Get current role from STOA_INSTANCE or default
ROLE="${STOA_INSTANCE:-interactive}"

# Parse tool output (for PR number extraction)
OUTPUT=$(echo "$INPUT" | jq -r '.tool_output.stdout // .tool_output // empty' 2>/dev/null)

# ── Event Detection ────────────────────────────────────────────

# 1. Branch creation: git checkout -b feat/cab-1350-description
if [[ "$COMMAND" =~ ^git\ checkout\ -b\ (.+) ]]; then
  BRANCH="${BASH_REMATCH[1]}"
  # Strip trailing flags or chained commands
  BRANCH=$(echo "$BRANCH" | awk '{print $1}')
  TICKET=$(extract_ticket "$BRANCH")
  if [ -n "$TICKET" ]; then
    $HEG_STATE start --ticket "$TICKET" --branch "$BRANCH" --role "$ROLE" >/dev/null 2>&1 || true
  fi
  exit 0
fi

# 2. PR creation: gh pr create ...
if [[ "$COMMAND" =~ ^gh\ pr\ create ]]; then
  TICKET=$(extract_ticket)
  [ -z "$TICKET" ] && exit 0

  # Extract PR number from output (URL pattern: /pull/NNN)
  PR_NUM=""
  if [ -n "$OUTPUT" ]; then
    PR_NUM=$(echo "$OUTPUT" | grep -oE '/pull/[0-9]+' | grep -oE '[0-9]+' | head -1)
  fi
  # Fallback: try gh pr view on current branch
  if [ -z "$PR_NUM" ]; then
    PR_NUM=$(gh pr view --json number -q '.number' 2>/dev/null || true)
  fi

  if [ -n "$PR_NUM" ]; then
    $HEG_STATE step "$TICKET" pr-created --pr "$PR_NUM" >/dev/null 2>&1 || true
  else
    $HEG_STATE step "$TICKET" pr-created >/dev/null 2>&1 || true
  fi
  exit 0
fi

# 3. PR merge: gh pr merge ...
if [[ "$COMMAND" =~ ^gh\ pr\ merge ]]; then
  TICKET=$(extract_ticket)
  [ -z "$TICKET" ] && exit 0

  # Extract PR number from the merge command (gh pr merge NNN ...)
  PR_NUM=$(echo "$COMMAND" | grep -oE 'gh pr merge [0-9]+' | grep -oE '[0-9]+' | head -1)

  if [ -n "$PR_NUM" ]; then
    $HEG_STATE step "$TICKET" merged --pr "$PR_NUM" >/dev/null 2>&1 || true
  else
    $HEG_STATE step "$TICKET" merged >/dev/null 2>&1 || true
  fi
  exit 0
fi

# 4. Git push: first push on a ticket branch = coding milestone
if [[ "$COMMAND" =~ ^git\ push ]]; then
  TICKET=$(extract_ticket)
  [ -z "$TICKET" ] && exit 0

  $HEG_STATE step "$TICKET" coding >/dev/null 2>&1 || true
  exit 0
fi

exit 0
