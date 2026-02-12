#!/bin/bash
# PostToolUse hook: auto-log significant Bash operations to operations.log
# Skips read-only commands (ls, cat, grep, git status, etc.)
# Appends one-line entries for write operations (git push, kubectl apply, etc.)

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
[ "$TOOL_NAME" != "Bash" ] && exit 0

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')
[ -z "$COMMAND" ] && exit 0

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

# Log significant operations
LOG="$HOME/.claude/projects/-Users-torpedo-CabIngenierie-Dropbox-Christophe-ABOULICAM--PERSO-stoa-platform-stoa/memory/operations.log"
CMD_SHORT=$(echo "$COMMAND" | head -1 | cut -c 1-100)
echo "$(date +%Y-%m-%dT%H:%M) | BASH-EXEC | cmd=\"$CMD_SHORT\"" >> "$LOG"
exit 0
