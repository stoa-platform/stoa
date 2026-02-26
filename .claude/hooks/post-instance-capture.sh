#!/bin/bash
# PostToolUse hook: Capture tool usage per instance for progressive allowlist.
#
# Appends a JSONL entry for every tool invocation when STOA_INSTANCE is set.
# Data: timestamp, tool name, file path (if applicable).
# Output: .claude/instances/<role>-captured.jsonl (gitignored, machine-local).
#
# After N sessions, run analyze-instance-usage.sh to generate allowlist proposals.

# No instance set → skip silently
[[ -z "${STOA_INSTANCE:-}" ]] && exit 0

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
ROLE="$STOA_INSTANCE"
CAPTURE_FILE="$PROJECT_DIR/.claude/instances/${ROLE}-captured.jsonl"

TOOL_NAME="${CLAUDE_TOOL_NAME:-}"
[[ -z "$TOOL_NAME" ]] && exit 0

# Read tool input from stdin
INPUT=$(cat)

# Extract file path from tool input
FILE_PATH=""
case "$TOOL_NAME" in
  Edit|Write|Read|Glob)
    FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // empty' 2>/dev/null)
    # Make relative to project
    FILE_PATH="${FILE_PATH#"$PROJECT_DIR"}"
    ;;
  Bash)
    # Capture first 80 chars of command
    FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null | head -c 80)
    ;;
  Grep)
    FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.path // empty' 2>/dev/null)
    FILE_PATH="${FILE_PATH#"$PROJECT_DIR"}"
    ;;
esac

# Append capture entry (fast, no locks needed for append)
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "{\"ts\":\"$TS\",\"tool\":\"$TOOL_NAME\",\"path\":\"$FILE_PATH\"}" >> "$CAPTURE_FILE"

exit 0
