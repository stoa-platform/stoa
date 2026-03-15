#!/bin/bash
# PermissionRequest hook: Auto-approve safe tool patterns on Contabo workers.
# Only active when STOA_CONTABO_WORKER=1 is set (Contabo hegemon-agent.service).
#
# Reads JSON from stdin: { "tool_name": "Bash", "tool_input": {"command": "..."}, ... }
# Returns JSON: { "decision": "allow"|"deny"|"ask", "reason": "..." }
#
# Rollback: Remove hook entry from settings.json → falls back to manual approval.

[ "${STOA_CONTABO_WORKER:-}" != "1" ] && echo '{}' && exit 0

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Always allow read-only tools
case "$TOOL_NAME" in
  Read|Grep|Glob|WebSearch|WebFetch)
    echo '{"decision":"allow","reason":"read-only tool"}'
    exit 0
    ;;
esac

# Bash tool: pattern-based approval
if [ "$TOOL_NAME" = "Bash" ] && [ -n "$COMMAND" ]; then
  # Extract first word (command name)
  FIRST_WORD=$(echo "$COMMAND" | awk '{print $1}')

  # DENY list — dangerous commands (always block, never auto-approve)
  case "$COMMAND" in
    *"rm -rf /"*|*"rm -rf /*"*)
      echo '{"decision":"deny","reason":"destructive: recursive delete of root"}'
      exit 0
      ;;
    sudo\ *)
      echo '{"decision":"deny","reason":"blocked: sudo not allowed on workers"}'
      exit 0
      ;;
    *"--force"*push*|*push*"--force"*)
      echo '{"decision":"deny","reason":"blocked: force push requires human approval"}'
      exit 0
      ;;
    *"terraform destroy"*|*"kubectl delete namespace"*)
      echo '{"decision":"deny","reason":"blocked: destructive infra operation"}'
      exit 0
      ;;
  esac

  # ALLOW list — safe development commands
  case "$FIRST_WORD" in
    git|gh|cargo|rustup|npm|npx|node|python|python3|pip|pip3|pytest|ruff|black|mypy|alembic)
      echo '{"decision":"allow","reason":"safe dev tool: '"$FIRST_WORD"'"}'
      exit 0
      ;;
    curl|jq|cat|head|tail|ls|tree|find|grep|sed|awk|wc|sort|uniq|cut|tr|diff|test|true|false)
      echo '{"decision":"allow","reason":"safe read/utility: '"$FIRST_WORD"'"}'
      exit 0
      ;;
    mkdir|touch|cp|mv|rm|chmod|echo|printf|date|sleep|basename|dirname|realpath|pwd|cd|which|env)
      echo '{"decision":"allow","reason":"safe shell builtin: '"$FIRST_WORD"'"}'
      exit 0
      ;;
    kubectl|helm|docker)
      echo '{"decision":"allow","reason":"safe ops tool: '"$FIRST_WORD"'"}'
      exit 0
      ;;
    heg-state|stoa-dispatch|infisical)
      echo '{"decision":"allow","reason":"safe stoa tool: '"$FIRST_WORD"'"}'
      exit 0
      ;;
  esac
fi

# Edit/Write — allow by default on workers (instance scope enforced by pre-instance-scope.sh)
if [ "$TOOL_NAME" = "Edit" ] || [ "$TOOL_NAME" = "Write" ]; then
  echo '{"decision":"allow","reason":"file ops allowed (scope enforced by PreToolUse hook)"}'
  exit 0
fi

# Default: ask for human approval (unknown tool or command)
echo '{"decision":"ask","reason":"unknown pattern, needs human review"}'
exit 0
