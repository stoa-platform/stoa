#!/bin/bash
# Stop hook: pause active sessions and run cleanup on session end.
#
# On session end:
# 1. Find current ticket from git branch → mark as paused
# 2. Clean up stale sessions (>24h)
# 3. Print active sessions summary
#
# Requires: heg-state CLI installed (~/.local/bin/heg-state via setup.sh)
# Graceful degradation: no heg-state = silent skip, never blocks session exit.

# Locate heg-state: direct path first (hook subprocess lacks ~/.local/bin on PATH)
HEG_STATE=""
if [ -x "${HOME}/.local/bin/heg-state" ]; then
  HEG_STATE="${HOME}/.local/bin/heg-state"
elif command -v heg-state &>/dev/null; then
  HEG_STATE="heg-state"
elif [ -n "$CLAUDE_PROJECT_DIR" ] && [ -f "${CLAUDE_PROJECT_DIR}/hegemon/tools/state/heg_state.py" ]; then
  HEG_STATE="python3 ${CLAUDE_PROJECT_DIR}/hegemon/tools/state/heg_state.py"
fi
[ -z "$HEG_STATE" ] && exit 0

# Check state.db exists (setup was run)
[ ! -f "${HOME}/.hegemon/state.db" ] && exit 0

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$PROJECT_DIR" 2>/dev/null || exit 0

# Extract ticket from current branch
BRANCH=$(git branch --show-current 2>/dev/null)
TICKET=""
if [ -n "$BRANCH" ]; then
  TICKET=$(echo "$BRANCH" | grep -oiE 'cab-[0-9]+' | head -1 | tr '[:lower:]' '[:upper:]')
fi

# Pause current ticket session (if active and not already done/merged)
if [ -n "$TICKET" ]; then
  # Check current step — don't pause if already done or merged
  CURRENT_STEP=$($HEG_STATE ls 2>/dev/null | grep "$TICKET" | awk '{print $4}')
  case "$CURRENT_STEP" in
    done|merged|cd-verified)
      ;; # Already complete, don't override with pause
    "")
      ;; # No active session for this ticket
    *)
      $HEG_STATE pause "$TICKET" --reason "session-end" >/dev/null 2>&1 || true
      ;;
  esac
fi

# Cleanup stale sessions (>24h) — best-effort hygiene
$HEG_STATE cleanup --stale 24h >/dev/null 2>&1 || true

# Print summary of remaining active sessions (informational)
ACTIVE=$($HEG_STATE ls --mine 2>/dev/null)
if [ -n "$ACTIVE" ] && ! echo "$ACTIVE" | grep -q "No active sessions"; then
  echo ""
  echo "--- HEGEMON State Store ---"
  echo "$ACTIVE"
  echo "---------------------------"
fi

exit 0
