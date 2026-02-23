#!/usr/bin/env bash
# AI Factory Notification Library — centralized Slack, Linear, GHA Job Summary
# Source this file: source scripts/ai-ops/ai-factory-notify.sh
# All functions are best-effort (never fail the parent step).
#
# Notification types:
#   notify_council    — Council validation report with approve button
#   notify_implement  — Implementation success/failure/ask with PR + metrics
#   notify_error      — Vercel-style error with log excerpt + retry button
#   notify_scan       — Autopilot scan summary with candidate count
#   notify_scheduled  — Daily/weekly task results with key metrics
#   notify_plan       — Stage 2 plan validation result
#   linear_comment    — Rich completion report posted to Linear ticket
#   write_job_summary — Structured markdown table in $GITHUB_STEP_SUMMARY
#
# Environment variables (all optional — graceful degradation):
#   SLACK_WEBHOOK           Incoming webhook URL (legacy, push-only)
#   SLACK_BOT_TOKEN         Bot API token (xoxb-...) — enables threading + updates
#   SLACK_CHANNEL_ID        Target channel for chat.postMessage (required with BOT_TOKEN)
#   SLACK_SIGNING_SECRET    Interactive payload HMAC validation (n8n only)
#   LINEAR_API_KEY          Linear API key for linear_comment()
#   N8N_WEBHOOK             n8n approve-ticket relay URL
#   N8N_MERGE_WEBHOOK       n8n merge-pr relay URL
#   HMAC_SECRET             HMAC secret for approve/merge button URLs
#   PUSHGATEWAY_URL         Prometheus Pushgateway URL for metrics push
#   PUSHGATEWAY_AUTH        Basic auth for Pushgateway (user:pass)
#
# Bot API path (SLACK_BOT_TOKEN + SLACK_CHANNEL_ID):
#   When both are set, notifications use chat.postMessage instead of webhooks.
#   This enables message threading, in-place updates, and interactive buttons.
#   Required bot scopes: chat:write, reactions:write, channels:read
#   Fallback: if BOT_TOKEN is unset, all functions use SLACK_WEBHOOK (no threading).

# ── Internal helpers ──────────────────────────────────────────────────────────

_linear_url() {
  echo "https://linear.app/cab-ing/issue/${1}"
}

_run_url() {
  echo "https://github.com/stoa-platform/stoa/actions/runs/${GITHUB_RUN_ID:-0}"
}

_retry_url() {
  # Build "Retry Workflow" button URL pointing to the GHA re-run page
  echo "https://github.com/stoa-platform/stoa/actions/runs/${GITHUB_RUN_ID:-0}/attempts"
}

_escape_json() {
  # Safe JSON string escaping; falls back to simple sed if python3 unavailable
  if command -v python3 &>/dev/null; then
    python3 -c "import json,sys; print(json.dumps(sys.stdin.read())[1:-1])" <<< "$1"
  else
    echo "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\t/\\t/g' | tr '\n' ' '
  fi
}

_approve_url() {
  # Build approve button URL: n8n HMAC relay if configured, else GitHub issue
  local ISSUE_NUM="$1"
  local FALLBACK_URL="$2"
  if [ -n "${N8N_WEBHOOK:-}" ] && [ -n "${HMAC_SECRET:-}" ] && [ -n "$ISSUE_NUM" ]; then
    local HMAC
    HMAC=$(echo -n "$ISSUE_NUM" | openssl dgst -sha256 -hmac "$HMAC_SECRET" | awk '{print $NF}')
    echo "${N8N_WEBHOOK}?issue=${ISSUE_NUM}&token=${HMAC}"
  else
    echo "$FALLBACK_URL"
  fi
}

_merge_url() {
  # Build merge button URL: n8n HMAC relay if configured, else PR URL fallback
  local PR_NUM="$1"
  local FALLBACK_URL="$2"
  if [ -n "${N8N_MERGE_WEBHOOK:-}" ] && [ -n "${HMAC_SECRET:-}" ] && [ -n "$PR_NUM" ]; then
    local HMAC
    HMAC=$(echo -n "$PR_NUM" | openssl dgst -sha256 -hmac "$HMAC_SECRET" | awk '{print $NF}')
    echo "${N8N_MERGE_WEBHOOK}?pr=${PR_NUM}&token=${HMAC}"
  else
    echo "$FALLBACK_URL"
  fi
}

_format_duration() {
  # Convert seconds to human-readable "Xm Ys" format
  local SECS="${1:-0}"
  if [ "$SECS" -le 0 ] 2>/dev/null; then
    echo ""
    return
  fi
  local MINS=$((SECS / 60))
  local REMAINING=$((SECS % 60))
  if [ "$MINS" -gt 0 ]; then
    echo "${MINS}m ${REMAINING}s"
  else
    echo "${REMAINING}s"
  fi
}

_extract_error() {
  # Extract last 500 chars of error from Claude execution output file
  local EXEC_FILE="${1:-}"
  local EXCERPT=""
  if [ -n "$EXEC_FILE" ] && [ -f "$EXEC_FILE" ]; then
    # Try .result field
    EXCERPT=$(jq -r '.[] | select(.type == "result") | .result // empty' "$EXEC_FILE" 2>/dev/null | tail -c 500 || true)
    # Fallback: assistant text
    if [ -z "$EXCERPT" ]; then
      EXCERPT=$(jq -r '[.[] | select(.type == "assistant") | .message.content[] | select(.type == "text") | .text] | join("\n")' "$EXEC_FILE" 2>/dev/null | tail -c 500 || true)
    fi
  fi
  # Fallback: step output (if set as env var)
  if [ -z "$EXCERPT" ] && [ -n "${STEP_OUTPUT:-}" ]; then
    EXCERPT=$(echo "$STEP_OUTPUT" | tail -c 500)
  fi
  echo "${EXCERPT:-No error details available.}"
}

