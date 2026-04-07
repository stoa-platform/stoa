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
# SECURITY (CAB-2005): Parse compound commands to prevent bypass via &&, ||, ;, |, $()
# Inspired by Claude Code leak CVE: permission checks must cover ALL subcommands,
# not just the first one. A command like "echo ok && rm -rf /" must be caught.
if [[ "$TOOL_NAME" == "Bash" ]]; then
  COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
  if [[ -z "$COMMAND" ]]; then
    exit 0
  fi

  # Split compound command into individual subcommands
  # Handles: &&, ||, ;, | (pipe), $(...), backticks, newlines
  # Strip subshell wrappers and split on shell operators
  SUBCOMMANDS=$(echo "$COMMAND" | \
    sed 's/\$([^)]*)//g' | \
    sed 's/`[^`]*`//g' | \
    tr '\n' ';' | \
    sed 's/&&/;/g; s/||/;/g; s/|/;/g' | \
    tr ';' '\n' | \
    sed 's/^[[:space:]]*//' | \
    grep -v '^$')

  # Also extract commands from $() and backtick subshells
  SUBSHELL_CMDS=$(echo "$COMMAND" | \
    grep -oE '\$\([^)]+\)' | \
    sed 's/^\$(\(.*\))$/\1/' || true)
  BACKTICK_CMDS=$(echo "$COMMAND" | \
    grep -oE '`[^`]+`' | \
    sed 's/^`\(.*\)`$/\1/' || true)

  ALL_CMDS=$(printf '%s\n%s\n%s' "$SUBCOMMANDS" "$SUBSHELL_CMDS" "$BACKTICK_CMDS" | grep -v '^$')

  # Count subcommands — warn if excessive (mirrors Claude Code 50-limit discovery)
  SUBCMD_COUNT=$(echo "$ALL_CMDS" | wc -l | tr -d ' ')
  if [[ "$SUBCMD_COUNT" -gt 50 ]]; then
    echo "BLOCKED by instance:${STOA_INSTANCE} — compound command has ${SUBCMD_COUNT} subcommands (limit: 50). Split into smaller commands." >&2
    exit 2
  fi

  # Check EACH subcommand against deny patterns
  while IFS= read -r pattern; do
    [[ -z "$pattern" ]] && continue
    inner=$(echo "$pattern" | sed -n 's/^Bash(\(.*\))/\1/p')
    cmd_prefix=$(echo "$inner" | sed 's/[[:space:]:]*\*$//')
    if [[ -n "$cmd_prefix" ]]; then
      while IFS= read -r subcmd; do
        [[ -z "$subcmd" ]] && continue
        # Trim leading whitespace from subcmd
        subcmd_trimmed=$(echo "$subcmd" | sed 's/^[[:space:]]*//')
        if [[ "$subcmd_trimmed" == "$cmd_prefix"* || "$subcmd_trimmed" == *" $cmd_prefix"* ]]; then
          echo "BLOCKED by instance:${STOA_INSTANCE} — Bash subcommand '${cmd_prefix}...' detected in compound command. Not allowed for this instance." >&2
          exit 2
        fi
      done <<< "$ALL_CMDS"
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
