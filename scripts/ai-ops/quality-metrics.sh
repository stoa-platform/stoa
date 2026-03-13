#!/usr/bin/env bash
# quality-metrics.sh — AI Factory Quality Metrics
# Tracks regression rate, time-to-regression, and PR rejection rate for AI-generated PRs.
# Usage: PUSHGATEWAY_URL=... bash scripts/ai-ops/quality-metrics.sh [--days 30] [--push] [--json]
# Cron: 0 7 * * 1 /opt/stoa-ops/quality-metrics.sh --push >> /var/log/stoa-quality-metrics.log 2>&1
set -euo pipefail

# --- Config ---
REPO="${REPO:-stoa-platform/stoa}"
DAYS="${DAYS:-30}"
PUSH="${PUSH:-false}"
JSON_OUTPUT="${JSON_OUTPUT:-false}"
PUSHGATEWAY_URL="${PUSHGATEWAY_URL:-}"
JOB_NAME="ai_factory_quality"

# --- Parse args ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --days) DAYS="$2"; shift 2 ;;
    --push) PUSH="true"; shift ;;
    --json) JSON_OUTPUT="true"; shift ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

# --- Date helpers (macOS + GNU compatible) ---
days_ago_iso() {
  local n="$1"
  date -u -v-"${n}d" +%Y-%m-%dT00:00:00Z 2>/dev/null || \
    date -u -d "${n} days ago" +%Y-%m-%dT00:00:00Z 2>/dev/null
}

iso_to_epoch() {
  local dt="$1"
  date -d "$dt" +%s 2>/dev/null || \
    python3 -c "from datetime import datetime; print(int(datetime.fromisoformat('${dt}'.replace('Z','+00:00')).timestamp()))" 2>/dev/null || \
    echo "0"
}

SINCE=$(days_ago_iso "$DAYS")

# --- Collect merged PRs in the time window ---
# Fetch all merged PRs with their metadata
echo "Collecting merged PRs from last ${DAYS} days..." >&2

ALL_PRS=$(gh pr list --repo "$REPO" --state merged --limit 200 \
  --search "merged:>=$(echo "$SINCE" | cut -dT -f1)" \
  --json number,title,author,headRefName,mergedAt,labels \
  2>/dev/null || echo "[]")

TOTAL_PRS=$(echo "$ALL_PRS" | jq 'length')

if [[ "$TOTAL_PRS" -eq 0 ]]; then
  echo "No merged PRs found in the last ${DAYS} days." >&2
  exit 0
fi

# --- Classify PRs ---

# AI-authored PRs: Co-Authored-By Claude, or author is claude/github-actions, or branch matches pattern
AI_PRS=$(echo "$ALL_PRS" | jq '[.[] | select(
  (.author.login == "claude[bot]") or
  (.author.login == "github-actions[bot]") or
  (.headRefName | test("^feat/cab-|^fix/cab-|^feat/CAB-|^fix/CAB-"; "i"))
)]')
AI_PR_COUNT=$(echo "$AI_PRS" | jq 'length')

HUMAN_PRS=$(echo "$ALL_PRS" | jq --argjson ai "$AI_PRS" '[
  .[] | . as $pr | select([$ai[] | .number] | index($pr.number) | not)
]')
HUMAN_PR_COUNT=$(echo "$HUMAN_PRS" | jq 'length')

# Fix PRs (title starts with fix( or hotfix()
AI_FIX_PRS=$(echo "$AI_PRS" | jq '[.[] | select(.title | test("^(fix|hotfix)\\("; "i"))]')
AI_FIX_COUNT=$(echo "$AI_FIX_PRS" | jq 'length')

AI_FEAT_PRS=$(echo "$AI_PRS" | jq '[.[] | select(.title | test("^feat\\("; "i"))]')
AI_FEAT_COUNT=$(echo "$AI_FEAT_PRS" | jq 'length')

HUMAN_FIX_PRS=$(echo "$HUMAN_PRS" | jq '[.[] | select(.title | test("^(fix|hotfix)\\("; "i"))]')
HUMAN_FIX_COUNT=$(echo "$HUMAN_FIX_PRS" | jq 'length')

HUMAN_FEAT_PRS=$(echo "$HUMAN_PRS" | jq '[.[] | select(.title | test("^feat\\("; "i"))]')
HUMAN_FEAT_COUNT=$(echo "$HUMAN_FEAT_PRS" | jq 'length')

# --- Metric 1: Regression Rate (fix PRs / feat PRs) ---
# A high ratio means features introduce bugs that need fixing
if [[ "$AI_FEAT_COUNT" -gt 0 ]]; then
  AI_REGRESSION_RATE=$(printf "%.4f" "$(echo "scale=4; $AI_FIX_COUNT / $AI_FEAT_COUNT" | bc)")
