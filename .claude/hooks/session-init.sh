#!/bin/bash
# SessionStart hook: generate session brief from HEGEMON state store.
# Replaces full memory.md + plan.md loading with compact context (~500 tokens).
# Falls back gracefully if state.db doesn't exist or heg-state is unavailable.

set -euo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
BRIEF_FILE="${PROJECT_DIR}/.claude/session-brief.json"
STATE_DB="${HOME}/.hegemon/state.db"

# Resolve heg-state CLI
HEG_STATE="${HOME}/.local/bin/heg-state"
if [ ! -x "$HEG_STATE" ]; then
    HEG_STATE="python3 ${PROJECT_DIR}/hegemon/tools/state/heg_state.py"
fi

# Sync tickets from Linear + generate brief from HEGEMON state store (0 tokens — pure bash/python)
if [ -f "$STATE_DB" ]; then
    # Rate-limit: only sync if brief is stale (>5 min) or missing
    if [ ! -f "$BRIEF_FILE" ] || [ -n "$(find "$BRIEF_FILE" -mmin +5 2>/dev/null)" ]; then
        $HEG_STATE ticket-sync --from-linear 2>/dev/null || true
        $HEG_STATE cleanup --stale 2h 2>/dev/null || true
    fi
    $HEG_STATE brief --project stoa > "$BRIEF_FILE" 2>/dev/null || true
fi

# Set instance ID via env file (persists for entire session)
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
    INSTANCE_ID="t$(( $(date +%s) % 100000 ))-$(openssl rand -hex 2)"
    echo "STOA_INSTANCE_ID=${INSTANCE_ID}" >> "$CLAUDE_ENV_FILE"
fi

exit 0
