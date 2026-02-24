#!/bin/bash
# PostToolUse hook: auto-log significant Bash operations to operations.log
# Skips read-only commands (ls, cat, grep, git status, etc.)
# Appends one-line entries for write operations (git push, kubectl apply, etc.)
#
# Instance guard: skips if too many Claude processes are running (prevents hook storms).
# Configure via CLAUDE_MAX_HOOK_INSTANCES env var (default: 8).

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
[ "$TOOL_NAME" != "Bash" ] && exit 0

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')
[ -z "$COMMAND" ] && exit 0

# Instance guard: skip logging if too many concurrent Claude processes
MAX_INSTANCES="${CLAUDE_MAX_HOOK_INSTANCES:-8}"
INSTANCE_COUNT=$(pgrep -fc "claude" 2>/dev/null || echo 0)
[ "$INSTANCE_COUNT" -gt "$MAX_INSTANCES" ] && exit 0

# Skip read-only commands — no need to log these
FIRST_CMD=$(echo "$COMMAND" | head -1 | awk '{print $1}')
case "$FIRST_CMD" in
  ls|cat|head|tail|grep|rg|echo|pwd|which|find|wc|file|stat|diff|tree|type|man|help)
    exit 0 ;;
esac

# Skip git/kubectl/gh read-only subcommands
if [[ "$COMMAND" =~ ^git\ (status|log|diff|show|branch|remote|tag|stash\ list) ]]; then
  exit 0
fi
if [[ "$COMMAND" =~ ^kubectl\ (get|describe|logs|top|explain) ]]; then
  exit 0
fi
if [[ "$COMMAND" =~ ^gh\ (pr\ view|pr\ checks|pr\ list|run\ list|run\ view|issue\ view|api\ repos) ]]; then
  exit 0
fi

# Resolve log path using CLAUDE_PROJECT_DIR (portable, no hardcoded paths)
MEMORY_DIR="$HOME/.claude/projects/-Users-torpedo-hlfh-repos-stoa/memory"
[ -n "$CLAUDE_PROJECT_DIR" ] && MEMORY_DIR="$(echo "$CLAUDE_PROJECT_DIR" | sed 's|/Users/|/-Users-|;s|/|-|g;s|^|'"$HOME"'/.claude/projects/|')/memory"

LOG="${MEMORY_DIR}/operations.log"
[ ! -d "$MEMORY_DIR" ] && exit 0

CMD_SHORT=$(echo "$COMMAND" | head -1 | cut -c 1-100)
echo "$(date +%Y-%m-%dT%H:%M) | BASH-EXEC | cmd=\"$CMD_SHORT\"" >> "$LOG"
exit 0
