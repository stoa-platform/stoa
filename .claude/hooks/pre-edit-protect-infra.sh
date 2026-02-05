#!/bin/bash
# Pre-edit hook: Block modifications to protected infrastructure paths
# without explicit user confirmation.
# Exit 0 = allow, Exit 2 = block with message

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)

if [ -z "$FILE_PATH" ]; then
  exit 0
fi

# Protected paths (production infrastructure)
PROTECTED_PATTERNS=(
  "terraform/environments/prod"
  "deploy/config/prod.env"
)

for pattern in "${PROTECTED_PATTERNS[@]}"; do
  if [[ "$FILE_PATH" == *"$pattern"* ]]; then
    echo "BLOCKED: $FILE_PATH is in a protected infrastructure path ($pattern). Requires explicit user confirmation." >&2
    exit 2
  fi
done

exit 0
