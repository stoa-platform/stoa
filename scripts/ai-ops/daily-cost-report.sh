#!/usr/bin/env bash
# daily-cost-report.sh — Daily AI Factory cost report
# Runs from VPS cron, reads Pushgateway metrics, sends Slack Block Kit message.
# Usage: SLACK_WEBHOOK=... PUSHGATEWAY_URL=... bash daily-cost-report.sh
# Cron: 0 8 * * * /opt/stoa-ops/daily-cost-report.sh >> /var/log/stoa-cost-report.log 2>&1
set -euo pipefail

# --- Source notification library ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "${SCRIPT_DIR}/ai-factory-notify.sh" ]]; then
  # shellcheck source=/dev/null
  source "${SCRIPT_DIR}/ai-factory-notify.sh"
elif [[ -f "/opt/stoa-ops/ai-factory-notify.sh" ]]; then
  # shellcheck source=/dev/null
  source "/opt/stoa-ops/ai-factory-notify.sh"
else
  echo "ERROR: ai-factory-notify.sh not found" >&2
  exit 1
fi

# --- Config ---
TODAY=$(date -u +%Y-%m-%d)
PUSHGATEWAY_URL="${PUSHGATEWAY_URL:?PUSHGATEWAY_URL is required}"
SLACK_WEBHOOK="${SLACK_WEBHOOK:?SLACK_WEBHOOK is required}"

# --- Functions ---

# Fetch a metric value from Pushgateway
# Usage: fetch_metric METRIC_NAME [LABEL_FILTER]
fetch_metric() {
  local metric="$1" filter="${2:-}"
  local url="${PUSHGATEWAY_URL}/metrics"
  local auth_header=""
  if [[ -n "${PUSHGATEWAY_AUTH:-}" ]]; then
    auth_header="-H \"Authorization: Basic ${PUSHGATEWAY_AUTH}\""
  fi

  local raw
  raw=$(eval curl -sf ${auth_header} "$url" 2>/dev/null) || { echo "0"; return; }

  if [[ -n "$filter" ]]; then
    echo "$raw" | grep "^${metric}{.*${filter}" | tail -1 | awk '{print $NF}' || echo "0"
  else
    echo "$raw" | grep "^${metric}" | grep -v "^#" | tail -1 | awk '{print $NF}' || echo "0"
  fi
}

# Fetch daily metric for a specific date
fetch_daily() {
  local metric="$1" date="$2"
  fetch_metric "$metric" "date=\"${date}\""
}

# --- Main ---
main() {
  echo "[$(date -u +%Y-%m-%dT%H:%M)] Starting daily cost report for ${TODAY}"

  # Fetch today's metrics
  local tokens_today cost_today sessions_today messages_today
  tokens_today=$(fetch_daily "ai_factory_daily_tokens" "$TODAY")
  cost_today=$(fetch_daily "ai_factory_daily_cost_usd" "$TODAY")
  sessions_today=$(fetch_daily "ai_factory_daily_sessions" "$TODAY")
  messages_today=$(fetch_daily "ai_factory_daily_messages" "$TODAY")

  # Default to 0 if empty
  tokens_today="${tokens_today:-0}"
  cost_today="${cost_today:-0}"
  sessions_today="${sessions_today:-0}"
  messages_today="${messages_today:-0}"

  # Fetch last 7 days for average
  local cost_sum=0 days_with_data=0
  for i in $(seq 1 7); do
    local d
    d=$(date -u -v-${i}d +%Y-%m-%d 2>/dev/null || date -u -d "-${i} days" +%Y-%m-%d 2>/dev/null)
    local c
    c=$(fetch_daily "ai_factory_daily_cost_usd" "$d")
    if [[ -n "$c" && "$c" != "0" ]]; then
      cost_sum=$(awk -v a="$cost_sum" -v b="$c" 'BEGIN { printf "%.2f", a+b }')
      days_with_data=$((days_with_data + 1))
    fi
  done

  local cost_7d_avg="0"
  if [[ "$days_with_data" -gt 0 ]]; then
    cost_7d_avg=$(awk -v s="$cost_sum" -v d="$days_with_data" 'BEGIN { printf "%.2f", s/d }')
  fi

  # Trend: compare today vs 3-day average
  local cost_3d_sum=0 days_3d=0
  for i in 1 2 3; do
    local d
    d=$(date -u -v-${i}d +%Y-%m-%d 2>/dev/null || date -u -d "-${i} days" +%Y-%m-%d 2>/dev/null)
    local c
    c=$(fetch_daily "ai_factory_daily_cost_usd" "$d")
    if [[ -n "$c" && "$c" != "0" ]]; then
      cost_3d_sum=$(awk -v a="$cost_3d_sum" -v b="$c" 'BEGIN { printf "%.2f", a+b }')
      days_3d=$((days_3d + 1))
    fi
  done

  local trend="flat"
  if [[ "$days_3d" -gt 0 && "$cost_today" != "0" ]]; then
    local cost_3d_avg
    cost_3d_avg=$(awk -v s="$cost_3d_sum" -v d="$days_3d" 'BEGIN { printf "%.2f", s/d }')
    local deviation
    deviation=$(awk -v t="$cost_today" -v a="$cost_3d_avg" 'BEGIN {
      if (a == 0) { print "flat"; exit }
      d = (t - a) / a
      if (d > 0.20) print "up"
      else if (d < -0.20) print "down"
      else print "flat"
    }')
    trend="$deviation"
  fi

  # Fetch PRs merged count (from events_total with verdict=merged)
  local prs_merged
  prs_merged=$(fetch_metric "ai_factory_events_total" "verdict=\"merged\"")
  prs_merged="${prs_merged:-0}"

  # Model mix (from daily tokens by model)
  local model_mix=""
  local raw_metrics
  raw_metrics=$(curl -sf "${PUSHGATEWAY_URL}/metrics" 2>/dev/null) || raw_metrics=""
  if [[ -n "$raw_metrics" ]]; then
    model_mix=$(echo "$raw_metrics" | grep "^ai_factory_daily_tokens_by_model{.*date=\"${TODAY}\"" | \
      sed 's/.*model="\([^"]*\)".* \([0-9.]*\)$/\1:\2/' | tr '\n' ' ' | xargs) || model_mix=""
  fi

  # Call notify_cost_report
  notify_cost_report "$TODAY" "$tokens_today" "$cost_today" "$cost_7d_avg" \
    "$sessions_today" "$messages_today" "$prs_merged" "$model_mix" "$trend"

  echo "[$(date -u +%Y-%m-%dT%H:%M)] Report sent: cost=\$${cost_today}, 7d_avg=\$${cost_7d_avg}, trend=${trend}"
}

main "$@"
