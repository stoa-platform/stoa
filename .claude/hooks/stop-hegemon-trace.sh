#!/usr/bin/env bash
# stop-hegemon-trace.sh — Push real session data to STOA Console dashboard
# Reads heg-state milestones + stats-cache.json, POSTs to /v1/traces/ingest.
# Runs on every session end (Stop hook). Always exits 0 (warn-only).
#
# Required env vars (graceful degradation if missing):
#   HEGEMON_INGEST_KEY  — API key for X-STOA-API-KEY header
#   HEGEMON_ROLE        — Worker role (backend, frontend, mcp, auth, qa)
#                         Falls back to STOA_INSTANCE, then "interactive"
#
# Optional:
#   STOA_API_URL        — API base URL (default: https://api.gostoa.dev)
#   HEGEMON_STATE_DB    — Path to state.db (default: ~/.hegemon/state.db)

set -euo pipefail

# --- Config ---
STOA_API_URL="${STOA_API_URL:-https://api.gostoa.dev}"
INGEST_ENDPOINT="${STOA_API_URL}/v1/traces/ingest"
STATS_FILE="$HOME/.claude/stats-cache.json"
STATE_DB="${HEGEMON_STATE_DB:-$HOME/.hegemon/state.db}"
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
TODAY="$(date -u +%Y-%m-%d)"

# --- Early exits ---
# No API key → skip silently
[ -z "${HEGEMON_INGEST_KEY:-}" ] && exit 0

# No state.db → skip silently
[ ! -f "$STATE_DB" ] && exit 0

# No jq or curl → skip silently
command -v jq &>/dev/null || exit 0
command -v curl &>/dev/null || exit 0

# --- Locate heg-state ---
HEG_STATE=""
if [ -x "${HOME}/.local/bin/heg-state" ]; then
  HEG_STATE="${HOME}/.local/bin/heg-state"
elif command -v heg-state &>/dev/null; then
  HEG_STATE="heg-state"
elif [ -n "$PROJECT_DIR" ] && [ -f "${PROJECT_DIR}/hegemon/tools/state/heg_state.py" ]; then
  HEG_STATE="python3 ${PROJECT_DIR}/hegemon/tools/state/heg_state.py"
fi
[ -z "$HEG_STATE" ] && exit 0

# --- Determine role ---
ROLE="${HEGEMON_ROLE:-${STOA_INSTANCE:-interactive}}"

# --- Extract ticket from current branch ---
cd "$PROJECT_DIR" 2>/dev/null || exit 0
BRANCH=$(git branch --show-current 2>/dev/null || echo "")
TICKET=""
if [ -n "$BRANCH" ]; then
  TICKET=$(echo "$BRANCH" | grep -oiE 'cab-[0-9]+' | head -1 | tr '[:lower:]' '[:upper:]' || true)
fi

# No ticket on branch → skip (nothing to report)
[ -z "$TICKET" ] && exit 0

