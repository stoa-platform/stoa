#!/bin/bash
# PostToolUse hook: track Edit failures per file to detect context rot.
#
# When the model patches the same file ≥2 times and keeps failing, the context
# accumulates failed attempts, wrong assumptions, and retry noise. Research
# (Liu et al. "Lost in the Middle", Databricks Mosaic) shows this degrades
# performance. This hook injects a systemMessage telling the model to switch
# to Write (rewrite) or delegate to a subagent.
#
# State: .claude/state/edit-attempts.json (session-scoped, reset on /clear via
# the PostCompact hook and on SessionStart).
#
# Thresholds:
#   - 2 consecutive Edit failures same file → "switch to Write or subagent"
#   - 5 Edit calls same file in session (even successful) → "consider rewrite"
#
# Exit 0 always (advisory, never blocks).

set -u

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')

# Only track Edit (not Write — Write is already the rewrite path)
[ "$TOOL_NAME" != "Edit" ] && exit 0

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
[ -z "$FILE_PATH" ] && exit 0

# Detect failure: tool_response has error indicator
# Claude Code marks failed tool calls via .tool_response.is_error or .error fields
IS_ERROR=$(echo "$INPUT" | jq -r '
  if (.tool_response.is_error // false) then "true"
  elif (.tool_response.error // "") != "" then "true"
  elif (.tool_response | type) == "string" and (.tool_response | test("Error|error|failed|not found|does not match"; "i")) then "true"
  else "false"
  end
' 2>/dev/null)

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
STATE_DIR="$PROJECT_DIR/.claude/state"
STATE_FILE="$STATE_DIR/edit-attempts.json"

mkdir -p "$STATE_DIR" 2>/dev/null || exit 0
[ ! -f "$STATE_FILE" ] && echo '{}' > "$STATE_FILE"

# Use a short hash of the file path as key (avoids JSON escaping issues)
FILE_KEY=$(echo -n "$FILE_PATH" | shasum -a 1 | awk '{print $1}' | cut -c1-16)

# Atomic update via jq — increment counters
TMP=$(mktemp)
jq --arg key "$FILE_KEY" \
   --arg path "$FILE_PATH" \
   --arg err "$IS_ERROR" \
   '
   .[$key] = {
     path: $path,
     total: ((.[$key].total // 0) + 1),
     consecutive_fails: (
       if $err == "true" then ((.[$key].consecutive_fails // 0) + 1)
       else 0
       end
     ),
     last_error: ($err == "true")
   }
   ' "$STATE_FILE" > "$TMP" 2>/dev/null && mv "$TMP" "$STATE_FILE" || { rm -f "$TMP"; exit 0; }

# Read back to decide if we warn
FAILS=$(jq -r --arg key "$FILE_KEY" '.[$key].consecutive_fails // 0' "$STATE_FILE" 2>/dev/null)
TOTAL=$(jq -r --arg key "$FILE_KEY" '.[$key].total // 0' "$STATE_FILE" 2>/dev/null)

BASENAME=$(basename "$FILE_PATH")

if [ "${FAILS:-0}" -ge 2 ]; then
  MSG="Edit failed ${FAILS}× consecutively on ${BASENAME}. Context rot risk: STOP patching. Read the current file, then use Write (full rewrite) or delegate to a subagent with fresh context. See feedback_rewrite_after_fail.md."
  echo "$MSG" | jq -Rs '{"systemMessage": .}'
elif [ "${TOTAL:-0}" -ge 5 ]; then
  MSG="Edit called ${TOTAL}× on ${BASENAME} this session. Consider switching to Write (rewrite) or subagent — accumulated patches pollute context and bias future decisions."
  echo "$MSG" | jq -Rs '{"systemMessage": .}'
else
  echo '{}'
fi

exit 0
