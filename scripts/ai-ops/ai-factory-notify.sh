#!/usr/bin/env bash
# ai-factory-notify.sh — Centralized AI Factory notification library
# Source this file in GHA workflow steps. All functions are no-op if SLACK_WEBHOOK is unset.
#
# Usage:
#   source scripts/ai-ops/ai-factory-notify.sh
#   notify_council "CAB-1350" "Traceparent injection" "8.5" "Go" "Ship" "150" "$ISSUE_URL"
#   notify_implement "success" "CAB-1350" "578" "https://github.com/.../pull/578" "12m 34s"
#   notify_error "claude-autopilot-scan" "scan" "CAB-1371" "GraphQL error" "8m 12s"
#   notify_scan "3" "2" "1"
#   notify_scheduled ":sunrise:" "Daily Triage" "Complete — check GitHub issues for digest"
#   linear_comment "CAB-1350" "578" "https://github.com/.../pull/578" "3 files, ~120 LOC" "12m 34s" "Ship"
#   write_job_summary "implement" "CAB-1350" "success" "578" "12m 34s"
#
# Env vars (all optional — graceful degradation):
#   SLACK_WEBHOOK       — Slack incoming webhook URL
#   LINEAR_API_KEY      — Linear API key (for linear_comment only)
#   GITHUB_RUN_ID       — auto-set by GHA
#   GITHUB_RUN_NUMBER   — auto-set by GHA
#   GITHUB_STEP_SUMMARY — auto-set by GHA
#   N8N_WEBHOOK         — n8n approval relay webhook
#   HMAC_SECRET         — HMAC signing key for approve button

# --- Internal helpers ---

_escape_json() {
  # Safely escape a string for JSON embedding
  # Uses python3 (available on all GHA runners) for reliable escaping
  local input="${1:-}"
  if [ -z "$input" ]; then
    echo ""
    return
  fi
  python3 -c 'import json,sys; print(json.dumps(sys.stdin.read())[1:-1])' <<< "$input" 2>/dev/null || \
    echo "$input" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\n/\\n/g; s/\t/\\t/g'
}

_linear_url() {
  # Deterministic Linear URL — no API call needed
  local ticket_id="${1:-}"
  [ -z "$ticket_id" ] && return
  echo "https://linear.app/cab-ing/issue/${ticket_id}"
}

_run_url() {
  # GitHub Actions run URL
  echo "https://github.com/stoa-platform/stoa/actions/runs/${GITHUB_RUN_ID:-0}"
}

_approve_url() {
  # Build approve button URL: n8n relay if configured, else GitHub issue
  local issue_num="${1:-}"
  local issue_url="${2:-}"

  if [ -n "${N8N_WEBHOOK:-}" ] && [ -n "${HMAC_SECRET:-}" ] && [ -n "$issue_num" ]; then
    local hmac
    hmac=$(echo -n "$issue_num" | openssl dgst -sha256 -hmac "$HMAC_SECRET" | awk '{print $NF}')
    echo "${N8N_WEBHOOK}?issue=${issue_num}&token=${hmac}"
  else
    echo "${issue_url:-$(_run_url)}"
  fi
}

_extract_error() {
  # Extract error excerpt (max 500 chars) from Claude execution output file
  local exec_file="${1:-}"
  local excerpt=""

  if [ -f "$exec_file" ]; then
    # Try result field first
    excerpt=$(jq -r '.[] | select(.type == "result") | .result // empty' "$exec_file" 2>/dev/null | tail -c 500 || true)
    # Fallback: assistant text
    if [ -z "$excerpt" ]; then
      excerpt=$(jq -r '[.[] | select(.type == "assistant") | .message.content[] | select(.type == "text") | .text] | join("\n")' \
        "$exec_file" 2>/dev/null | tail -c 500 || true)
    fi
  fi

  # Fallback: empty
  echo "${excerpt:-No error details available}"
}

_send_slack() {
  # Internal: send JSON payload to Slack webhook
  local payload="${1:-}"
  if [ -z "${SLACK_WEBHOOK:-}" ]; then
    echo "[notify] SLACK_WEBHOOK not set — skipping"
    return 0
  fi
  local http_status
  http_status=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$SLACK_WEBHOOK" \
    -H 'Content-Type: application/json' \
    -d "$payload" 2>/dev/null || echo "000")

  if [ "$http_status" -ge 200 ] 2>/dev/null && [ "$http_status" -lt 300 ] 2>/dev/null; then
    echo "[notify] Slack notification sent (HTTP $http_status)"
  else
    echo "[notify] WARNING: Slack returned HTTP $http_status" >&2
  fi
}

