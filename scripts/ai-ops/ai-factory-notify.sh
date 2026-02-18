#!/usr/bin/env bash
# AI Factory Notification Library — centralized Slack, Linear, GHA Job Summary
# Source this file: source scripts/ai-ops/ai-factory-notify.sh
# All functions are best-effort (never fail the parent step).

# ── Internal helpers ──────────────────────────────────────────────────────────

_linear_url() {
  echo "https://linear.app/cab-ing/issue/${1}"
}

_run_url() {
  echo "https://github.com/stoa-platform/stoa/actions/runs/${GITHUB_RUN_ID:-0}"
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
  # Internal: send Block Kit payload to Slack. Graceful degradation if webhook unset.
  local PAYLOAD="$1"
  if [ -z "${SLACK_WEBHOOK:-}" ]; then
    echo "::notice::Slack webhook not configured — skipping notification"
    return 0
  fi
  curl -sf -X POST "$SLACK_WEBHOOK" \
    -H 'Content-Type: application/json' \
    -d "$PAYLOAD" > /dev/null 2>&1 || {
    echo "::warning::Slack notification failed (non-blocking)"
    return 0
  }
}

# ── Public functions ──────────────────────────────────────────────────────────

# notify_council TICKET_ID TITLE SCORE VERDICT ISSUE_URL [ISSUE_NUM]
# Sends Council validation report to Slack with approve button + Linear link.
notify_council() {
  local TICKET_ID="${1:?}" TITLE="${2:?}" SCORE="${3:-?}" VERDICT="${4:-Go}"
  local ISSUE_URL="${5:-}" ISSUE_NUM="${6:-}"
  local LINEAR_LINK="$(_linear_url "$TICKET_ID")"
  local RUN_LINK="$(_run_url)"

  # Determine emoji + color
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
          \"text\": \"*${ESCAPED_TITLE}*\n\n<${LINEAR_LINK}|Linear> | <${RUN_LINK}|GHA Run>\"
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
        \"elements\": [{\"type\": \"mrkdwn\", \"text\": \"STOA AI Factory | $(date -u +%H:%M) UTC\"}]
      }
    ]
  }"
}

# notify_implement TICKET_ID STATUS [PR_NUM] [PR_URL] [ISSUE_NUM] [PIPELINE]
# STATUS: success|failure|ask|skipped
notify_implement() {
  local TICKET_ID="${1:?}" STATUS="${2:?}"
  local PR_NUM="${3:-}" PR_URL="${4:-}" ISSUE_NUM="${5:-}" PIPELINE="${6:-L3 Pipeline}"
  local LINEAR_LINK="$(_linear_url "$TICKET_ID")"
  local RUN_LINK="$(_run_url)"

  local MSG=""
  case "$STATUS" in
    success)
      if [ -n "$PR_NUM" ]; then
        MSG=":tada: *${TICKET_ID}* completed! PR <${PR_URL}|#${PR_NUM}> merged | <${LINEAR_LINK}|Linear> → Done"
      else
        MSG=":white_check_mark: *${TICKET_ID}* implementation complete. <${LINEAR_LINK}|Linear>"
      fi
      ;;
    ask)
      MSG=":eyes: *${TICKET_ID}* — PR <${PR_URL}|#${PR_NUM}> created (Ask mode). <${LINEAR_LINK}|Linear>"
      ;;
    failure)
      MSG=":x: *${TICKET_ID}* implementation failed. <${RUN_LINK}|View Logs> | <${LINEAR_LINK}|Linear>"
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

# notify_error WORKFLOW JOB [TICKET_ID] [EXEC_FILE]
# Vercel-style error report with log excerpt + links.
notify_error() {
  local WORKFLOW="${1:?}" JOB="${2:?}"
  local TICKET_ID="${3:-}" EXEC_FILE="${4:-}"
  local RUN_LINK="$(_run_url)"
  local LINEAR_REF=""
  [ -n "$TICKET_ID" ] && LINEAR_REF=" | <$(_linear_url "$TICKET_ID")|Linear>"

  local EXCERPT
  EXCERPT=$(_extract_error "$EXEC_FILE")
  local ESCAPED_EXCERPT
  ESCAPED_EXCERPT=$(_escape_json "$EXCERPT")

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
          \"text\": \"*Workflow*: ${WORKFLOW}\n*Job*: ${JOB}${TICKET_ID:+\n*Ticket*: ${TICKET_ID}}\n\n\`\`\`${ESCAPED_EXCERPT}\`\`\`\"
        }
      },
      {
        \"type\": \"actions\",
        \"elements\": [
          {\"type\":\"button\",\"text\":{\"type\":\"plain_text\",\"text\":\"View Full Logs\"},\"url\":\"${RUN_LINK}\"}
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

# linear_comment TICKET_ID STATUS [PR_NUM] [PR_URL] [PIPELINE]
# Post rich completion report to Linear ticket. Requires LINEAR_API_KEY env var.
linear_comment() {
  local TICKET_ID="${1:?}" STATUS="${2:?}"
  local PR_NUM="${3:-}" PR_URL="${4:-}" PIPELINE="${5:-L3 Pipeline}"

  if [ -z "${LINEAR_API_KEY:-}" ]; then
    echo "::notice::LINEAR_API_KEY not set — skipping Linear comment"
    return 0
  fi

  local PR_REF=""
  [ -n "$PR_NUM" ] && PR_REF="PR [#${PR_NUM}](${PR_URL})"

  local BODY="Completed autonomously via AI Factory ${PIPELINE}. ${PR_REF}"
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

# write_job_summary TICKET_ID STATUS [PR_NUM] [MODEL] [PIPELINE]
# Write structured markdown table to $GITHUB_STEP_SUMMARY.
write_job_summary() {
  local TICKET_ID="${1:?}" STATUS="${2:?}"
  local PR_NUM="${3:-}" MODEL="${4:-}" PIPELINE="${5:-}"

  if [ -z "${GITHUB_STEP_SUMMARY:-}" ]; then
    echo "::notice::GITHUB_STEP_SUMMARY not set — skipping job summary"
    return 0
  fi

  local LINEAR_LINK="$(_linear_url "$TICKET_ID")"
  local RUN_LINK="$(_run_url)"

  {
    echo "## AI Factory: ${PIPELINE:-implement}"
    echo ""
    echo "| Field | Value |"
    echo "|-------|-------|"
    echo "| Ticket | [${TICKET_ID}](${LINEAR_LINK}) |"
    echo "| Status | ${STATUS} |"
    [ -n "$PR_NUM" ] && echo "| PR | #${PR_NUM} |"
    [ -n "$MODEL" ] && echo "| Model | ${MODEL} |"
    echo "| Run | [#${GITHUB_RUN_NUMBER:-?}](${RUN_LINK}) |"
    echo ""
  } >> "$GITHUB_STEP_SUMMARY"
}
