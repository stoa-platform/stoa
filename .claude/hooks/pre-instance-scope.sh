#!/bin/bash
# Pre-tool hook: Enforce per-instance file scope and command restrictions.
#
# Reads STOA_INSTANCE env var (backend, frontend, auth, mcp, qa).
# If set, loads deny rules from .claude/instances/<role>.json and blocks
# Edit/Write on denied paths + Bash commands matching deny patterns.
#
# Supports two modes via INSTANCE_MODE env var:
#   deny  (default) — blocks operations matching deny list
#   allow           — only permits operations matching allowlist
#
# Works for any Claude session:
#   export STOA_INSTANCE=backend && claude   # standalone
#   stoa-parallel                             # sets per-window
#
# Exit 0 = allow, Exit 2 = block

# No instance set → allow everything
if [[ -z "${STOA_INSTANCE:-}" ]]; then
  exit 0
fi

# Resolve paths
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
INSTANCE_FILE="$PROJECT_DIR/.claude/instances/${STOA_INSTANCE}.json"
ALLOWLIST_FILE="$PROJECT_DIR/.claude/instances/${STOA_INSTANCE}-allowlist.json"

# Mode: deny (default) or allow
MODE="${INSTANCE_MODE:-deny}"

if [[ ! -f "$INSTANCE_FILE" ]]; then
  exit 0
fi

# Read tool input from stdin
INPUT=$(cat)
TOOL_NAME="${CLAUDE_TOOL_NAME:-}"

# Fallback: extract tool name from JSON if env var not available
if [[ -z "$TOOL_NAME" ]]; then
  TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)
fi

if [[ -z "$TOOL_NAME" ]]; then
  exit 0
fi

# --- Edit/Write: check file_path against deny_paths ---
if [[ "$TOOL_NAME" == "Edit" || "$TOOL_NAME" == "Write" ]]; then
  FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
  if [[ -z "$FILE_PATH" ]]; then
    exit 0
  fi

  # Make path relative to project for matching
  REL_PATH="${FILE_PATH#"$PROJECT_DIR"}"

  # Read deny patterns for Edit/Write from instance file
  # Format: "Edit(/portal/**)" or "Write(/stoa-gateway/src/**)"
  while IFS= read -r pattern; do
    [[ -z "$pattern" ]] && continue
    # Extract path from pattern: "Edit(/portal/**)" → "/portal/"
    # Match both Edit and Write deny rules for either tool
    deny_path=$(echo "$pattern" | sed -n 's/^[^(]*(\/\(.*\)\*\*)/\/\1/p')
    if [[ -n "$deny_path" && "$REL_PATH" == "$deny_path"* ]]; then
      echo "BLOCKED by instance:${STOA_INSTANCE} — ${TOOL_NAME} on ${REL_PATH} is outside your scope. Denied path: ${deny_path}" >&2
      exit 2
    fi
  done < <(jq -r '.permissions.deny[]? // empty' "$INSTANCE_FILE" 2>/dev/null | grep -E '^(Edit|Write)\(')
fi

# --- Bash: check command against deny patterns ---
if [[ "$TOOL_NAME" == "Bash" ]]; then
  COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
  if [[ -z "$COMMAND" ]]; then
    exit 0
  fi

  # Read Bash deny patterns from instance file
  # Format: "Bash(rm -rf *)" or "Bash(npm:*)" or "Bash(sudo *)"
  while IFS= read -r pattern; do
    [[ -z "$pattern" ]] && continue
    # Extract inner: "Bash(npm:*)" → "npm:*", strip Bash() wrapper
    inner=$(echo "$pattern" | sed -n 's/^Bash(\(.*\))/\1/p')
    # Strip trailing :* or space-* to get the command prefix
    cmd_prefix=$(echo "$inner" | sed 's/[[:space:]:]*\*$//')
    if [[ -n "$cmd_prefix" ]]; then
      # Check if command starts with the denied prefix
      if [[ "$COMMAND" == "$cmd_prefix"* || "$COMMAND" == *" $cmd_prefix"* ]]; then
        echo "BLOCKED by instance:${STOA_INSTANCE} — Bash command '${cmd_prefix}...' is not allowed for this instance." >&2
        exit 2
      fi
    fi
  done < <(jq -r '.permissions.deny[]? // empty' "$INSTANCE_FILE" 2>/dev/null | grep '^Bash(')
fi

# --- Allowlist mode: only permit operations in the allowlist ---
if [[ "$MODE" == "allow" && -f "$ALLOWLIST_FILE" ]]; then
  if [[ "$TOOL_NAME" == "Edit" || "$TOOL_NAME" == "Write" ]]; then
    FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
    REL_PATH="${FILE_PATH#"$PROJECT_DIR"}"
    ALLOWED=false
    while IFS= read -r pattern; do
      [[ -z "$pattern" ]] && continue
      allow_path=$(echo "$pattern" | sed -n 's/^[^(]*(\/\(.*\)\*\*)/\/\1/p')
      if [[ -n "$allow_path" && "$REL_PATH" == "$allow_path"* ]]; then
        ALLOWED=true
        break
      fi
    done < <(jq -r '.permissions.allow[]? // empty' "$ALLOWLIST_FILE" 2>/dev/null | grep -E "^(Edit|Write)\(")
    if [[ "$ALLOWED" == "false" ]]; then
      echo "BLOCKED by allowlist:${STOA_INSTANCE} — ${TOOL_NAME} on ${REL_PATH} not in allowlist." >&2
      exit 2
    fi
  fi

  if [[ "$TOOL_NAME" == "Bash" ]]; then
    COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
    ALLOWED=false
    while IFS= read -r pattern; do
      [[ -z "$pattern" ]] && continue
      inner=$(echo "$pattern" | sed -n 's/^Bash(\(.*\))/\1/p')
      cmd_prefix=$(echo "$inner" | sed 's/[[:space:]:]*\*$//')
      if [[ -n "$cmd_prefix" && ("$COMMAND" == "$cmd_prefix"* || "$COMMAND" == *" $cmd_prefix"*) ]]; then
        ALLOWED=true
        break
      fi
    done < <(jq -r '.permissions.allow[]? // empty' "$ALLOWLIST_FILE" 2>/dev/null | grep '^Bash(')
    if [[ "$ALLOWED" == "false" ]]; then
      echo "BLOCKED by allowlist:${STOA_INSTANCE} — Bash command not in allowlist." >&2
      exit 2
    fi
  fi
fi

exit 0
