#!/usr/bin/env bash
# stop-cost-tracker.sh — Token Observatory stop hook
# Parses ~/.claude/stats-cache.json, logs TOKEN-SPEND to metrics.log,
# pushes cost gauges to Pushgateway.
# Runs on every session end (Stop hook). Always exits 0 (warn-only).
set -euo pipefail

# --- Config ---
STATS_FILE="$HOME/.claude/stats-cache.json"
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
METRICS_LOG="$HOME/.claude/projects/-Users-torpedo-hlfh-repos-stoa/memory/metrics.log"
TODAY="${COST_DATE:-$(date -u +%Y-%m-%d)}"
NOW="$(date -u +%Y-%m-%dT%H:%M)"
COST_ALERT_THRESHOLD="${COST_ALERT_THRESHOLD:-50}"

# --- Functions ---

# Shorten model name: claude-opus-4-6 → opus-4-6, claude-haiku-4-5-20251001 → haiku-4-5
shorten_model() {
  echo "$1" | sed 's/claude-//;s/-20[0-9]*//'
}

# Get API-equivalent pricing per million tokens: input output cache_read cache_write
# Usage: get_pricing MODEL → sets PI PO PCR PCW
get_pricing() {
  case "$1" in
    opus-4-6)    PI=15;   PO=75;  PCR=1.50;  PCW=18.75 ;;
    sonnet-4-6)  PI=3;    PO=15;  PCR=0.30;  PCW=3.75 ;;
    sonnet-4-5)  PI=3;    PO=15;  PCR=0.30;  PCW=3.75 ;;
    haiku-4-5)   PI=0.80; PO=4;   PCR=0.08;  PCW=1 ;;
    *)           PI=3;    PO=15;  PCR=0.30;  PCW=3.75 ;;  # default to sonnet pricing
  esac
}

# Calculate cost for a model given estimated token breakdown
# Usage: calc_model_cost MODEL TOKENS INPUT_RATIO OUTPUT_RATIO CACHE_READ_RATIO CACHE_WRITE_RATIO
calc_model_cost() {
  local model="$1" tokens="$2"
  local in_ratio="$3" out_ratio="$4" cr_ratio="$5" cw_ratio="$6"

  local PI PO PCR PCW
  get_pricing "$model"

  # tokens * ratio * price_per_M / 1_000_000
  awk -v t="$tokens" -v ir="$in_ratio" -v or="$out_ratio" -v crr="$cr_ratio" -v cwr="$cw_ratio" \
      -v pi="$PI" -v po="$PO" -v pcr="$PCR" -v pcw="$PCW" \
      'BEGIN { printf "%.4f", (t*ir*pi + t*or*po + t*crr*pcr + t*cwr*pcw) / 1000000 }'
}