# --- Query milestones from state.db ---
# Get milestones as JSON array using direct SQLite query (faster than CLI)
MILESTONES_JSON=$(sqlite3 -json "$STATE_DB" \
  "SELECT step, instance_id, pr, sha, detail, created_at
   FROM milestones WHERE ticket='$TICKET' ORDER BY created_at ASC" 2>/dev/null) || MILESTONES_JSON="[]"

# Get session info
SESSION_JSON=$(sqlite3 -json "$STATE_DB" \
  "SELECT role, step, pr, branch, started_at, updated_at
   FROM sessions WHERE ticket='$TICKET' LIMIT 1" 2>/dev/null) || SESSION_JSON="[]"

# If no milestones and no session, nothing to report
if [ "$MILESTONES_JSON" = "[]" ] && [ "$SESSION_JSON" = "[]" ]; then
  exit 0
fi

# Extract PR number from session or milestones
PR_NUM=$(echo "$SESSION_JSON" | jq -r '.[0].pr // empty' 2>/dev/null) || PR_NUM=""
if [ -z "$PR_NUM" ] || [ "$PR_NUM" = "null" ]; then
  PR_NUM=$(echo "$MILESTONES_JSON" | jq -r '[.[] | select(.pr != null)] | last | .pr // empty' 2>/dev/null) || PR_NUM=""
fi

# Extract session timestamps for duration
STARTED_AT=$(echo "$SESSION_JSON" | jq -r '.[0].started_at // empty' 2>/dev/null) || STARTED_AT=""
UPDATED_AT=$(echo "$SESSION_JSON" | jq -r '.[0].updated_at // empty' 2>/dev/null) || UPDATED_AT=""
CURRENT_STEP=$(echo "$SESSION_JSON" | jq -r '.[0].step // "unknown"' 2>/dev/null) || CURRENT_STEP="unknown"

# Calculate duration (ms)
TOTAL_DURATION_MS=""
if [ -n "$STARTED_AT" ] && [ -n "$UPDATED_AT" ]; then
  # Parse ISO timestamps to epoch seconds (macOS + GNU compatible)
  if date --version &>/dev/null 2>&1; then
    # GNU date
    START_EPOCH=$(date -d "$STARTED_AT" +%s 2>/dev/null) || START_EPOCH=""
    END_EPOCH=$(date -d "$UPDATED_AT" +%s 2>/dev/null) || END_EPOCH=""
  else
    # macOS date — convert ISO to something date -j understands
    START_EPOCH=$(date -jf "%Y-%m-%dT%H:%M:%SZ" "$STARTED_AT" +%s 2>/dev/null) || \
    START_EPOCH=$(date -jf "%Y-%m-%dT%H:%M:%S" "$STARTED_AT" +%s 2>/dev/null) || START_EPOCH=""
    END_EPOCH=$(date -jf "%Y-%m-%dT%H:%M:%SZ" "$UPDATED_AT" +%s 2>/dev/null) || \
    END_EPOCH=$(date -jf "%Y-%m-%dT%H:%M:%S" "$UPDATED_AT" +%s 2>/dev/null) || END_EPOCH=""
  fi
  if [ -n "$START_EPOCH" ] && [ -n "$END_EPOCH" ]; then
    TOTAL_DURATION_MS=$(( (END_EPOCH - START_EPOCH) * 1000 ))
    # Sanity check: negative or >24h → skip
    if [ "$TOTAL_DURATION_MS" -lt 0 ] || [ "$TOTAL_DURATION_MS" -gt 86400000 ]; then
      TOTAL_DURATION_MS=""
    fi
  fi
fi

# --- Determine session status ---
STATUS="success"
case "$CURRENT_STEP" in
  merged|done|cd-verified) STATUS="success" ;;
  ci-failed|blocked)       STATUS="failed" ;;
  paused|coding|pr-created|claimed) STATUS="success" ;;  # partial progress, not failure
esac

# --- Extract token/cost data from stats-cache.json ---
TOKENS_TOTAL=0
COST_USD="0.00"
MODEL="unknown"

