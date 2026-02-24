#!/usr/bin/env bash
# AI Factory Model Router — tiered model selection by ticket complexity
# Source this file: source scripts/ai-ops/model-router.sh
# Usage: ROUTE=$(route_model "$ESTIMATE" "$MODE")
#        MODEL=$(echo "$ROUTE" | cut -d'|' -f1)
#        TURNS=$(echo "$ROUTE" | cut -d'|' -f2)

# Tiered model routing (implementation jobs):
#   <=3pts Ship   → Sonnet, 20 turns  (~$5/ticket)
#   <=3pts        → Sonnet, 25 turns  (~$7/ticket)
#   4-5pts        → Sonnet, 35 turns  (~$10/ticket)
#   6-8pts        → Opus,   30 turns  (~$18/ticket)
#   >8pts         → Opus,   40 turns  (~$25/ticket)
#
# Kill-switch: set CLAUDE_DEFAULT_MODEL repo variable to force a single model
# for all tiers (e.g. "claude-sonnet-4-6" to revert to Sonnet-only).
#
# Haiku is reserved for council/plan-validate (structured evaluation).
# Turn budget accounts for action overhead (~5-8 turns for branch+PR+tests).

route_model() {
  local ESTIMATE="${1:-0}"
  local MODE="${2:-ask}"

  # Normalize mode to lowercase
  MODE=$(echo "$MODE" | tr '[:upper:]' '[:lower:]')

  # Ensure ESTIMATE is numeric
  if ! echo "$ESTIMATE" | grep -qE '^[0-9]+$'; then
    ESTIMATE=0
  fi

  # Kill-switch: CLAUDE_DEFAULT_MODEL overrides all tiers
  if [ -n "${CLAUDE_DEFAULT_MODEL:-}" ]; then
    local TURNS=40
    [ "$ESTIMATE" -le 3 ] && TURNS=25
    [ "$ESTIMATE" -gt 8 ] && TURNS=60
    echo "${CLAUDE_DEFAULT_MODEL}|${TURNS}"
    return
  fi

  local MODEL TURNS
  if [ "$ESTIMATE" -le 3 ]; then
    MODEL="claude-sonnet-4-6"
    TURNS=25
  elif [ "$ESTIMATE" -le 5 ]; then
    MODEL="claude-sonnet-4-6"
    TURNS=35
  elif [ "$ESTIMATE" -le 8 ]; then
    MODEL="claude-opus-4-6"
    TURNS=30
  else
    MODEL="claude-opus-4-6"
    TURNS=40
  fi

  # Ship mode: tighter budget on small tickets (faster, cheaper)
  if [ "$MODE" = "ship" ] && [ "$ESTIMATE" -le 3 ]; then
    TURNS=20
  fi

  echo "${MODEL}|${TURNS}"
}

# Extract estimate from issue body text (searches for "Estimate: X pts" or "X pts" patterns)
# Falls back to LOC-based heuristic: ~80 LOC ≈ 3pts, ~200 LOC ≈ 5pts, ~500+ LOC ≈ 8pts
extract_estimate() {
  local TEXT="$1"
  local EST=""

  # Try "Estimate: X pts" pattern first
  EST=$(echo "$TEXT" | grep -oiE 'estimate:?\s*[0-9]+\s*pts?' | head -1 | grep -oE '[0-9]+' | head -1)

  # Fallback: try "(X pts" pattern (e.g. "(13 pts)")
  if [ -z "$EST" ]; then
    EST=$(echo "$TEXT" | grep -oE '\([0-9]+ pts' | head -1 | grep -oE '[0-9]+' | head -1)
  fi

  # Fallback: try "X pts" in Council context (e.g. "8 pts reasonable", "13 pts")
  # Only match small numbers (1-99) to avoid false positives with scores like "8.0/10"
  if [ -z "$EST" ]; then
    EST=$(echo "$TEXT" | grep -oE '\b[0-9]{1,2} pts\b' | head -1 | grep -oE '[0-9]+' | head -1)
  fi

  # Fallback: try "Total: ~NNN LOC" from Stage 2 plan comments
  if [ -z "$EST" ]; then
    local LOC_TOTAL
    LOC_TOTAL=$(echo "$TEXT" | grep -oiE 'total:?\s*~?[0-9]+\s*LOC' | head -1 | grep -oE '[0-9]+' | head -1)
    if [ -n "$LOC_TOTAL" ]; then
      if [ "$LOC_TOTAL" -le 100 ]; then
        EST=3
      elif [ "$LOC_TOTAL" -le 300 ]; then
        EST=5
      else
        EST=8
      fi
    fi
  fi

  # Fallback: derive from LOC estimate ("Estimated LOC: ~80" or "~150 LOC")
  if [ -z "$EST" ]; then
    local LOC
    LOC=$(echo "$TEXT" | grep -oiE '(estimated\s+loc|loc):?\s*~?[0-9]+' | head -1 | grep -oE '[0-9]+' | head -1)
    if [ -z "$LOC" ]; then
      LOC=$(echo "$TEXT" | grep -oE '~[0-9]+ LOC' | head -1 | grep -oE '[0-9]+' | head -1)
    fi
    if [ -n "$LOC" ]; then
      if [ "$LOC" -le 100 ]; then
        EST=3
      elif [ "$LOC" -le 300 ]; then
        EST=5
      else
        EST=8
      fi
    fi
  fi

  echo "${EST:-0}"
}

# Extract Ship/Show/Ask mode from Council report text
extract_mode() {
  local TEXT="$1"
  local MODE=""

  # Try "Ship/Show/Ask: MODE" pattern
  MODE=$(echo "$TEXT" | grep -oiE 'ship/show/ask:?\s*(ship|show|ask)' | head -1 | grep -oiE '(ship|show|ask)$' | head -1)

  # Fallback: try standalone patterns
  if [ -z "$MODE" ]; then
    if echo "$TEXT" | grep -qiE 'classification:?\s*ship'; then
      MODE="ship"
    elif echo "$TEXT" | grep -qiE 'classification:?\s*show'; then
      MODE="show"
    fi
  fi

  echo "${MODE:-ask}" | tr '[:upper:]' '[:lower:]'
}