else
  AI_REGRESSION_RATE="0.0000"
fi

if [[ "$HUMAN_FEAT_COUNT" -gt 0 ]]; then
  HUMAN_REGRESSION_RATE=$(printf "%.4f" "$(echo "scale=4; $HUMAN_FIX_COUNT / $HUMAN_FEAT_COUNT" | bc)")
else
  HUMAN_REGRESSION_RATE="0.0000"
fi

# --- Metric 2: Time-to-Regression (hours between feat merge and subsequent fix on same files) ---
# For each fix PR, find the most recent feat PR that touched the same files
# This is expensive, so we sample up to 10 fix PRs
TOTAL_TTR_HOURS=0
TTR_COUNT=0

SAMPLE_FIXES=$(echo "$AI_FIX_PRS" | jq -c '.[0:10][]' 2>/dev/null || echo "")
while IFS= read -r fix_pr; do
  [[ -z "$fix_pr" ]] && continue
  fix_num=$(echo "$fix_pr" | jq -r '.number')
  fix_merged=$(echo "$fix_pr" | jq -r '.mergedAt')

  # Get files changed in this fix PR
  fix_files=$(gh pr diff "$fix_num" --repo "$REPO" --name-only 2>/dev/null || echo "")
  [[ -z "$fix_files" ]] && continue

  # Search feat PRs merged before this fix that touch the same files
  while IFS= read -r feat_pr; do
    [[ -z "$feat_pr" ]] && continue
    feat_num=$(echo "$feat_pr" | jq -r '.number')
    feat_merged=$(echo "$feat_pr" | jq -r '.mergedAt')

    # Skip if feat merged after fix
    feat_epoch=$(iso_to_epoch "$feat_merged")
    fix_epoch=$(iso_to_epoch "$fix_merged")
    [[ "$feat_epoch" -ge "$fix_epoch" ]] && continue

    # Check file overlap
    feat_files=$(gh pr diff "$feat_num" --repo "$REPO" --name-only 2>/dev/null || echo "")
    overlap=$(comm -12 <(echo "$fix_files" | sort) <(echo "$feat_files" | sort) | head -1)
    if [[ -n "$overlap" ]]; then
      diff_hours=$(( (fix_epoch - feat_epoch) / 3600 ))
      TOTAL_TTR_HOURS=$((TOTAL_TTR_HOURS + diff_hours))
      TTR_COUNT=$((TTR_COUNT + 1))
      break  # Found the most recent feat PR, stop searching
    fi
  done < <(echo "$AI_FEAT_PRS" | jq -c 'sort_by(.mergedAt) | reverse | .[0:20][]' 2>/dev/null)
done < <(echo "$SAMPLE_FIXES")

if [[ "$TTR_COUNT" -gt 0 ]]; then
  AVG_TTR_HOURS=$((TOTAL_TTR_HOURS / TTR_COUNT))
else
  AVG_TTR_HOURS=0
fi

# --- Metric 3: PR Rejection Rate (CI failures on first push) ---
# Count PRs that had at least one failed check run before passing
AI_REJECTED=0
SAMPLE_AI=$(echo "$AI_PRS" | jq -c '.[0:20][]' 2>/dev/null || echo "")
while IFS= read -r pr; do
  [[ -z "$pr" ]] && continue
  pr_num=$(echo "$pr" | jq -r '.number')

  # Check if PR had any failed check suites
  failed=$(gh api "repos/${REPO}/pulls/${pr_num}/commits" \
    --jq '.[0].sha' 2>/dev/null || echo "")
  if [[ -n "$failed" ]]; then
    check_failures=$(gh api "repos/${REPO}/commits/${failed}/check-runs" \
      --jq '[.check_runs[] | select(.conclusion == "failure")] | length' 2>/dev/null || echo "0")
    if [[ "$check_failures" -gt 0 ]]; then
      AI_REJECTED=$((AI_REJECTED + 1))
    fi
  fi
done < <(echo "$SAMPLE_AI")

SAMPLE_AI_COUNT=$(echo "$AI_PRS" | jq '[.[0:20]] | .[0] | length')
if [[ "$SAMPLE_AI_COUNT" -gt 0 ]]; then
  AI_REJECTION_RATE=$(printf "%.4f" "$(echo "scale=4; $AI_REJECTED / $SAMPLE_AI_COUNT" | bc)")
else
  AI_REJECTION_RATE="0"
fi

