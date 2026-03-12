#!/bin/bash
# PostToolUse hook: auto-notify after `gh pr merge`
# Detects merge commands and logs the event for verify-app follow-up.
# Does NOT block — just signals that a merge happened so Claude can trigger verify.
#
# Instance guard: skips if too many Claude processes are running.

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
[ "$TOOL_NAME" != "Bash" ] && exit 0

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')
[ -z "$COMMAND" ] && exit 0

# Only trigger on gh pr merge commands
if ! echo "$COMMAND" | grep -qE '^gh\s+pr\s+merge'; then
  exit 0
fi

# Check tool result — only proceed if merge succeeded
TOOL_OUTPUT=$(echo "$INPUT" | jq -r '.tool_result.stdout // empty')
TOOL_ERROR=$(echo "$INPUT" | jq -r '.tool_result.stderr // empty')
EXIT_CODE=$(echo "$INPUT" | jq -r '.tool_result.exit_code // 0')

[ "$EXIT_CODE" != "0" ] && exit 0

# Instance guard
MAX_INSTANCES="${CLAUDE_MAX_HOOK_INSTANCES:-8}"
INSTANCE_COUNT=$(pgrep -fc "claude" 2>/dev/null || echo 0)
[ "$INSTANCE_COUNT" -gt "$MAX_INSTANCES" ] && exit 0

# Extract PR number from the command
PR_NUMBER=$(echo "$COMMAND" | grep -oE '[0-9]+' | head -1)
[ -z "$PR_NUMBER" ] && PR_NUMBER="unknown"

# Resolve log path
MEMORY_DIR="$HOME/.claude/projects/-Users-torpedo-hlfh-repos-stoa/memory"
LOG="${MEMORY_DIR}/operations.log"
[ ! -d "$MEMORY_DIR" ] && exit 0

# Log the merge event
echo "$(date +%Y-%m-%dT%H:%M) | PR-MERGED-HOOK | pr=$PR_NUMBER cmd=\"$(echo "$COMMAND" | cut -c 1-80)\"" >> "$LOG"

# Signal to Claude via stdout — this message appears as hook feedback
# Remind Claude to run post-merge verification
cat <<EOF
{"notification": "PR #$PR_NUMBER merged. Post-merge checklist: (1) verify CI on main, (2) check ArgoCD sync, (3) update memory.md + plan.md, (4) Linear MCP sync if CAB-XXXX ticket."}
EOF

exit 0