if [ -f "$STATS_FILE" ]; then
  # Get today's daily tokens by model
  DAILY_JSON=$(jq -r --arg d "$TODAY" '
    (.dailyModelTokens // []) | map(select(.date == $d)) | .[0] // empty
  ' "$STATS_FILE" 2>/dev/null) || DAILY_JSON=""

  if [ -n "$DAILY_JSON" ] && [ "$DAILY_JSON" != "null" ]; then
    TOKENS_TOTAL=$(echo "$DAILY_JSON" | jq -r '.totalTokens // 0' 2>/dev/null) || TOKENS_TOTAL=0

    # Get primary model (highest token count)
    MODEL=$(echo "$DAILY_JSON" | jq -r '
      .tokensByModel // {} | to_entries | sort_by(.value) | reverse | .[0].key // "unknown"
    ' 2>/dev/null) || MODEL="unknown"

    # Simplified cost calculation using cumulative ratios
    MODEL_USAGE=$(jq -r '.modelUsage // {}' "$STATS_FILE" 2>/dev/null) || MODEL_USAGE="{}"
    TOKENS_BY_MODEL=$(echo "$DAILY_JSON" | jq -r '.tokensByModel // {} | to_entries[] | "\(.key)=\(.value)"' 2>/dev/null) || TOKENS_BY_MODEL=""

    if [ -n "$TOKENS_BY_MODEL" ]; then
      TOTAL_COST=0
      while IFS='=' read -r raw_model tokens; do
        # Get pricing
        short_model=$(echo "$raw_model" | sed 's/claude-//;s/-20[0-9]*//')
        case "$short_model" in
          opus-4-6)    PI=15;   PO=75;  PCR=1.50;  PCW=18.75 ;;
          sonnet-4-6)  PI=3;    PO=15;  PCR=0.30;  PCW=3.75 ;;
          sonnet-4-5)  PI=3;    PO=15;  PCR=0.30;  PCW=3.75 ;;
          haiku-4-5)   PI=0.80; PO=4;   PCR=0.08;  PCW=1 ;;
          *)           PI=3;    PO=15;  PCR=0.30;  PCW=3.75 ;;
        esac

        # Get cumulative ratios
        cum_in=$(echo "$MODEL_USAGE" | jq -r --arg m "$raw_model" '.[$m].inputTokens // 0' 2>/dev/null) || cum_in=0
        cum_out=$(echo "$MODEL_USAGE" | jq -r --arg m "$raw_model" '.[$m].outputTokens // 0' 2>/dev/null) || cum_out=0
        cum_cr=$(echo "$MODEL_USAGE" | jq -r --arg m "$raw_model" '.[$m].cacheReadInputTokens // 0' 2>/dev/null) || cum_cr=0
        cum_cw=$(echo "$MODEL_USAGE" | jq -r --arg m "$raw_model" '.[$m].cacheCreationInputTokens // 0' 2>/dev/null) || cum_cw=0
        cum_total=$((cum_in + cum_out + cum_cr + cum_cw))

        if [ "$cum_total" -gt 0 ]; then
          in_r=$(awk -v a="$cum_in" -v t="$cum_total" 'BEGIN { printf "%.4f", a/t }')
          out_r=$(awk -v a="$cum_out" -v t="$cum_total" 'BEGIN { printf "%.4f", a/t }')
          cr_r=$(awk -v a="$cum_cr" -v t="$cum_total" 'BEGIN { printf "%.4f", a/t }')
          cw_r=$(awk -v a="$cum_cw" -v t="$cum_total" 'BEGIN { printf "%.4f", a/t }')
        else
          in_r="0.40"; out_r="0.30"; cr_r="0.20"; cw_r="0.10"
        fi

        cost=$(awk -v t="$tokens" -v ir="$in_r" -v or="$out_r" -v crr="$cr_r" -v cwr="$cw_r" \
               -v pi="$PI" -v po="$PO" -v pcr="$PCR" -v pcw="$PCW" \
               'BEGIN { printf "%.4f", (t*ir*pi + t*or*po + t*crr*pcr + t*cwr*pcw) / 1000000 }')
        TOTAL_COST=$(awk -v a="$TOTAL_COST" -v b="$cost" 'BEGIN { printf "%.4f", a+b }')
      done <<< "$TOKENS_BY_MODEL"

      COST_USD=$(awk -v c="$TOTAL_COST" 'BEGIN { printf "%.2f", c }')
    fi
  fi
fi

# Get git author
GIT_AUTHOR=$(git config user.name 2>/dev/null || echo "hegemon-worker")

