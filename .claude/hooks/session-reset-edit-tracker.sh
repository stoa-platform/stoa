#!/bin/bash
# SessionStart + PostCompact hook: reset the edit-attempts state.
# Fresh session or post-/compact = clean slate for the failure counter.

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
STATE_FILE="$PROJECT_DIR/.claude/state/edit-attempts.json"

[ -f "$STATE_FILE" ] && echo '{}' > "$STATE_FILE"
exit 0
