#!/usr/bin/env bash
# analyze-model-efficiency.sh — Reads metrics.log TOKEN-SPEND events, produces efficiency report
# Analyzes model routing effectiveness and recommends threshold adjustments.
# Usage: ./scripts/ai-ops/analyze-model-efficiency.sh [--days N] [--json]
# Defaults to 7-day lookback.
set -euo pipefail

DAYS=7
OUTPUT_JSON=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --days) DAYS="$2"; shift 2 ;;
    --json) OUTPUT_JSON=true; shift ;;
    *) shift ;;
  esac
done

METRICS_LOG="${METRICS_LOG:-$HOME/.claude/projects/-Users-torpedo-hlfh-repos-stoa/memory/metrics.log}"

if [[ ! -f "$METRICS_LOG" ]]; then
  echo "No metrics.log found at ${METRICS_LOG}"
  exit 0
fi

# Calculate date threshold (N days ago)
if [[ "$(uname)" == "Darwin" ]]; then
  DATE_THRESHOLD=$(date -u -v-${DAYS}d +%Y-%m-%d)
else
  DATE_THRESHOLD=$(date -u -d "${DAYS} days ago" +%Y-%m-%d)
fi

# Extract TOKEN-SPEND events within the date range
SPEND_EVENTS=$(grep 'TOKEN-SPEND' "$METRICS_LOG" \
  | awk -F'|' -v threshold="$DATE_THRESHOLD" '{
    split($1, ts, "T");
    gsub(/^ +| +$/, "", ts[1]);
    if (ts[1] >= threshold) print $0
  }') || true

if [[ -z "$SPEND_EVENTS" ]]; then
  echo "No TOKEN-SPEND events in the last ${DAYS} days."
  exit 0
fi

# Parse into aggregates
TOTAL_TOKENS=0
TOTAL_COST=0
TOTAL_SESSIONS=0
TOTAL_MESSAGES=0
DAYS_WITH_DATA=0
declare -A MODEL_TOKENS 2>/dev/null || true