# --- Build steps array from milestones ---
# Convert milestones to ingest steps format.
# Filter out "paused" steps (noise from session-end hooks) and deduplicate
# consecutive same-step entries (keep last occurrence with most data).
STEPS_JSON=$(echo "$MILESTONES_JSON" | jq '
  [.[] | select(.step != "paused")] |
  reduce .[] as $m ([];
    if length > 0 and .[-1].step == $m.step then
      .[-1] = $m
    else
      . + [$m]
    end
  ) |
  [.[] | {
    name: .step,
    status: (if .step == "ci-failed" or .step == "blocked" then "failed" else "success" end),
    duration_ms: null,
    details: (
      (if .pr != null and .pr != "" then {pr: (.pr | tonumber? // .pr)} else {} end) +
      (if .sha != null and .sha != "" then {sha: .sha} else {} end) +
      (if .detail != null and .detail != "" then {detail: .detail} else {} end)
    ),
    error: (if .step == "ci-failed" then (.detail // "CI failed") elif .step == "blocked" then (.detail // "Blocked") else null end)
  }]
' 2>/dev/null) || STEPS_JSON="[]"

# --- Count files changed (from last commit or PR) ---
FILES_CHANGED=0
LOC=0
if [ -n "$PR_NUM" ] && [ "$PR_NUM" != "null" ]; then
  PR_STAT=$(gh pr diff "$PR_NUM" --stat 2>/dev/null | tail -1) || PR_STAT=""
  if [ -n "$PR_STAT" ]; then
    FILES_CHANGED=$(echo "$PR_STAT" | grep -oE '[0-9]+ files? changed' | grep -oE '[0-9]+' || echo "0")
    INSERTIONS=$(echo "$PR_STAT" | grep -oE '[0-9]+ insertions?' | grep -oE '[0-9]+' || echo "0")
    DELETIONS=$(echo "$PR_STAT" | grep -oE '[0-9]+ deletions?' | grep -oE '[0-9]+' || echo "0")
    LOC=$(( ${INSERTIONS:-0} + ${DELETIONS:-0} ))
  fi
fi

# Shorten model name for display
MODEL_SHORT=$(echo "$MODEL" | sed 's/claude-//;s/-20[0-9]*//')

# --- Build ingest payload ---
PAYLOAD=$(jq -n \
  --arg trigger_type "ai-session" \
  --arg trigger_source "hegemon-${ROLE}" \
  --arg tenant_id "hegemon" \
  --arg api_name "$TICKET" \
  --arg environment "production" \
  --arg git_branch "$BRANCH" \
  --arg git_author "$GIT_AUTHOR" \
  --argjson total_duration_ms "${TOTAL_DURATION_MS:-null}" \
  --arg status "$STATUS" \
  --argjson steps "$STEPS_JSON" \
  --argjson tokens_total "$TOKENS_TOTAL" \
  --arg cost_usd "$COST_USD" \
  --arg model "$MODEL_SHORT" \
  --arg worker_role "$ROLE" \
  --argjson files_changed "${FILES_CHANGED:-0}" \
  --argjson loc "${LOC:-0}" \
  --argjson pr_number "${PR_NUM:-null}" \
  --arg current_step "$CURRENT_STEP" \
  '{
    trigger_type: $trigger_type,
    trigger_source: $trigger_source,
    tenant_id: $tenant_id,
    api_name: $api_name,
    environment: $environment,
    git_branch: $git_branch,
    git_author: $git_author,
    total_duration_ms: $total_duration_ms,
    status: $status,
    steps: $steps,
    metadata: {
      total_tokens: $tokens_total,
      cost_usd: ($cost_usd | tonumber),
      model: $model,
      worker_role: $worker_role,
      files_changed: $files_changed,
      loc: $loc,
      pr_number: $pr_number,
      current_step: $current_step
    }
  }')

# --- Log rotation (500-line cap, 90-day retention on .1) ---
MEMORY_DIR="${HOME}/.claude/projects/-Users-torpedo-hlfh-repos-stoa/memory"
rotate_log() {
  local logfile="$1"
  [ ! -f "$logfile" ] && return
  local lines
  lines=$(wc -l < "$logfile" 2>/dev/null) || return
  if [ "$lines" -gt 500 ]; then
    local keep=$((lines - 500))
    head -n "$keep" "$logfile" >> "${logfile}.1"
    local tmp="${logfile}.tmp.$$"
    tail -n 500 "$logfile" > "$tmp" && mv "$tmp" "$logfile"
  fi
  # Purge .1 files older than 90 days
  if [ -f "${logfile}.1" ]; then
    find "$(dirname "${logfile}.1")" -name "$(basename "${logfile}.1")" -mtime +90 -delete 2>/dev/null || true
  fi
}
rotate_log "${MEMORY_DIR}/metrics.log"
rotate_log "${MEMORY_DIR}/operations.log"

# --- POST to ingest endpoint ---
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$INGEST_ENDPOINT" \
  -H "Content-Type: application/json" \
  -H "X-STOA-API-KEY: $HEGEMON_INGEST_KEY" \
  -d "$PAYLOAD" \
  --connect-timeout 5 \
  --max-time 10) || HTTP_CODE="000"

# Log result (best-effort, never fail)
if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "201" ]; then
  echo "[hegemon-trace] Pushed session trace for $TICKET (${ROLE}, ${STATUS})"
else
  echo "[hegemon-trace] Failed to push trace for $TICKET (HTTP $HTTP_CODE)" >&2
fi

exit 0