_footer() {
  local pipeline="${1:-AI Factory}"
  echo "STOA AI Factory | ${pipeline} | $(date -u +%H:%M) UTC"
}

# --- Public notification functions ---

notify_council() {
  # Council validation report with approve button
  # Args: ticket_id title score verdict ship_show_ask loc_estimate issue_url [issue_num]
  local ticket_id="${1:-}" title="${2:-}" score="${3:-0}" verdict="${4:-Redo}"
  local ship_show_ask="${5:-Ask}" loc_estimate="${6:-?}" issue_url="${7:-}"
  local issue_num="${8:-}"

  # Extract issue number from URL if not provided
  if [ -z "$issue_num" ] && [ -n "$issue_url" ]; then
    issue_num=$(echo "$issue_url" | grep -oE '/issues/[0-9]+' | grep -oE '[0-9]+' || echo "")
  fi

  local emoji linear_url approve_url button_text instructions
  case "$verdict" in
    Go)  emoji=":white_check_mark:" ;;
    Fix) emoji=":warning:" ;;
    *)   emoji=":x:" ;;
  esac

  linear_url=$(_linear_url "$ticket_id")
  approve_url=$(_approve_url "$issue_num" "$issue_url")

  if [ -n "${N8N_WEBHOOK:-}" ] && [ -n "${HMAC_SECRET:-}" ] && [ -n "$issue_num" ]; then
    button_text="Approve \\u0026 Start"
    instructions=":zap: Click *Approve & Start* to trigger implementation (1 click).\n:mag: Or open the <${issue_url}|GitHub issue> to review first."
  else
    button_text="Review \\u0026 Approve"
    instructions=":point_right: Comment \`/go\` on the GitHub issue to start implementation.\n:point_right: Comment \`/adjust <feedback>\` to request changes."
  fi

  local escaped_title escaped_instructions
  escaped_title=$(_escape_json "$title")
  escaped_instructions=$(_escape_json "$instructions")

  local linear_link=""
  [ -n "$linear_url" ] && linear_link="\nLinear: <${linear_url}|${ticket_id}>"

  local payload
  payload="{
    \"blocks\": [
      {
        \"type\": \"header\",
        \"text\": {\"type\": \"plain_text\", \"text\": \"${emoji} Council: ${ticket_id} \\u2014 ${score}/10 ${verdict}\", \"emoji\": true}
      },
      {
        \"type\": \"section\",
        \"text\": {
          \"type\": \"mrkdwn\",
          \"text\": \"*${escaped_title}*\n${ship_show_ask} mode | ~${loc_estimate} LOC${linear_link}\n\n${escaped_instructions}\"
        },
        \"accessory\": {
          \"type\": \"button\",
          \"text\": {\"type\": \"plain_text\", \"text\": \"${button_text}\"},
          \"url\": \"${approve_url}\",
          \"style\": \"primary\"
        }
      },
      {
        \"type\": \"context\",
        \"elements\": [{\"type\": \"mrkdwn\", \"text\": \"$(_footer "Council Gate")\"}]
      }
    ]
  }"

  _send_slack "$payload"

  # Write job summary
  write_job_summary "council" "$ticket_id" "$verdict" "" "" "$score"
}

notify_implement() {
  # Implementation result notification
  # Args: status ticket_id pr_num pr_url duration [issue_num] [ask_mode]
  local status="${1:-unknown}" ticket_id="${2:-}" pr_num="${3:-}" pr_url="${4:-}"
  local duration="${5:-}" issue_num="${6:-}" ask_mode="${7:-false}"

  local emoji msg linear_url
  linear_url=$(_linear_url "$ticket_id")

  case "$status" in
    success)
      if [ -n "$pr_num" ] && [ "$ask_mode" != "true" ]; then
        emoji=":tada:"
        msg="*${ticket_id:-#${issue_num}}* completed!\nPR <${pr_url}|#${pr_num}> merged | Linear -> Done"
        [ -n "$duration" ] && msg="${msg} | ${duration}"
      elif [ "$ask_mode" = "true" ]; then
        emoji=":eyes:"
        msg="*${ticket_id:-#${issue_num}}* \\u2014 PR created (Ask mode). Awaiting human review."
        [ -n "$pr_url" ] && msg="${msg}\nPR: <${pr_url}|#${pr_num}>"
      else
        emoji=":white_check_mark:"
        msg="Implementation complete for ${ticket_id:-#${issue_num}}."
      fi
      ;;
    skipped)
      emoji=":warning:"
      msg="Implementation skipped for ${ticket_id:-#${issue_num}}."
      ;;
    *)
      emoji=":x:"
      msg="*${ticket_id:-#${issue_num}}* \\u2014 Implementation failed.\n<$(_run_url)|View Full Logs>"
      ;;
  esac

  [ -n "$linear_url" ] && [ -n "$ticket_id" ] && msg="${msg}\nLinear: <${linear_url}|${ticket_id}>"

  local payload
  payload="{
    \"blocks\": [
      {
        \"type\": \"section\",
        \"text\": {\"type\": \"mrkdwn\", \"text\": \"${emoji} ${msg}\"}
      },
      {
        \"type\": \"context\",
        \"elements\": [{\"type\": \"mrkdwn\", \"text\": \"$(_footer "L3 Pipeline")\"}]
      }
    ]
  }"

  _send_slack "$payload"

  # Write job summary
  write_job_summary "implement" "$ticket_id" "$status" "$pr_num" "$duration"
}