_send_slack() {
  # Internal: send Block Kit payload to Slack via Bot API or webhook fallback.
  # When SLACK_BOT_TOKEN + SLACK_CHANNEL_ID are set, uses chat.postMessage (enables
  # threading + updates). Otherwise falls back to SLACK_WEBHOOK (legacy, push-only).
  # $1 = JSON payload (with "blocks" key)
  # $2 = optional thread_ts (only effective with Bot API path)
  # stdout: message timestamp (ts) when Bot API is used (empty for webhook)
  local PAYLOAD="$1"
  local THREAD_TS="${2:-${SLACK_THREAD_TS:-}}"

  # Bot API path — chat.postMessage with threading support
  if [ -n "${SLACK_BOT_TOKEN:-}" ] && [ -n "${SLACK_CHANNEL_ID:-}" ]; then
    _send_slack_bot "$PAYLOAD" "$THREAD_TS"
    return $?
  fi

  # Webhook fallback (existing behavior — no threading, no updates)
  if [ -z "${SLACK_WEBHOOK:-}" ]; then
    echo "::notice::Slack not configured — skipping notification"
    return 0
  fi
  curl -sf -X POST "$SLACK_WEBHOOK" \
    -H 'Content-Type: application/json' \
    -d "$PAYLOAD" > /dev/null 2>&1 || {
    echo "::warning::Slack notification failed (non-blocking)"
    return 0
  }
}

_send_slack_bot() {
  # Internal: send Block Kit payload via Slack chat.postMessage (Bot API).
  # $1 = JSON payload (with "blocks" key)
  # $2 = optional thread_ts for threading
  # stdout: message timestamp (ts) for threading/updates
  # Requires: SLACK_BOT_TOKEN, SLACK_CHANNEL_ID, jq
  local PAYLOAD="$1"
  local THREAD_TS="${2:-}"

  # Guard: jq required for JSON manipulation
  if ! command -v jq &>/dev/null; then
    echo "::warning::jq not available — falling back to webhook" >&2
    if [ -n "${SLACK_WEBHOOK:-}" ]; then
      curl -sf -X POST "$SLACK_WEBHOOK" \
        -H 'Content-Type: application/json' \
        -d "$PAYLOAD" > /dev/null 2>&1 || true
    fi
    return 0
  fi

  # Build chat.postMessage payload: inject channel (and thread_ts if provided)
  local BOT_PAYLOAD
  BOT_PAYLOAD=$(echo "$PAYLOAD" | jq --arg ch "$SLACK_CHANNEL_ID" --arg ts "$THREAD_TS" \
    '. + {channel: $ch} | if $ts != "" then . + {thread_ts: $ts} else . end' 2>/dev/null)

  if [ -z "$BOT_PAYLOAD" ]; then
    echo "::warning::Failed to build Bot API payload — falling back to webhook" >&2
    if [ -n "${SLACK_WEBHOOK:-}" ]; then
      curl -sf -X POST "$SLACK_WEBHOOK" \
        -H 'Content-Type: application/json' \
        -d "$PAYLOAD" > /dev/null 2>&1 || true
    fi
    return 0
  fi

  # Send via Bot API
  local RESPONSE
  RESPONSE=$(curl -sf -X POST "https://slack.com/api/chat.postMessage" \
    -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
    -H 'Content-Type: application/json' \
    -d "$BOT_PAYLOAD" 2>/dev/null) || {
    echo "::warning::Slack Bot API call failed (non-blocking)" >&2
    return 0
  }

  # Extract and return message timestamp for threading/updates
  local TS
  TS=$(echo "$RESPONSE" | jq -r '.ts // empty' 2>/dev/null)
  if [ -n "$TS" ]; then
    echo "$TS"
  fi
  return 0
}

_update_slack() {
  # Internal: update an existing Slack message via chat.update (Bot API).
  # No-op if ts is empty or Bot API not configured (graceful degradation).
  # $1 = message timestamp (ts) of the message to update
  # $2 = new JSON payload (with "blocks" key)
  local TS="${1:-}"
  local PAYLOAD="${2:-}"

  # No-op guards
  if [ -z "$TS" ] || [ -z "${SLACK_BOT_TOKEN:-}" ] || [ -z "${SLACK_CHANNEL_ID:-}" ]; then
    return 0
  fi
  if ! command -v jq &>/dev/null; then
    echo "::warning::jq not available — skipping message update" >&2
    return 0
  fi

  local UPDATE_PAYLOAD
  UPDATE_PAYLOAD=$(echo "$PAYLOAD" | jq --arg ch "$SLACK_CHANNEL_ID" --arg ts "$TS" \
    '. + {channel: $ch, ts: $ts}' 2>/dev/null)

  curl -sf -X POST "https://slack.com/api/chat.update" \
    -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
    -H 'Content-Type: application/json' \
    -d "$UPDATE_PAYLOAD" > /dev/null 2>&1 || {
    echo "::warning::Slack message update failed (non-blocking)" >&2
  }
  return 0
}

_reply_slack() {
  # Internal: reply in a Slack thread via chat.postMessage with thread_ts.
  # Wrapper around _send_slack_bot(). Falls back to top-level if parent_ts empty.
  # $1 = parent message timestamp (ts)
  # $2 = JSON payload (with "blocks" key)
  # stdout: reply message timestamp (ts)
  local PARENT_TS="${1:-}"
  local PAYLOAD="${2:-}"

  if [ -z "$PARENT_TS" ]; then
    # No parent thread — send as top-level message
    _send_slack "$PAYLOAD"
    return $?
  fi

  _send_slack_bot "$PAYLOAD" "$PARENT_TS"
}

_react_slack() {
  # Internal: add an emoji reaction to a Slack message via reactions.add.
  # No-op if Bot API not configured or ts is empty (graceful degradation).
  # $1 = emoji name (without colons, e.g., "rocket")
  # $2 = message timestamp (ts) to react to
  local EMOJI="${1:-}"
  local MESSAGE_TS="${2:-}"

  # No-op guards
  if [ -z "$EMOJI" ] || [ -z "$MESSAGE_TS" ]; then
    return 0
  fi
  if [ -z "${SLACK_BOT_TOKEN:-}" ] || [ -z "${SLACK_CHANNEL_ID:-}" ]; then
    return 0
  fi

  curl -sf -X POST "https://slack.com/api/reactions.add" \
    -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
    -H 'Content-Type: application/json' \
    -d "{\"channel\":\"$SLACK_CHANNEL_ID\",\"name\":\"$EMOJI\",\"timestamp\":\"$MESSAGE_TS\"}" \
    > /dev/null 2>&1 || {
    echo "::warning::Slack reaction failed (non-blocking)" >&2
  }
  return 0
}