# --- Output ---
echo ""
echo "=== AI Factory Quality Metrics (last ${DAYS} days) ==="
echo ""
echo "PRs merged:           ${TOTAL_PRS} total (${AI_PR_COUNT} AI, ${HUMAN_PR_COUNT} human)"
echo "AI feat PRs:          ${AI_FEAT_COUNT}"
echo "AI fix PRs:           ${AI_FIX_COUNT}"
echo "Human feat PRs:       ${HUMAN_FEAT_COUNT}"
echo "Human fix PRs:        ${HUMAN_FIX_COUNT}"
echo ""
echo "--- Regression Rate (fix/feat ratio) ---"
echo "  AI:    ${AI_REGRESSION_RATE} (${AI_FIX_COUNT} fixes / ${AI_FEAT_COUNT} feats)"
echo "  Human: ${HUMAN_REGRESSION_RATE} (${HUMAN_FIX_COUNT} fixes / ${HUMAN_FEAT_COUNT} feats)"
echo ""
echo "--- Time-to-Regression (avg hours, feat→fix on same files) ---"
echo "  AI:    ${AVG_TTR_HOURS}h (${TTR_COUNT} samples)"
echo ""
echo "--- PR Rejection Rate (CI failure on first commit) ---"
echo "  AI:    ${AI_REJECTION_RATE} (${AI_REJECTED}/${SAMPLE_AI_COUNT} sampled)"
echo ""

# --- JSON output ---
if [[ "$JSON_OUTPUT" == "true" ]]; then
  cat <<ENDJSON
{
  "period_days": ${DAYS},
  "total_prs": ${TOTAL_PRS},
  "ai_prs": ${AI_PR_COUNT},
  "human_prs": ${HUMAN_PR_COUNT},
  "ai_feat_prs": ${AI_FEAT_COUNT},
  "ai_fix_prs": ${AI_FIX_COUNT},
  "human_feat_prs": ${HUMAN_FEAT_COUNT},
  "human_fix_prs": ${HUMAN_FIX_COUNT},
  "ai_regression_rate": ${AI_REGRESSION_RATE},
  "human_regression_rate": ${HUMAN_REGRESSION_RATE},
  "ai_time_to_regression_hours": ${AVG_TTR_HOURS},
  "ai_ttr_samples": ${TTR_COUNT},
  "ai_rejection_rate": ${AI_REJECTION_RATE},
  "ai_rejected_samples": ${AI_REJECTED},
  "ai_sampled_total": ${SAMPLE_AI_COUNT}
}
ENDJSON
fi

# --- Push to Pushgateway ---
if [[ "$PUSH" == "true" ]]; then
  if [[ -z "$PUSHGATEWAY_URL" ]]; then
    echo "ERROR: --push requires PUSHGATEWAY_URL" >&2
    exit 1
  fi

  AUTH_HEADER=""
  if [[ -n "${PUSHGATEWAY_AUTH:-}" ]]; then
    AUTH_HEADER="-H 'Authorization: Basic ${PUSHGATEWAY_AUTH}'"
  fi

  METRICS_PAYLOAD=$(cat <<METRICS
# HELP ai_factory_regression_rate Ratio of fix PRs to feat PRs (lower is better)
# TYPE ai_factory_regression_rate gauge
ai_factory_regression_rate{source="ai"} ${AI_REGRESSION_RATE}
ai_factory_regression_rate{source="human"} ${HUMAN_REGRESSION_RATE}
# HELP ai_factory_time_to_regression_hours Average hours between feat merge and fix on same files
# TYPE ai_factory_time_to_regression_hours gauge
ai_factory_time_to_regression_hours{source="ai"} ${AVG_TTR_HOURS}
# HELP ai_factory_pr_rejection_rate Ratio of PRs with CI failures on first commit
# TYPE ai_factory_pr_rejection_rate gauge
ai_factory_pr_rejection_rate{source="ai"} ${AI_REJECTION_RATE}
# HELP ai_factory_prs_total Total merged PRs in the measurement window
# TYPE ai_factory_prs_total gauge
ai_factory_prs_total{source="ai",type="feat"} ${AI_FEAT_COUNT}
ai_factory_prs_total{source="ai",type="fix"} ${AI_FIX_COUNT}
ai_factory_prs_total{source="human",type="feat"} ${HUMAN_FEAT_COUNT}
ai_factory_prs_total{source="human",type="fix"} ${HUMAN_FIX_COUNT}
# HELP ai_factory_quality_last_run_timestamp Unix timestamp of last quality metrics run
# TYPE ai_factory_quality_last_run_timestamp gauge
ai_factory_quality_last_run_timestamp $(date +%s)
METRICS
)

  echo "Pushing metrics to Pushgateway..." >&2
  eval curl -sf ${AUTH_HEADER} --data-binary "'${METRICS_PAYLOAD}'" \
    "${PUSHGATEWAY_URL}/metrics/job/${JOB_NAME}" >/dev/null 2>&1 && \
    echo "Metrics pushed successfully." >&2 || \
    echo "WARNING: Failed to push metrics to Pushgateway." >&2
fi
