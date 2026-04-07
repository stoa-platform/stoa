#!/bin/bash
# PostToolUse hook: Monitor context usage and warn when approaching limits.
#
# CAB-2005: Inspired by Claude Code's internal 5-strategy compaction system
# revealed in the March 2026 source leak. Their AutoCompact fires at ~95%
# with a 13K-token buffer. We trigger earlier (70%) to give the operator
# time to act, and hard-warn at 85%.
#
# This hook reads CLAUDE_CONTEXT_USAGE (if available via env) or estimates
# usage from conversation turn count. Outputs systemMessage advisories.
#
# Trigger: PostToolUse on all tools (lightweight — exits fast if no concern)
# Exit 0 always (advisory, never blocks)

# Fast exit if context tracking env vars not available
# Claude Code exposes context % in some builds — check for it
CONTEXT_PCT="${CLAUDE_CONTEXT_WINDOW_PERCENT:-}"

if [[ -z "$CONTEXT_PCT" ]]; then
  # Fallback: estimate from conversation metrics if available
  # The session-brief tracks approximate token usage
  PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
  BRIEF="$PROJECT_DIR/.claude/session-brief.json"

  if [[ -f "$BRIEF" ]]; then
    CONTEXT_PCT=$(jq -r '.context_percent // empty' "$BRIEF" 2>/dev/null)
  fi
fi

# If we still can't determine context %, exit silently
if [[ -z "$CONTEXT_PCT" ]]; then
  exit 0
fi

# Strip % if present
CONTEXT_PCT="${CONTEXT_PCT//%/}"

# Validate numeric
if ! [[ "$CONTEXT_PCT" =~ ^[0-9]+$ ]]; then
  exit 0
fi

# --- Thresholds ---
# 70%: suggest delegation to subagents
# 85%: recommend /compact
# 95%: urgent — wrap up and commit

if [[ "$CONTEXT_PCT" -ge 95 ]]; then
  MSG="URGENT: Context at ${CONTEXT_PCT}%. Wrap up immediately: commit current work, update state files, end session. Start a fresh session for remaining work."
  echo "$MSG" | jq -Rs '{"systemMessage": .}'
elif [[ "$CONTEXT_PCT" -ge 85 ]]; then
  MSG="Context at ${CONTEXT_PCT}%. Run /compact now to compress conversation. Delegate remaining research to subagents."
  echo "$MSG" | jq -Rs '{"systemMessage": .}'
elif [[ "$CONTEXT_PCT" -ge 70 ]]; then
  MSG="Context at ${CONTEXT_PCT}%. Consider delegating verbose operations to subagents to preserve context budget."
  echo "$MSG" | jq -Rs '{"systemMessage": .}'
else
  echo '{}'
fi

exit 0