# Use awk for robust parsing
STATS=$(echo "$SPEND_EVENTS" | awk '
  {
    for (i=1; i<=NF; i++) {
      if ($i ~ /^tokens_total=/) { split($i, a, "="); tokens += a[2] }
      if ($i ~ /^cost_usd=/) { split($i, a, "="); cost += a[2] }
      if ($i ~ /^sessions=/) { split($i, a, "="); sessions += a[2] }
      if ($i ~ /^messages=/) { split($i, a, "="); messages += a[2] }
      if ($i ~ /^date=/) { split($i, a, "="); dates[a[2]] = 1 }
      if ($i ~ /^models=/) {
        # Parse model=tokens pairs after "models="
        gsub(/^models=/, "", $i)
        # Remaining fields are model=tokens pairs
        split($i, mp, " ")
        for (m in mp) {
          if (mp[m] ~ /=/) {
            split(mp[m], mt, "=")
            model_tokens[mt[1]] += mt[2]
          }
        }
        # Also grab any trailing model=tokens pairs
        for (j=i+1; j<=NF; j++) {
          if ($j ~ /^[a-z].*=.*[0-9]/ && $j !~ /\|/) {
            split($j, mt, "=")
            model_tokens[mt[1]] += mt[2]
          }
        }
      }
    }
    lines++
  }
  END {
    printf "TOTAL_TOKENS=%d\n", tokens
    printf "TOTAL_COST=%.2f\n", cost
    printf "TOTAL_SESSIONS=%d\n", sessions
    printf "TOTAL_MESSAGES=%d\n", messages
    for (d in dates) day_count++
    printf "DAYS_WITH_DATA=%d\n", day_count
    printf "EVENT_COUNT=%d\n", lines
    for (m in model_tokens) {
      printf "MODEL:%s=%d\n", m, model_tokens[m]
    }
  }
')

eval "$(echo "$STATS" | grep -v '^MODEL:')"
MODEL_LINES=$(echo "$STATS" | grep '^MODEL:' | sed 's/^MODEL://')

# Count anomalies
ANOMALY_COUNT=$(grep 'COST-ANOMALY' "$METRICS_LOG" \
  | awk -F'|' -v threshold="$DATE_THRESHOLD" '{
    split($1, ts, "T"); gsub(/^ +| +$/, "", ts[1]);
    if (ts[1] >= threshold) count++
  } END { print count+0 }') || ANOMALY_COUNT=0

ALERT_COUNT=$(grep 'COST-ALERT' "$METRICS_LOG" \
  | awk -F'|' -v threshold="$DATE_THRESHOLD" '{
    split($1, ts, "T"); gsub(/^ +| +$/, "", ts[1]);
    if (ts[1] >= threshold) count++
  } END { print count+0 }') || ALERT_COUNT=0

# Compute derived metrics
AVG_DAILY_COST=$(awk -v total="$TOTAL_COST" -v days="${DAYS_WITH_DATA:-1}" 'BEGIN { printf "%.2f", total / (days > 0 ? days : 1) }')
AVG_TOKENS_PER_SESSION=$(awk -v tokens="$TOTAL_TOKENS" -v sessions="${TOTAL_SESSIONS:-1}" 'BEGIN { printf "%d", tokens / (sessions > 0 ? sessions : 1) }')

# Count PR-MERGED events for cost-per-PR
PR_COUNT=$(grep 'PR-MERGED' "$METRICS_LOG" \
  | awk -F'|' -v threshold="$DATE_THRESHOLD" '{
    split($1, ts, "T"); gsub(/^ +| +$/, "", ts[1]);
    if (ts[1] >= threshold) count++
  } END { print count+0 }') || PR_COUNT=0

COST_PER_PR="N/A"
if [[ "$PR_COUNT" -gt 0 ]]; then
  COST_PER_PR=$(awk -v cost="$TOTAL_COST" -v prs="$PR_COUNT" 'BEGIN { printf "$%.2f", cost / prs }')
fi

# --- Output ---
if [[ "$OUTPUT_JSON" == "true" ]]; then
  cat << EOF
{
  "period_days": ${DAYS},
  "days_with_data": ${DAYS_WITH_DATA:-0},
  "total_tokens": ${TOTAL_TOKENS},
  "total_cost_usd": ${TOTAL_COST},
  "total_sessions": ${TOTAL_SESSIONS},
  "total_messages": ${TOTAL_MESSAGES},
  "avg_daily_cost_usd": ${AVG_DAILY_COST},
  "avg_tokens_per_session": ${AVG_TOKENS_PER_SESSION},
  "prs_merged": ${PR_COUNT},
  "cost_per_pr": "${COST_PER_PR}",
  "anomalies": ${ANOMALY_COUNT},
  "alerts": ${ALERT_COUNT},
  "event_count": ${EVENT_COUNT:-0}
}
EOF
  exit 0
fi

echo "=== AI Factory Model Efficiency Report ==="
echo "Period: last ${DAYS} days (${DAYS_WITH_DATA:-0} days with data)"
echo ""
echo "--- Summary ---"
printf "  Total tokens:       %'d\n" "$TOTAL_TOKENS"
printf "  Total cost (API eq): \$%.2f\n" "$TOTAL_COST"
printf "  Sessions:           %d\n" "$TOTAL_SESSIONS"
printf "  Messages:           %d\n" "$TOTAL_MESSAGES"
echo ""
echo "--- Averages ---"
printf "  Avg daily cost:     \$%s\n" "$AVG_DAILY_COST"
printf "  Avg tokens/session: %'d\n" "$AVG_TOKENS_PER_SESSION"
printf "  PRs merged:         %d\n" "$PR_COUNT"
printf "  Cost per PR:        %s\n" "$COST_PER_PR"
echo ""
echo "--- Model Distribution ---"
if [[ -n "$MODEL_LINES" ]]; then
  echo "$MODEL_LINES" | while IFS='=' read -r model tokens; do
    local_pct=$(awk -v t="$tokens" -v total="$TOTAL_TOKENS" 'BEGIN { printf "%.1f", (total > 0) ? t/total*100 : 0 }')
    printf "  %-20s %'10d tokens (%s%%)\n" "$model" "$tokens" "$local_pct"
  done
fi
echo ""
echo "--- Alerts ---"
printf "  Cost alerts (>\$50/day): %d\n" "$ALERT_COUNT"
printf "  Cost anomalies (>2x avg): %d\n" "$ANOMALY_COUNT"
echo ""

# Recommendations
echo "--- Recommendations ---"
if [[ "$ANOMALY_COUNT" -gt 2 ]]; then
  echo "  ! Frequent cost anomalies — review session sizes and model routing"
fi
if [[ "$AVG_TOKENS_PER_SESSION" -gt 100000 ]]; then
  echo "  ! High avg tokens/session — consider splitting long sessions"
fi
if [[ "$PR_COUNT" -gt 0 ]]; then
  COST_NUM=$(echo "$COST_PER_PR" | tr -d '$')
  HIGH=$(awk -v c="${COST_NUM:-0}" 'BEGIN { print (c > 20) ? "yes" : "no" }')
  if [[ "$HIGH" == "yes" ]]; then
    echo "  ! Cost/PR > \$20 — check for over-scoped tickets or model tier mismatches"
  fi
fi
# Check if haiku is being used enough for small tasks
HAIKU_TOKENS=$(echo "$MODEL_LINES" | grep 'haiku' | cut -d= -f2 || echo 0)
HAIKU_PCT=$(awk -v h="${HAIKU_TOKENS:-0}" -v t="$TOTAL_TOKENS" 'BEGIN { printf "%.0f", (t > 0) ? h/t*100 : 0 }')
if [[ "$HAIKU_PCT" -lt 10 && "$TOTAL_SESSIONS" -gt 5 ]]; then
  echo "  * Haiku usage < 10% — consider routing more <=3pt tickets to Haiku"
fi
echo ""
echo "Done."