notify_error() {
  # Vercel-style error report with log excerpt
  # Args: workflow job ticket_id error_excerpt duration [exec_file]
  local workflow="${1:-unknown}" job="${2:-}" ticket_id="${3:-}"
  local error_excerpt="${4:-}" duration="${5:-}" exec_file="${6:-}"

  # Try to extract error from execution file if no excerpt provided
  if [ -z "$error_excerpt" ] && [ -n "$exec_file" ]; then
    error_excerpt=$(_extract_error "$exec_file")
  fi

  local escaped_error
  escaped_error=$(_escape_json "${error_excerpt:0:500}")

  local linear_ref=""
  [ -n "$ticket_id" ] && linear_ref=" | Ticket: <$(_linear_url "$ticket_id")|${ticket_id}>"

  local duration_ref=""
  [ -n "$duration" ] && duration_ref="\nDuration: ${duration}"

  local payload
  payload="{
    \"blocks\": [
      {
        \"type\": \"header\",
        \"text\": {\"type\": \"plain_text\", \"text\": \":rotating_light: AI Factory Error\", \"emoji\": true}
      },
      {
        \"type\": \"section\",
        \"text\": {
          \"type\": \"mrkdwn\",
          \"text\": \"Workflow: \`${workflow}\`\nJob: \`${job}\`${linear_ref}${duration_ref}\"
        }
      },
      {
        \"type\": \"section\",
        \"text\": {
          \"type\": \"mrkdwn\",
          \"text\": \"\`\`\`${escaped_error}\`\`\`\"
        }
      },
      {
        \"type\": \"actions\",
        \"elements\": [
          {
            \"type\": \"button\",
            \"text\": {\"type\": \"plain_text\", \"text\": \"View Full Logs\"},
            \"url\": \"$(_run_url)\"
          }
        ]
      },
      {
        \"type\": \"context\",
        \"elements\": [{\"type\": \"mrkdwn\", \"text\": \"Run #${GITHUB_RUN_NUMBER:-?} | $(date -u +%H:%M) UTC\"}]
      }
    ]
  }"

  _send_slack "$payload"

  # Write job summary with error
  write_job_summary "$job" "$ticket_id" "error" "" "$duration" "" "$error_excerpt"
}

notify_scan() {
  # Autopilot scan summary
  # Args: total_eligible approved remaining_velocity
  local total="${1:-0}" approved="${2:-0}" remaining="${3:-0}"

  local msg
  if [ "$total" = "capped" ]; then
    msg=":pause_button: Autopilot scan skipped \\u2014 daily velocity cap reached."
  elif [ "$total" = "0" ]; then
    msg=":inbox_tray: Autopilot scan complete \\u2014 no eligible tickets in backlog."
  elif [ "$total" = "dry_run" ]; then
    msg=":mag: Autopilot scan (dry run) \\u2014 found eligible tickets. No issues created."
  elif [ "$total" = "council_failed" ]; then
    msg=":warning: Autopilot scan \\u2014 Council validation failed. <$(_run_url)|View logs>"
  else
    msg=":sunrise: Autopilot scan complete \\u2014 ${approved} candidates from ${total} eligible. Velocity: ${remaining} slots remaining."
  fi

  local payload
  payload="{\"text\":\"${msg}\"}"

  _send_slack "$payload"

  # Write job summary
  write_job_summary "scan" "" "complete" "" "" "" "" "$total" "$approved"
}

