#!/usr/bin/env bash
# AI Factory Model Router — tiered model selection by ticket complexity
# Source this file: source scripts/ai-ops/model-router.sh
# Usage: ROUTE=$(route_model "$ESTIMATE" "$MODE")
#        MODEL=$(echo "$ROUTE" | cut -d'|' -f1)
#        TURNS=$(echo "$ROUTE" | cut -d'|' -f2)

# Tiered model routing:
#   Ship <=3pts  → Haiku, 15 turns  (~$2.50/ticket)
#   <=8pts       → Sonnet, 30 turns (~$9.50/ticket)
#   >8pts        → Sonnet, 60 turns (~$16.50/ticket)
# Weighted average: ~$6.50/ticket (vs $16.50 flat Sonnet-60)

route_model() {
  local ESTIMATE="${1:-0}"
  local MODE="${2:-ask}"

  # Normalize mode to lowercase
  MODE=$(echo "$MODE" | tr '[:upper:]' '[:lower:]')

  # Ensure ESTIMATE is numeric
  if ! echo "$ESTIMATE" | grep -qE '^[0-9]+$'; then
    ESTIMATE=0
  fi

  if [ "$ESTIMATE" -le 3 ] && [ "$MODE" = "ship" ]; then
    echo "claude-haiku-4-5-20251001|15"
  elif [ "$ESTIMATE" -le 8 ]; then
    echo "claude-sonnet-4-5-20250929|30"
  else
    echo "claude-sonnet-4-5-20250929|60"
  fi
}

# Extract estimate from issue body text (searches for "Estimate: X pts" or "X pts" patterns)
extract_estimate() {
  local TEXT="$1"
  local EST=""

  # Try "Estimate: X pts" pattern first
  EST=$(echo "$TEXT" | grep -oiE 'estimate:?\s*[0-9]+\s*pts?' | head -1 | grep -oE '[0-9]+' | head -1)

  # Fallback: try "(X pts" pattern
  if [ -z "$EST" ]; then
    EST=$(echo "$TEXT" | grep -oE '\([0-9]+ pts' | head -1 | grep -oE '[0-9]+' | head -1)
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
