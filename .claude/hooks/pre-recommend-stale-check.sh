#!/bin/bash
# PreToolUse hook (Agent tool): Verify memory-referenced paths exist before delegation.
#
# CAB-2005: Inspired by Claude Code's "Strict Write Discipline" pattern revealed
# in the March 2026 source leak. The agent treats its own memory as a "hint" and
# verifies facts against the codebase before acting.
#
# This hook reads MEMORY.md, extracts file paths and function names, and checks
# if they still exist. If stale references are found, it warns via systemMessage.
#
# Trigger: PostToolUse on Read (when reading memory files)
# Exit 0 always (advisory, never blocks)

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
MEMORY_DIR="$HOME/.claude/projects/-Users-torpedo-hlfh-repos-stoa/memory"
MEMORY_INDEX="$MEMORY_DIR/MEMORY.md"

# Only run when reading memory files
INPUT=$(cat)
TOOL_NAME="${CLAUDE_TOOL_NAME:-}"

# Only check after reading memory-related files
if [[ "$TOOL_NAME" != "Read" ]]; then
  exit 0
fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

# Only trigger on memory files
case "$FILE_PATH" in
  *memory/MEMORY.md|*memory/*.md|*/memory.md)
    ;;
  *)
    exit 0
    ;;
esac

# Extract file paths mentioned in memory (patterns like `path/to/file.ext` or path/to/file.ext:L42)
STALE_PATHS=""
while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  # Strip line number suffix
  clean_path=$(echo "$path" | sed 's/:L[0-9]*$//')
  # Skip URLs, anchors, markdown links
  [[ "$clean_path" == http* ]] && continue
  [[ "$clean_path" == "#"* ]] && continue
  [[ "$clean_path" == "["* ]] && continue
  # Skip if it's just a filename without path separator
  [[ "$clean_path" != *"/"* ]] && continue
  # Check if file exists (relative to project)
  if [[ ! -f "$PROJECT_DIR/$clean_path" && ! -d "$PROJECT_DIR/$clean_path" ]]; then
    STALE_PATHS="${STALE_PATHS}  - ${clean_path}\n"
  fi
done < <(grep -oE '`[a-zA-Z0-9_./-]+\.[a-z]{1,5}(:[L0-9]+)?`' "$FILE_PATH" 2>/dev/null | tr -d '`' | sort -u)

# Report stale references as advisory
if [[ -n "$STALE_PATHS" ]]; then
  MSG=$(printf 'Memory stale-check warning: The following paths referenced in memory no longer exist in the codebase. Verify before recommending:\n%b' "$STALE_PATHS")
  echo "$MSG" | jq -Rs '{"systemMessage": .}'
else
  echo '{}'
fi

exit 0