# --- Main ---
main() {
  if [[ ! -f "$STATS_FILE" ]]; then
    exit 0
  fi

  if ! command -v jq &>/dev/null; then
    exit 0
  fi

  # Extract today's daily tokens by model
  local daily_json
  daily_json=$(jq -r --arg d "$TODAY" '
    (.dailyModelTokens // []) | map(select(.date == $d)) | .[0] // empty
  ' "$STATS_FILE" 2>/dev/null) || true

  if [[ -z "$daily_json" || "$daily_json" == "null" ]]; then
    exit 0
  fi

  # Extract today's activity
  local sessions messages
  sessions=$(jq -r --arg d "$TODAY" '
    (.dailyActivity // []) | map(select(.date == $d)) | .[0].sessionCount // 0
  ' "$STATS_FILE" 2>/dev/null) || sessions=0
  messages=$(jq -r --arg d "$TODAY" '
    (.dailyActivity // []) | map(select(.date == $d)) | .[0].messageCount // 0
  ' "$STATS_FILE" 2>/dev/null) || messages=0

  # Get cumulative modelUsage for ratio estimation
  local model_usage
  model_usage=$(jq -r '.modelUsage // {}' "$STATS_FILE" 2>/dev/null) || model_usage="{}"

  # Parse daily tokens by model
  local tokens_by_model
  tokens_by_model=$(echo "$daily_json" | jq -r '.tokensByModel // {} | to_entries[] | "\(.key)=\(.value)"' 2>/dev/null) || true

  if [[ -z "$tokens_by_model" ]]; then
    exit 0
  fi

  local total_tokens=0
  local total_cost=0
  local model_summary=""

  while IFS='=' read -r raw_model tokens; do
    local model
    model=$(shorten_model "$raw_model")
    total_tokens=$((total_tokens + tokens))

    # Get cumulative stats for this model to estimate in/out/cache ratios
    local cum_in cum_out cum_cr cum_cw cum_total
    cum_in=$(echo "$model_usage" | jq -r --arg m "$raw_model" '.[$m].inputTokens // 0' 2>/dev/null) || cum_in=0
    cum_out=$(echo "$model_usage" | jq -r --arg m "$raw_model" '.[$m].outputTokens // 0' 2>/dev/null) || cum_out=0
    cum_cr=$(echo "$model_usage" | jq -r --arg m "$raw_model" '.[$m].cacheReadInputTokens // 0' 2>/dev/null) || cum_cr=0
    cum_cw=$(echo "$model_usage" | jq -r --arg m "$raw_model" '.[$m].cacheCreationInputTokens // 0' 2>/dev/null) || cum_cw=0
    cum_total=$((cum_in + cum_out + cum_cr + cum_cw))

    # Calculate ratios (default: 40% in, 30% out, 20% cache read, 10% cache write)
    local in_ratio out_ratio cr_ratio cw_ratio
    if [[ "$cum_total" -gt 0 ]]; then
      in_ratio=$(awk -v a="$cum_in" -v t="$cum_total" 'BEGIN { printf "%.4f", a/t }')
      out_ratio=$(awk -v a="$cum_out" -v t="$cum_total" 'BEGIN { printf "%.4f", a/t }')
      cr_ratio=$(awk -v a="$cum_cr" -v t="$cum_total" 'BEGIN { printf "%.4f", a/t }')
      cw_ratio=$(awk -v a="$cum_cw" -v t="$cum_total" 'BEGIN { printf "%.4f", a/t }')
    else
      in_ratio="0.40"; out_ratio="0.30"; cr_ratio="0.20"; cw_ratio="0.10"
    fi

    local cost
    cost=$(calc_model_cost "$model" "$tokens" "$in_ratio" "$out_ratio" "$cr_ratio" "$cw_ratio")
    total_cost=$(awk -v a="$total_cost" -v b="$cost" 'BEGIN { printf "%.4f", a+b }')

    if [[ -n "$model_summary" ]]; then
      model_summary+=" "
    fi
    model_summary+="${model}=${tokens}"
  done <<< "$tokens_by_model"

  # Format cost with 2 decimals
  local cost_display
  cost_display=$(awk -v c="$total_cost" 'BEGIN { printf "%.2f", c }')

  # Log TOKEN-SPEND
  echo "${NOW} | TOKEN-SPEND | date=${TODAY} tokens_total=${total_tokens} cost_usd=${cost_display} sessions=${sessions} messages=${messages} models=${model_summary}" >> "$METRICS_LOG"

  # Check cost alert
  local alert
  alert=$(awk -v c="$total_cost" -v t="$COST_ALERT_THRESHOLD" 'BEGIN { print (c > t) ? "yes" : "no" }')
  if [[ "$alert" == "yes" ]]; then
    echo "${NOW} | COST-ALERT | threshold=${COST_ALERT_THRESHOLD} actual=${cost_display} date=${TODAY}" >> "$METRICS_LOG"
  fi

  # Push to Pushgateway (if ai-factory-notify.sh is available and PUSHGATEWAY_URL set)
  local notify_script="${PROJECT_DIR}/scripts/ai-ops/ai-factory-notify.sh"
  if [[ -f "$notify_script" && -n "${PUSHGATEWAY_URL:-}" ]]; then
    # shellcheck source=/dev/null
    source "$notify_script"

    local METRICS=""
    METRICS+="# HELP ai_factory_daily_tokens Daily token consumption\n"
    METRICS+="# TYPE ai_factory_daily_tokens gauge\n"
    METRICS+="ai_factory_daily_tokens{date=\"${TODAY}\"} ${total_tokens}\n"
    METRICS+="# HELP ai_factory_daily_cost_usd Daily estimated cost (API equivalent)\n"
    METRICS+="# TYPE ai_factory_daily_cost_usd gauge\n"
    METRICS+="ai_factory_daily_cost_usd{date=\"${TODAY}\"} ${total_cost}\n"
    METRICS+="# HELP ai_factory_daily_sessions Daily session count\n"
    METRICS+="# TYPE ai_factory_daily_sessions gauge\n"
    METRICS+="ai_factory_daily_sessions{date=\"${TODAY}\"} ${sessions}\n"
    METRICS+="# HELP ai_factory_daily_messages Daily message count\n"
    METRICS+="# TYPE ai_factory_daily_messages gauge\n"
    METRICS+="ai_factory_daily_messages{date=\"${TODAY}\"} ${messages}\n"

    # Per-model token breakdown
    METRICS+="# HELP ai_factory_daily_tokens_by_model Daily tokens per model\n"
    METRICS+="# TYPE ai_factory_daily_tokens_by_model gauge\n"
    while IFS='=' read -r raw_model tokens; do
      local model
      model=$(shorten_model "$raw_model")
      METRICS+="ai_factory_daily_tokens_by_model{date=\"${TODAY}\",model=\"${model}\"} ${tokens}\n"
    done <<< "$tokens_by_model"

    _push_metrics "cost-tracker/${TODAY}" "$(printf '%b' "$METRICS")" 2>/dev/null || true
  fi
}

main "$@" || true