_push_metrics() {
  # Internal: push Prometheus text format metrics to Pushgateway.
  # Graceful degradation if PUSHGATEWAY_URL is unset.
  # $1 = job path suffix (e.g., "workflow/linear-dispatch/stage/council")
  # $2 = metrics text (Prometheus exposition format)
  local JOB_PATH="${1:?}" METRICS_TEXT="${2:?}"
  if [ -z "${PUSHGATEWAY_URL:-}" ]; then
    echo "::notice::PUSHGATEWAY_URL not configured — skipping metrics push"
    return 0
  fi
  local PUSH_URL="${PUSHGATEWAY_URL}/metrics/job/ai_factory/${JOB_PATH}"
  local HTTP_CODE
  if [ -n "${PUSHGATEWAY_AUTH:-}" ]; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X PUT \
      --data-binary "$METRICS_TEXT" \
      -H "Content-Type: text/plain" \
      -u "${PUSHGATEWAY_AUTH}" "$PUSH_URL" 2>/dev/null)
  else
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X PUT \
      --data-binary "$METRICS_TEXT" \
      -H "Content-Type: text/plain" \
      "$PUSH_URL" 2>/dev/null)
  fi
  # Retry without auth if server rejects Basic Auth (IP-whitelisted setup)
  if [ "${HTTP_CODE:-000}" = "400" ] && [ -n "${PUSHGATEWAY_AUTH:-}" ]; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X PUT \
      --data-binary "$METRICS_TEXT" \
      -H "Content-Type: text/plain" \
      "$PUSH_URL" 2>/dev/null)
  fi
  [ -z "$HTTP_CODE" ] && HTTP_CODE="000"
  if [ "$HTTP_CODE" -ge 300 ] || [ "$HTTP_CODE" = "000" ]; then
    echo "::warning::Pushgateway returned HTTP ${HTTP_CODE} (non-blocking)"
  fi
  return 0
}

# ── Public functions ──────────────────────────────────────────────────────────

# notify_council TICKET_ID TITLE SCORE VERDICT ISSUE_URL [ISSUE_NUM] [MODE] [LOC] [FILES]
# Sends Council validation report to Slack with approve button + Linear link.
# MODE: Ship|Show|Ask (optional, shown in detail line)
# LOC: estimated lines of code (optional)
# FILES: number of files affected (optional)
notify_council() {
  local TICKET_ID="${1:?}" TITLE="${2:?}" SCORE="${3:-?}" VERDICT="${4:-Go}"
  local ISSUE_URL="${5:-}" ISSUE_NUM="${6:-}"
  local MODE="${7:-}" LOC="${8:-}" FILES="${9:-}"
  local LINEAR_LINK="$(_linear_url "$TICKET_ID")"
  local RUN_LINK="$(_run_url)"

  # Determine emoji
  local EMOJI=":white_check_mark:"
  case "$VERDICT" in
    Fix|fix) EMOJI=":warning:" ;;
    Redo|redo) EMOJI=":x:" ;;
  esac

  # Build approve button
  local APPROVE_BTN_URL
  APPROVE_BTN_URL=$(_approve_url "$ISSUE_NUM" "$ISSUE_URL")
  local BTN_TEXT="Review \\u0026 Approve"
  if [ -n "${N8N_WEBHOOK:-}" ] && [ -n "${HMAC_SECRET:-}" ] && [ -n "$ISSUE_NUM" ]; then
    BTN_TEXT="Approve \\u0026 Start"
  fi

  local ESCAPED_TITLE
  ESCAPED_TITLE=$(_escape_json "$TITLE")

  # Build optional detail line: "Ship mode | ~150 LOC | 3 files"
  local DETAIL_LINE=""
  local PARTS=()
  [ -n "$MODE" ] && PARTS+=("${MODE} mode")
  [ -n "$LOC" ] && PARTS+=("~${LOC} LOC")
  [ -n "$FILES" ] && PARTS+=("${FILES} files")
  if [ ${#PARTS[@]} -gt 0 ]; then
    local IFS=" | "
    DETAIL_LINE="\n${PARTS[*]}"
  fi

  _send_slack "{
    \"blocks\": [
      {
        \"type\": \"header\",
        \"text\": {\"type\": \"plain_text\", \"text\": \"${EMOJI} Council: ${TICKET_ID} — ${SCORE}/10 ${VERDICT}\", \"emoji\": true}
      },
      {
        \"type\": \"section\",
        \"text\": {
          \"type\": \"mrkdwn\",
          \"text\": \"*${ESCAPED_TITLE}*${DETAIL_LINE}\n\n<${LINEAR_LINK}|Linear> | <${RUN_LINK}|GHA Run>\"
        },
        \"accessory\": {
          \"type\": \"button\",
          \"text\": {\"type\": \"plain_text\", \"text\": \"${BTN_TEXT}\"},
          \"url\": \"${APPROVE_BTN_URL:-$ISSUE_URL}\",
          \"style\": \"primary\"
        }
      },
      {
        \"type\": \"context\",
        \"elements\": [{\"type\": \"mrkdwn\", \"text\": \"STOA AI Factory | L3 Pipeline | $(date -u +%H:%M) UTC\"}]
      }
    ]
  }"
}