notify_scheduled() {
  # Scheduled task notification (simple emoji + message)
  # Args: emoji task_name message [issue_url]
  local emoji="${1:-:robot_face:}" task_name="${2:-Task}" message="${3:-Complete}"
  local issue_url="${4:-}"

  local button=""
  if [ -n "$issue_url" ]; then
    button=",\"accessory\":{\"type\":\"button\",\"text\":{\"type\":\"plain_text\",\"text\":\"View Report\"},\"url\":\"${issue_url}\"}"
  fi

  local payload
  payload="{
    \"blocks\": [
      {
        \"type\": \"section\",
        \"text\": {
          \"type\": \"mrkdwn\",
          \"text\": \"${emoji} *${task_name}* \\u2014 ${message}\"
        }
        ${button}
      },
      {
        \"type\": \"context\",
        \"elements\": [{\"type\": \"mrkdwn\", \"text\": \"$(_footer "Scheduled")\"}]
      }
    ]
  }"

  _send_slack "$payload"

  # Write job summary
  write_job_summary "$task_name" "" "complete"
}

linear_comment() {
  # Post rich completion report to Linear ticket
  # Args: ticket_id pr_num pr_url changes duration mode
  local ticket_id="${1:-}" pr_num="${2:-}" pr_url="${3:-}"
  local changes="${4:-}" duration="${5:-}" mode="${6:-Ship}"

  if [ -z "${LINEAR_API_KEY:-}" ] || [ -z "$ticket_id" ]; then
    echo "[notify] LINEAR_API_KEY or ticket_id missing — skipping Linear comment"
    return 0
  fi

  local pr_ref=""
  [ -n "$pr_num" ] && pr_ref="**PR**: [#${pr_num}](${pr_url})"

  local body
  body="## AI Factory Report\n\n**Status**: Completed\n${pr_ref}\n**Changes**: ${changes}\n**Duration**: ${duration}\n**Mode**: ${mode}\n\n*Auto-generated by STOA AI Factory L3 Pipeline*"

  local escaped_body
  escaped_body=$(echo "$body" | sed 's/"/\\"/g')

  # Find Linear issue ID
  local issue_id
  issue_id=$(curl -s -X POST "https://api.linear.app/graphql" \
    -H "Authorization: ${LINEAR_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "{\"query\": \"{ issueSearch(filter: { identifier: { eq: \\\"${ticket_id}\\\" } }) { nodes { id } } }\"}" \
    | jq -r '.data.issueSearch.nodes[0].id // empty' 2>/dev/null || echo "")

  if [ -z "$issue_id" ]; then
    echo "[notify] Could not find Linear issue ID for ${ticket_id}"
    return 0
  fi

  # Post comment
  curl -s -X POST "https://api.linear.app/graphql" \
    -H "Authorization: ${LINEAR_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "{\"query\": \"mutation { commentCreate(input: { issueId: \\\"${issue_id}\\\", body: \\\"${escaped_body}\\\" }) { success } }\"}" \
    > /dev/null 2>&1 || true

  echo "[notify] Posted completion report to Linear ${ticket_id}"
}

write_job_summary() {
  # Write structured table to GHA Job Summary
  # Args: job_name ticket_id status [pr_num] [duration] [score] [error] [total] [approved]
  local job_name="${1:-}" ticket_id="${2:-}" status="${3:-}" pr_num="${4:-}"
  local duration="${5:-}" score="${6:-}" error="${7:-}" total="${8:-}" approved="${9:-}"

  if [ -z "${GITHUB_STEP_SUMMARY:-}" ]; then
    echo "[notify] GITHUB_STEP_SUMMARY not set — skipping job summary"
    return 0
  fi

  local linear_link=""
  [ -n "$ticket_id" ] && linear_link="[${ticket_id}]($(_linear_url "$ticket_id"))"

  cat >> "$GITHUB_STEP_SUMMARY" << EOF

## AI Factory: ${job_name}

| Field | Value |
|-------|-------|
| Ticket | ${linear_link:-N/A} |
| Status | ${status} |
| PR | ${pr_num:+#${pr_num}} |
| Duration | ${duration:-N/A} |
| Score | ${score:-N/A} |
| Run | [#${GITHUB_RUN_NUMBER:-?}]($(_run_url)) |

EOF

  if [ -n "$error" ]; then
    cat >> "$GITHUB_STEP_SUMMARY" << EOF
### Error
\`\`\`
${error:0:500}
\`\`\`

EOF
  fi

  if [ -n "$total" ]; then
    cat >> "$GITHUB_STEP_SUMMARY" << EOF
### Scan Results
- Eligible: ${total}
- Approved: ${approved:-0}

EOF
  fi

  echo "[notify] Job summary written for ${job_name}"
}
