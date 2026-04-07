#!/bin/bash
# PostToolUse hook: Capture agent/subagent invocation metrics.
#
# CAB-2005 Phase 2: Agent Observability. Logs every Agent tool call with
# duration, model, and description to agent-metrics.log for cost analysis.
#
# Trigger: PostToolUse on Agent tool
# Output: Appends to agent-metrics.log, optionally pushes to Pushgateway
# Exit 0 always (never blocks)

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)

# Only track Agent tool calls
if [[ "$TOOL_NAME" != "Agent" ]]; then
  exit 0
fi

# Extract agent metadata from tool input
AGENT_TYPE=$(echo "$INPUT" | jq -r '.tool_input.subagent_type // "general-purpose"' 2>/dev/null)
AGENT_MODEL=$(echo "$INPUT" | jq -r '.tool_input.model // "inherited"' 2>/dev/null)
AGENT_DESC=$(echo "$INPUT" | jq -r '.tool_input.description // "unnamed"' 2>/dev/null | cut -c 1-80)
AGENT_NAME=$(echo "$INPUT" | jq -r '.tool_input.name // empty' 2>/dev/null)
BACKGROUND=$(echo "$INPUT" | jq -r '.tool_input.run_in_background // false' 2>/dev/null)

# Extract result metadata (if available from tool output)
DURATION_MS=$(echo "$INPUT" | jq -r '.tool_result.duration_ms // empty' 2>/dev/null)
TOTAL_TOKENS=$(echo "$INPUT" | jq -r '.tool_result.total_tokens // empty' 2>/dev/null)
TOOL_USES=$(echo "$INPUT" | jq -r '.tool_result.tool_uses // empty' 2>/dev/null)

# Resolve log path
MEMORY_DIR="$HOME/.claude/projects/-Users-torpedo-hlfh-repos-stoa/memory"
AGENT_LOG="${MEMORY_DIR}/agent-metrics.log"

# Ensure directory exists
[ ! -d "$MEMORY_DIR" ] && exit 0

NOW=$(date +%Y-%m-%dT%H:%M)
INSTANCE="${STOA_INSTANCE:-main}"

# Format duration for readability
if [[ -n "$DURATION_MS" && "$DURATION_MS" != "null" ]]; then
  DURATION_SEC=$((DURATION_MS / 1000))
  DURATION_STR="${DURATION_SEC}s"
else
  DURATION_STR="unknown"
fi

# Format tokens
if [[ -n "$TOTAL_TOKENS" && "$TOTAL_TOKENS" != "null" ]]; then
  TOKEN_STR="${TOTAL_TOKENS}"
else
  TOKEN_STR="unknown"
fi

# Log entry
echo "${NOW} | AGENT-CALL | type=${AGENT_TYPE} model=${AGENT_MODEL} duration=${DURATION_STR} tokens=${TOKEN_STR} tools=${TOOL_USES:-0} bg=${BACKGROUND} instance=${INSTANCE} desc=\"${AGENT_DESC}\"" >> "$AGENT_LOG"

# Rotate if over 500 lines
LINE_COUNT=$(wc -l < "$AGENT_LOG" 2>/dev/null || echo 0)
if [[ "$LINE_COUNT" -gt 500 ]]; then
  tail -250 "$AGENT_LOG" > "${AGENT_LOG}.tmp" && mv "${AGENT_LOG}.tmp" "$AGENT_LOG"
fi

# Push to Pushgateway if configured (non-blocking)
if [[ -n "${PUSHGATEWAY_URL:-}" && -n "$DURATION_MS" && "$DURATION_MS" != "null" ]]; then
  (
    cat <<METRICS | curl -s --max-time 5 --data-binary @- "${PUSHGATEWAY_URL}/metrics/job/ai_factory_agents/instance/${INSTANCE}" 2>/dev/null || true
# HELP ai_factory_agent_duration_seconds Agent call duration
# TYPE ai_factory_agent_duration_seconds gauge
ai_factory_agent_duration_seconds{type="${AGENT_TYPE}",model="${AGENT_MODEL}"} $(echo "scale=2; ${DURATION_MS}/1000" | bc 2>/dev/null || echo 0)
# HELP ai_factory_agent_tokens Agent call token usage
# TYPE ai_factory_agent_tokens gauge
ai_factory_agent_tokens{type="${AGENT_TYPE}",model="${AGENT_MODEL}"} ${TOTAL_TOKENS:-0}
# HELP ai_factory_agent_calls_total Agent call counter
# TYPE ai_factory_agent_calls_total counter
ai_factory_agent_calls_total{type="${AGENT_TYPE}",model="${AGENT_MODEL}"} 1
METRICS
  ) &
fi

exit 0