# notify_implement TICKET_ID STATUS [PR_NUM] [PR_URL] [ISSUE_NUM] [PIPELINE] [DURATION_SECS] [FILES] [LOC]
# STATUS: success|failure|ask|skipped
# DURATION_SECS: elapsed seconds (from $SECONDS). Shown as "Duration: Xm Ys".
# FILES: number of changed files (optional)
# LOC: lines of code changed (optional)
notify_implement() {
  local TICKET_ID="${1:?}" STATUS="${2:?}"
  local PR_NUM="${3:-}" PR_URL="${4:-}" ISSUE_NUM="${5:-}" PIPELINE="${6:-L3 Pipeline}"
  local DURATION_SECS="${7:-}" FILES="${8:-}" LOC="${9:-}"
  local LINEAR_LINK="$(_linear_url "$TICKET_ID")"
  local RUN_LINK="$(_run_url)"

  # Build optional metrics line: "3 files, ~120 LOC | Duration: 12m 34s"
  local METRICS=""
  local MPARTS=()
  [ -n "$FILES" ] && [ "$FILES" != "0" ] && MPARTS+=("${FILES} files")
  [ -n "$LOC" ] && [ "$LOC" != "0" ] && MPARTS+=("~${LOC} LOC")
  local DURATION_FMT
  DURATION_FMT=$(_format_duration "$DURATION_SECS")
  [ -n "$DURATION_FMT" ] && MPARTS+=("Duration: ${DURATION_FMT}")
  if [ ${#MPARTS[@]} -gt 0 ]; then
    local IFS=" | "
    METRICS="\n${MPARTS[*]}"
  fi

  local MSG=""
  case "$STATUS" in
    success)
      if [ -n "$PR_NUM" ]; then
        MSG=":tada: *${TICKET_ID}* completed — PR <${PR_URL}|#${PR_NUM}> merged${METRICS}\n<${LINEAR_LINK}|Linear> → Done"
      else
        MSG=":white_check_mark: *${TICKET_ID}* implementation complete${METRICS}\n<${LINEAR_LINK}|Linear>"
      fi
      ;;
    ask)
      local MERGE_BTN_URL
      MERGE_BTN_URL=$(_merge_url "$PR_NUM" "${PR_URL:-}")
      _send_slack "{
        \"blocks\": [
          {\"type\":\"header\",\"text\":{\"type\":\"plain_text\",\"text\":\":eyes: Ask Mode — Review Required\",\"emoji\":true}},
          {\"type\":\"section\",\"text\":{\"type\":\"mrkdwn\",\"text\":\"*${TICKET_ID}* — PR <${PR_URL}|#${PR_NUM}> created${METRICS}\n<${LINEAR_LINK}|Linear> | <$(_run_url)|GHA Run>\"}},
          {\"type\":\"actions\",\"elements\":[
            {\"type\":\"button\",\"text\":{\"type\":\"plain_text\",\"text\":\"Review PR\"},\"url\":\"${PR_URL}\"},
            {\"type\":\"button\",\"text\":{\"type\":\"plain_text\",\"text\":\":white_check_mark: Merge PR\",\"emoji\":true},\"url\":\"${MERGE_BTN_URL}\",\"style\":\"primary\"}
          ]},
          {\"type\":\"context\",\"elements\":[{\"type\":\"mrkdwn\",\"text\":\"STOA AI Factory | ${PIPELINE} | $(date -u +%H:%M) UTC\"}]}
        ]
      }"
      return 0
      ;;
    failure)
      MSG=":x: *${TICKET_ID}* implementation failed${METRICS}\n<${RUN_LINK}|View Logs> | <${LINEAR_LINK}|Linear>"
      ;;
    skipped)
      MSG=":warning: *${TICKET_ID}* implementation skipped. <${RUN_LINK}|View Logs>"
      ;;
  esac

  _send_slack "{
    \"blocks\": [
      {\"type\":\"section\",\"text\":{\"type\":\"mrkdwn\",\"text\":\"${MSG}\"}},
      {\"type\":\"context\",\"elements\":[{\"type\":\"mrkdwn\",\"text\":\"STOA AI Factory | ${PIPELINE} | $(date -u +%H:%M) UTC\"}]}
    ]
  }"
}

# notify_error WORKFLOW JOB [TICKET_ID] [EXEC_FILE] [DURATION_SECS]
# Vercel-style error report with log excerpt + View Full Logs + Retry Workflow buttons.
notify_error() {
  local WORKFLOW="${1:?}" JOB="${2:?}"
  local TICKET_ID="${3:-}" EXEC_FILE="${4:-}" DURATION_SECS="${5:-}"
  local RUN_LINK="$(_run_url)"
  local RETRY_LINK="$(_retry_url)"
  local LINEAR_REF=""
  [ -n "$TICKET_ID" ] && LINEAR_REF=" | <$(_linear_url "$TICKET_ID")|Linear>"

  local EXCERPT
  EXCERPT=$(_extract_error "$EXEC_FILE")
  local ESCAPED_EXCERPT
  ESCAPED_EXCERPT=$(_escape_json "$EXCERPT")

  # Optional duration line
  local DURATION_LINE=""
  local DURATION_FMT
  DURATION_FMT=$(_format_duration "$DURATION_SECS")
  [ -n "$DURATION_FMT" ] && DURATION_LINE="\n*Duration*: ${DURATION_FMT}"

  _send_slack "{
    \"blocks\": [
      {
        \"type\": \"header\",
        \"text\": {\"type\": \"plain_text\", \"text\": \":rotating_light: AI Factory Error\", \"emoji\": true}
      },
      {
        \"type\": \"section\",
        \"text\": {
          \"type\": \"mrkdwn\",
          \"text\": \"*Workflow*: ${WORKFLOW}\n*Job*: ${JOB}${TICKET_ID:+\n*Ticket*: ${TICKET_ID}}${DURATION_LINE}\n\n\`\`\`${ESCAPED_EXCERPT}\`\`\`\"
        }
      },
      {
        \"type\": \"actions\",
        \"elements\": [
          {\"type\":\"button\",\"text\":{\"type\":\"plain_text\",\"text\":\"View Full Logs\"},\"url\":\"${RUN_LINK}\"},
          {\"type\":\"button\",\"text\":{\"type\":\"plain_text\",\"text\":\"Retry Workflow\"},\"url\":\"${RETRY_LINK}\"}
        ]
      },
      {
        \"type\": \"context\",
        \"elements\": [{\"type\": \"mrkdwn\", \"text\": \"Run #${GITHUB_RUN_NUMBER:-?} | $(date -u +%H:%M) UTC${LINEAR_REF}\"}]
      }
    ]
  }"
}

# notify_scan TOTAL_ELIGIBLE CREATED [CAPPED]
# Autopilot scan summary notification.
notify_scan() {
  local TOTAL="${1:-0}" CREATED="${2:-0}" CAPPED="${3:-false}"
  local RUN_LINK="$(_run_url)"

  local MSG=""
  if [ "$CAPPED" = "true" ]; then
    MSG=":pause_button: Autopilot scan skipped — daily velocity cap reached."
  elif [ "$TOTAL" = "0" ]; then
    MSG=":inbox_tray: Autopilot scan complete — no eligible tickets in backlog."
  elif [ "$CREATED" = "0" ]; then
    MSG=":mag: Autopilot scan — ${TOTAL} eligible tickets found (dry run, no issues created)."
  else
    MSG=":sunrise: Autopilot scan complete — ${CREATED}/${TOTAL} candidates dispatched. <${RUN_LINK}|Details>"
  fi

  _send_slack "{
    \"blocks\": [
      {\"type\":\"section\",\"text\":{\"type\":\"mrkdwn\",\"text\":\"${MSG}\"}},
      {\"type\":\"context\",\"elements\":[{\"type\":\"mrkdwn\",\"text\":\"STOA AI Factory | Autopilot Scan | $(date -u +%H:%M) UTC\"}]}
    ]
  }"
}

# notify_scheduled TASK_NAME STATUS [DETAILS]
# Notification for daily/weekly scheduled tasks.
notify_scheduled() {
  local TASK="${1:?}" STATUS="${2:?}" DETAILS="${3:-}"
  local RUN_LINK="$(_run_url)"

  local EMOJI=":white_check_mark:"
  [ "$STATUS" != "success" ] && EMOJI=":warning:"

  local DETAIL_LINE=""
  if [ -n "$DETAILS" ]; then
    local ESCAPED_DETAILS
    ESCAPED_DETAILS=$(_escape_json "$DETAILS")
    DETAIL_LINE="\n${ESCAPED_DETAILS}"
  fi

  _send_slack "{
    \"blocks\": [
      {\"type\":\"section\",\"text\":{\"type\":\"mrkdwn\",\"text\":\"${EMOJI} *${TASK}* — ${STATUS}${DETAIL_LINE}\n<${RUN_LINK}|View Run>\"}},
      {\"type\":\"context\",\"elements\":[{\"type\":\"mrkdwn\",\"text\":\"STOA AI Factory | Scheduled | $(date -u +%H:%M) UTC\"}]}
    ]
  }"
}

# notify_pr_hygiene TOTAL STALE ABANDONED DRAFT
# PR Hygiene daily report with optional close button.
notify_pr_hygiene() {
  local TOTAL="${1:-0}" STALE="${2:-0}" ABANDONED="${3:-0}" DRAFT="${4:-0}"

  # Severity emoji
  local EMOJI=":large_green_circle:"
  if [ "${ABANDONED}" -gt 0 ]; then
    EMOJI=":red_circle:"
  elif [ "${STALE}" -gt 0 ]; then
    EMOJI=":large_yellow_circle:"
  fi

  local DATE
  DATE=$(date -u +%Y-%m-%d)
  local RUN_LINK="https://github.com/${GITHUB_REPOSITORY:-stoa-platform/stoa}/actions/runs/${GITHUB_RUN_ID:-0}"

  # Build actions block if abandoned > 0
  local ACTIONS_BLOCK=""
  if [ "${ABANDONED}" -gt 0 ]; then
    ACTIONS_BLOCK=",{\"type\":\"actions\",\"elements\":[{\"type\":\"button\",\"text\":{\"type\":\"plain_text\",\"text\":\"Close Abandoned PRs\"},\"style\":\"danger\",\"action_id\":\"close_abandoned_prs\",\"confirm\":{\"title\":{\"type\":\"plain_text\",\"text\":\"Close Abandoned PRs?\"},\"text\":{\"type\":\"mrkdwn\",\"text\":\"This will close all ${ABANDONED} PRs labelled \`abandoned\`.\"},\"confirm\":{\"type\":\"plain_text\",\"text\":\"Close them\"},\"deny\":{\"type\":\"plain_text\",\"text\":\"Cancel\"}}}]}"
  fi

  _send_slack "{
    \"blocks\": [
      {\"type\":\"section\",\"text\":{\"type\":\"mrkdwn\",\"text\":\"${EMOJI} *PR Hygiene Report — ${DATE}*\n<${RUN_LINK}|View Run>\"}},
      {\"type\":\"section\",\"fields\":[
        {\"type\":\"mrkdwn\",\"text\":\"*Total Open*\n${TOTAL}\"},
        {\"type\":\"mrkdwn\",\"text\":\"*Stale*\n${STALE}\"},
        {\"type\":\"mrkdwn\",\"text\":\"*Abandoned*\n${ABANDONED}\"},
        {\"type\":\"mrkdwn\",\"text\":\"*Draft*\n${DRAFT}\"}
      ]}
      ${ACTIONS_BLOCK},
      {\"type\":\"context\",\"elements\":[{\"type\":\"mrkdwn\",\"text\":\"STOA AI Factory | Scheduled | $(date -u +%H:%M) UTC\"}]}
    ]
  }"
}

# push_metrics_pr_hygiene TOTAL STALE ABANDONED DRAFT
# Push PR hygiene gauge metrics to Pushgateway.
push_metrics_pr_hygiene() {
  local TOTAL="${1:-0}" STALE="${2:-0}" ABANDONED="${3:-0}" DRAFT="${4:-0}"
  local METRICS=""
  METRICS+="# HELP ai_factory_pr_hygiene PR hygiene gauge by type\n"
  METRICS+="# TYPE ai_factory_pr_hygiene gauge\n"
  METRICS+="ai_factory_pr_hygiene{type=\"total\"} ${TOTAL}\n"
  METRICS+="ai_factory_pr_hygiene{type=\"stale\"} ${STALE}\n"
  METRICS+="ai_factory_pr_hygiene{type=\"abandoned\"} ${ABANDONED}\n"
  METRICS+="ai_factory_pr_hygiene{type=\"draft\"} ${DRAFT}\n"
  _push_metrics "workflow/scheduled/stage/pr-hygiene" "$(printf '%b' "$METRICS")"
}

# notify_plan ISSUE_NUM ISSUE_TITLE ISSUE_URL STATUS
# Stage 2 plan validation result.
notify_plan() {
  local ISSUE_NUM="${1:?}" ISSUE_TITLE="${2:?}" ISSUE_URL="${3:?}" STATUS="${4:?}"

  local EMOJI=":clipboard:" TEXT=""
  if [ "$STATUS" = "success" ]; then
    TEXT="Stage 2 plan validation passed.\nComment \`/go-plan\` to start implementation."
  else
    EMOJI=":warning:"
    TEXT="Stage 2 plan validation failed. Check the GitHub issue for details."
  fi

  local ESCAPED_TITLE
  ESCAPED_TITLE=$(_escape_json "$ISSUE_TITLE")

  _send_slack "{
    \"blocks\": [
      {\"type\":\"header\",\"text\":{\"type\":\"plain_text\",\"text\":\"${EMOJI} Plan Validation: #${ISSUE_NUM}\",\"emoji\":true}},
      {\"type\":\"section\",\"text\":{\"type\":\"mrkdwn\",\"text\":\"*${ESCAPED_TITLE}*\n${TEXT}\"},\"accessory\":{\"type\":\"button\",\"text\":{\"type\":\"plain_text\",\"text\":\"Review Plan\"},\"url\":\"${ISSUE_URL}\"}},
      {\"type\":\"context\",\"elements\":[{\"type\":\"mrkdwn\",\"text\":\"STOA AI Factory | L3 Pipeline | $(date -u +%H:%M) UTC\"}]}
    ]
  }"
}

# ── Linear integration ────────────────────────────────────────────────────────

# linear_comment TICKET_ID STATUS [PR_NUM] [PR_URL] [PIPELINE] [DURATION_SECS] [FILES] [LOC] [MODE]
# Post rich completion report to Linear ticket. Requires LINEAR_API_KEY env var.
linear_comment() {
  local TICKET_ID="${1:?}" STATUS="${2:?}"
  local PR_NUM="${3:-}" PR_URL="${4:-}" PIPELINE="${5:-L3 Pipeline}"
  local DURATION_SECS="${6:-}" FILES="${7:-}" LOC="${8:-}" MODE="${9:-Ship}"

  if [ -z "${LINEAR_API_KEY:-}" ]; then
    echo "::notice::LINEAR_API_KEY not set — skipping Linear comment"
    return 0
  fi

  # Build rich markdown report
  local DURATION_FMT
  DURATION_FMT=$(_format_duration "$DURATION_SECS")

  local BODY="## AI Factory Report\n\n"
  BODY+="**Status**: ${STATUS}\n"
  [ -n "$PR_NUM" ] && BODY+="**PR**: [#${PR_NUM}](${PR_URL})\n"
  if [ -n "$FILES" ] || [ -n "$LOC" ]; then
    local CHANGES=""
    [ -n "$FILES" ] && [ "$FILES" != "0" ] && CHANGES="${FILES} files"
    [ -n "$LOC" ] && [ "$LOC" != "0" ] && CHANGES="${CHANGES:+${CHANGES}, }~${LOC} LOC"
    [ -n "$CHANGES" ] && BODY+="**Changes**: ${CHANGES}\n"
  fi
  [ -n "$DURATION_FMT" ] && BODY+="**Duration**: ${DURATION_FMT}\n"
  BODY+="**Mode**: ${MODE} (auto-merged)\n"
  BODY+="\n*Auto-generated by STOA AI Factory ${PIPELINE}*"

  local ESCAPED_BODY
  ESCAPED_BODY=$(_escape_json "$BODY")

  # Resolve Linear issue ID
  local ISSUE_ID
  ISSUE_ID=$(curl -sf -X POST "https://api.linear.app/graphql" \
    -H "Authorization: ${LINEAR_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "{\"query\": \"{ issueSearch(filter: { identifier: { eq: \\\"${TICKET_ID}\\\" } }) { nodes { id } } }\"}" \
    | jq -r '.data.issueSearch.nodes[0].id // empty' 2>/dev/null || echo "")

  if [ -z "$ISSUE_ID" ]; then
    echo "::warning::Could not find Linear issue for ${TICKET_ID}"
    return 0
  fi

  curl -sf -X POST "https://api.linear.app/graphql" \
    -H "Authorization: ${LINEAR_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "{\"query\": \"mutation { commentCreate(input: { issueId: \\\"${ISSUE_ID}\\\", body: \\\"${ESCAPED_BODY}\\\" }) { success } }\"}" \
    > /dev/null 2>&1 || true
}

# ── GHA Job Summary ───────────────────────────────────────────────────────────

# write_job_summary TICKET_ID STATUS [PR_NUM] [MODEL] [PIPELINE] [DURATION_SECS] [ERROR_EXCERPT]
# Write structured markdown table to $GITHUB_STEP_SUMMARY.
write_job_summary() {
  local TICKET_ID="${1:?}" STATUS="${2:?}"
  local PR_NUM="${3:-}" MODEL="${4:-}" PIPELINE="${5:-}"
  local DURATION_SECS="${6:-}" ERROR_EXCERPT="${7:-}"

  if [ -z "${GITHUB_STEP_SUMMARY:-}" ]; then
    echo "::notice::GITHUB_STEP_SUMMARY not set — skipping job summary"
    return 0
  fi

  local LINEAR_LINK="$(_linear_url "$TICKET_ID")"
  local RUN_LINK="$(_run_url)"
  local DURATION_FMT
  DURATION_FMT=$(_format_duration "$DURATION_SECS")

  {
    echo "## AI Factory: ${PIPELINE:-implement}"
    echo ""
    echo "| Field | Value |"
    echo "|-------|-------|"
    echo "| Ticket | [${TICKET_ID}](${LINEAR_LINK}) |"
    echo "| Status | ${STATUS} |"
    [ -n "$PR_NUM" ] && echo "| PR | #${PR_NUM} |"
    [ -n "$DURATION_FMT" ] && echo "| Duration | ${DURATION_FMT} |"
    [ -n "$MODEL" ] && echo "| Model | ${MODEL} |"
    echo "| Run | [#${GITHUB_RUN_NUMBER:-?}](${RUN_LINK}) |"
    echo ""
    # Append error section if present
    if [ -n "$ERROR_EXCERPT" ]; then
      echo "### Error"
      echo ""
      echo '```'
      echo "$ERROR_EXCERPT"
      echo '```'
      echo ""
    fi
  } >> "$GITHUB_STEP_SUMMARY"
}

# ── Prometheus Metrics Push ──────────────────────────────────────────────────

# push_metrics_council WORKFLOW TICKET_ID SCORE VERDICT
# Push Council validation metrics to Pushgateway.
push_metrics_council() {
  local WORKFLOW="${1:-unknown}" TICKET_ID="${2:-}" SCORE="${3:-0}" VERDICT="${4:-unknown}"
  local STAGE="council"
  local METRICS=""
  METRICS+="# HELP ai_factory_council_score Council validation score (0-10)\n"
  METRICS+="# TYPE ai_factory_council_score gauge\n"
  METRICS+="ai_factory_council_score{workflow=\"${WORKFLOW}\",ticket_id=\"${TICKET_ID}\"} ${SCORE}\n"
  METRICS+="# HELP ai_factory_events_total AI Factory event counter\n"
  METRICS+="# TYPE ai_factory_events_total gauge\n"
  METRICS+="ai_factory_events_total{workflow=\"${WORKFLOW}\",stage=\"${STAGE}\",verdict=\"${VERDICT}\"} 1\n"
  _push_metrics "workflow/${WORKFLOW}/stage/${STAGE}/instance/${TICKET_ID}" "$(printf '%b' "$METRICS")"
}

# push_metrics_implement WORKFLOW TICKET_ID VERDICT [DURATION_SECS] [FILES] [LOC] [MODEL] [MAX_TURNS]
# Push implementation result metrics to Pushgateway.
push_metrics_implement() {
  local WORKFLOW="${1:-unknown}" TICKET_ID="${2:-}" VERDICT="${3:-unknown}"
  local DURATION_SECS="${4:-0}" FILES="${5:-0}" LOC="${6:-0}"
  local MODEL="${7:-sonnet}" MAX_TURNS="${8:-30}"
  local STAGE="implement"
  local METRICS=""
  METRICS+="# HELP ai_factory_events_total AI Factory event counter\n"
  METRICS+="# TYPE ai_factory_events_total gauge\n"
  METRICS+="ai_factory_events_total{workflow=\"${WORKFLOW}\",stage=\"${STAGE}\",verdict=\"${VERDICT}\"} 1\n"
  METRICS+="# HELP ai_factory_duration_seconds Implementation duration in seconds\n"
  METRICS+="# TYPE ai_factory_duration_seconds gauge\n"
  METRICS+="ai_factory_duration_seconds{workflow=\"${WORKFLOW}\",stage=\"${STAGE}\",model=\"${MODEL}\"} ${DURATION_SECS}\n"
  if [ "${LOC:-0}" != "0" ]; then
    METRICS+="# HELP ai_factory_pr_loc Lines of code changed in PR\n"
    METRICS+="# TYPE ai_factory_pr_loc gauge\n"
    METRICS+="ai_factory_pr_loc{workflow=\"${WORKFLOW}\",stage=\"${STAGE}\",ticket_id=\"${TICKET_ID}\"} ${LOC}\n"
  fi
  if [ "${FILES:-0}" != "0" ]; then
    METRICS+="# HELP ai_factory_pr_files Files changed in PR\n"
    METRICS+="# TYPE ai_factory_pr_files gauge\n"
    METRICS+="ai_factory_pr_files{workflow=\"${WORKFLOW}\",stage=\"${STAGE}\",ticket_id=\"${TICKET_ID}\"} ${FILES}\n"
  fi
  # Estimated cost: max_turns * $0.015 (Sonnet upper bound)
  local COST
  COST=$(echo "${MAX_TURNS} * 0.015" | bc -l 2>/dev/null || echo "0")
  METRICS+="# HELP ai_factory_estimated_cost_usd Estimated cost in USD (upper bound)\n"
  METRICS+="# TYPE ai_factory_estimated_cost_usd gauge\n"
  METRICS+="ai_factory_estimated_cost_usd{workflow=\"${WORKFLOW}\",stage=\"${STAGE}\",model=\"${MODEL}\"} ${COST}\n"
  _push_metrics "workflow/${WORKFLOW}/stage/${STAGE}/instance/${TICKET_ID}" "$(printf '%b' "$METRICS")"
}

# push_metrics_scan TOTAL CREATED DAILY_COUNT DAILY_MAX [CAPPED]
# Push autopilot scan metrics to Pushgateway.
push_metrics_scan() {
  local TOTAL="${1:-0}" CREATED="${2:-0}" DAILY_COUNT="${3:-0}" DAILY_MAX="${4:-5}"
  local CAPPED="${5:-false}"
  local STAGE="scan"
  local TODAY
  TODAY=$(date -u +%Y-%m-%d)
  local METRICS=""
  METRICS+="# HELP ai_factory_scan_candidates Eligible tickets found in scan\n"
  METRICS+="# TYPE ai_factory_scan_candidates gauge\n"
  METRICS+="ai_factory_scan_candidates{} ${TOTAL}\n"
  METRICS+="# HELP ai_factory_scan_dispatched Tickets dispatched from scan\n"
  METRICS+="# TYPE ai_factory_scan_dispatched gauge\n"
  METRICS+="ai_factory_scan_dispatched{} ${CREATED}\n"
  METRICS+="# HELP ai_factory_velocity_daily Tickets processed today\n"
  METRICS+="# TYPE ai_factory_velocity_daily gauge\n"
  METRICS+="ai_factory_velocity_daily{date=\"${TODAY}\"} ${DAILY_COUNT}\n"
  METRICS+="# HELP ai_factory_velocity_cap Daily velocity cap\n"
  METRICS+="# TYPE ai_factory_velocity_cap gauge\n"
  METRICS+="ai_factory_velocity_cap{} ${DAILY_MAX}\n"
  _push_metrics "workflow/autopilot-scan/stage/${STAGE}" "$(printf '%b' "$METRICS")"
}

# push_metrics_scheduled WORKFLOW TASK_NAME STATUS [DURATION_SECS]
# Push scheduled task metrics to Pushgateway.
push_metrics_scheduled() {
  local WORKFLOW="${1:-unknown}" TASK_NAME="${2:-unknown}" STATUS="${3:-unknown}"
  local DURATION_SECS="${4:-0}"
  local STAGE="scheduled"
  local VERDICT="success"
  [ "$STATUS" != "success" ] && VERDICT="failure"
  local METRICS=""
  METRICS+="# HELP ai_factory_events_total AI Factory event counter\n"
  METRICS+="# TYPE ai_factory_events_total gauge\n"
  METRICS+="ai_factory_events_total{workflow=\"${WORKFLOW}\",stage=\"${STAGE}\",verdict=\"${VERDICT}\"} 1\n"
  if [ "${DURATION_SECS:-0}" != "0" ]; then
    METRICS+="# HELP ai_factory_duration_seconds Task duration in seconds\n"
    METRICS+="# TYPE ai_factory_duration_seconds gauge\n"
    METRICS+="ai_factory_duration_seconds{workflow=\"${WORKFLOW}\",stage=\"${STAGE}\",model=\"haiku\"} ${DURATION_SECS}\n"
  fi
  _push_metrics "workflow/${WORKFLOW}/stage/${STAGE}/instance/${TASK_NAME}" "$(printf '%b' "$METRICS")"
}

# push_metrics_error WORKFLOW JOB [TICKET_ID]
# Push error event metric to Pushgateway.
push_metrics_error() {
  local WORKFLOW="${1:-unknown}" JOB="${2:-unknown}" TICKET_ID="${3:-}"
  local STAGE="${JOB}"
  local METRICS=""
  METRICS+="# HELP ai_factory_events_total AI Factory event counter\n"
  METRICS+="# TYPE ai_factory_events_total gauge\n"
  METRICS+="ai_factory_events_total{workflow=\"${WORKFLOW}\",stage=\"${STAGE}\",verdict=\"error\"} 1\n"
  _push_metrics "workflow/${WORKFLOW}/stage/${STAGE}/instance/${TICKET_ID:-error}" "$(printf '%b' "$METRICS")"
}

# push_metrics_cost DATE TOKENS_TOTAL COST_USD MODEL_BREAKDOWN SESSIONS MESSAGES
# Push daily cost metrics to Pushgateway.
push_metrics_cost() {
  local DATE="${1:-}" TOKENS="${2:-0}" COST="${3:-0}" MODELS="${4:-}" SESSIONS="${5:-0}" MESSAGES="${6:-0}"
  local METRICS=""
  METRICS+="# HELP ai_factory_daily_tokens Daily token consumption\n"
  METRICS+="# TYPE ai_factory_daily_tokens gauge\n"
  METRICS+="ai_factory_daily_tokens{date=\"${DATE}\"} ${TOKENS}\n"
  METRICS+="# HELP ai_factory_daily_cost_usd Daily estimated cost (API equivalent)\n"
  METRICS+="# TYPE ai_factory_daily_cost_usd gauge\n"
  METRICS+="ai_factory_daily_cost_usd{date=\"${DATE}\"} ${COST}\n"
  METRICS+="# HELP ai_factory_daily_sessions Daily session count\n"
  METRICS+="# TYPE ai_factory_daily_sessions gauge\n"
  METRICS+="ai_factory_daily_sessions{date=\"${DATE}\"} ${SESSIONS}\n"
  METRICS+="# HELP ai_factory_daily_messages Daily message count\n"
  METRICS+="# TYPE ai_factory_daily_messages gauge\n"
  METRICS+="ai_factory_daily_messages{date=\"${DATE}\"} ${MESSAGES}\n"

  # Per-model token breakdown (MODELS format: "opus-4-6=123 sonnet-4-6=456")
  if [[ -n "$MODELS" ]]; then
    METRICS+="# HELP ai_factory_daily_tokens_by_model Daily tokens per model\n"
    METRICS+="# TYPE ai_factory_daily_tokens_by_model gauge\n"
    for entry in $MODELS; do
      local model="${entry%%=*}" tokens="${entry#*=}"
      METRICS+="ai_factory_daily_tokens_by_model{date=\"${DATE}\",model=\"${model}\"} ${tokens}\n"
    done
  fi

  _push_metrics "cost-tracker/${DATE}" "$(printf '%b' "$METRICS")"
}

# notify_cost_report DATE TOKENS_TODAY COST_TODAY COST_7D_AVG SESSIONS MESSAGES PRS_MERGED MODEL_MIX TREND
# Send daily cost report to Slack as Block Kit message.
notify_cost_report() {
  local DATE="${1:-}" TOKENS="${2:-0}" COST="${3:-0}" AVG_7D="${4:-0}"
  local SESSIONS="${5:-0}" MESSAGES="${6:-0}" PRS="${7:-0}" MODEL_MIX="${8:-}" TREND="${9:-flat}"

  [[ -z "${SLACK_WEBHOOK:-}" ]] && return 0

  # Trend arrow
  local trend_arrow="→"
  case "$TREND" in
    up) trend_arrow="↑" ;;
    down) trend_arrow="↓" ;;
  esac

  # Color based on cost
  local color="good"  # green
  local cost_int
  cost_int=$(awk -v c="$COST" 'BEGIN { printf "%d", c }')
  if [[ "$cost_int" -ge 50 ]]; then
    color="danger"  # red
  elif [[ "$cost_int" -ge 30 ]]; then
    color="warning"  # yellow
  fi

  # Cost per PR
  local cost_per_pr="N/A"
  local prs_int
  prs_int=$(awk -v p="$PRS" 'BEGIN { printf "%d", p }')
  if [[ "$prs_int" -gt 0 ]]; then
    cost_per_pr=$(awk -v c="$COST" -v p="$PRS" 'BEGIN { printf "$%.2f", c/p }')
  fi

  # Format tokens with K/M suffix
  local tokens_fmt
  tokens_fmt=$(awk -v t="$TOKENS" 'BEGIN {
    if (t >= 1000000) printf "%.1fM", t/1000000
    else if (t >= 1000) printf "%.0fK", t/1000
    else printf "%d", t
  }')

  local payload
  payload=$(cat <<EOJSON
{
  "attachments": [{
    "color": "${color}",
    "blocks": [
      {
        "type": "header",
        "text": { "type": "plain_text", "text": "AI Factory Daily Report — ${DATE}" }
      },
      {
        "type": "section",
        "fields": [
          { "type": "mrkdwn", "text": "*Tokens*\n${tokens_fmt}" },
          { "type": "mrkdwn", "text": "*Cost (API eq.)*\n\$${COST}" },
          { "type": "mrkdwn", "text": "*Sessions*\n${SESSIONS}" },
          { "type": "mrkdwn", "text": "*Messages*\n${MESSAGES}" },
          { "type": "mrkdwn", "text": "*PRs Merged*\n${PRS}" },
          { "type": "mrkdwn", "text": "*Cost/PR*\n${cost_per_pr}" }
        ]
      },
      {
        "type": "context",
        "elements": [
          { "type": "mrkdwn", "text": "7d avg: \$${AVG_7D} ${trend_arrow} | Models: ${MODEL_MIX:-n/a}" }
        ]
      }
    ]
  }]
}
EOJSON
  )

  curl -sf -X POST -H "Content-Type: application/json" -d "$payload" "$SLACK_WEBHOOK" >/dev/null 2>&1 || true
}
