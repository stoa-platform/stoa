#!/usr/bin/env bash
# HEGEMON VPS Slack notification wrapper.
# Lightweight subset of ai-factory-notify.sh for VPS workers.
#
# Usage:
#   source deploy/vps/hegemon/notify.sh
#   hegemon_notify "started" "CAB-1350" "Working on traceparent injection"
#   hegemon_notify "done" "CAB-1350" "PR #578 merged"
#   hegemon_notify "error" "CAB-1350" "CI failed: clippy warning"
# NOTE: no "set -euo pipefail" here — this file is sourced from .bashrc.
# Setting -e in a sourced script bleeds into the interactive shell and kills
# it on the first non-zero return code.

# Resolve env
: "${SLACK_WEBHOOK_URL:=}"
: "${HEGEMON_ROLE:=worker}"
: "${HEGEMON_HOSTNAME:=$(hostname)}"

_hegemon_escape_json() {
  if command -v python3 &>/dev/null; then
    python3 -c "import json,sys; print(json.dumps(sys.argv[1]))" "$1"
  else
    echo "\"$(echo "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\n/\\n/g')\""
  fi
}

# hegemon_notify STATUS TICKET [DETAIL]
hegemon_notify() {
  [ -z "$SLACK_WEBHOOK_URL" ] && return 0

  local status="${1:?Usage: hegemon_notify STATUS TICKET [DETAIL]}"
  local ticket="${2:-}"
  local detail="${3:-}"

  local emoji icon_color
  case "$status" in
    started)      emoji=":rocket:"      ; icon_color="#2196F3" ;;
    coding)       emoji=":hammer:"       ; icon_color="#FF9800" ;;
    pr-created)   emoji=":arrow_heading_up:" ; icon_color="#9C27B0" ;;
    done)         emoji=":white_check_mark:" ; icon_color="#4CAF50" ;;
    error)        emoji=":x:"            ; icon_color="#F44336" ;;
    paused)       emoji=":pause_button:" ; icon_color="#607D8B" ;;
    *)            emoji=":gear:"         ; icon_color="#9E9E9E" ;;
  esac

  local ticket_text=""
  [ -n "$ticket" ] && ticket_text=" \`${ticket}\`"

  local detail_text=""
  [ -n "$detail" ] && detail_text="\n${detail}"

  local safe_detail
  safe_detail=$(_hegemon_escape_json "${detail_text}")

  local payload
  payload=$(cat <<PAYLOAD
{
  "blocks": [
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "${emoji} *HEGEMON* \`${HEGEMON_HOSTNAME}\` — ${status}${ticket_text}${detail_text}"
      }
    },
    {
      "type": "context",
      "elements": [
        {
          "type": "mrkdwn",
          "text": "Role: \`${HEGEMON_ROLE}\` | $(date -u '+%H:%M UTC')"
        }
      ]
    }
  ]
}
PAYLOAD
)

  curl -sf -X POST "$SLACK_WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -d "$payload" >/dev/null 2>&1 || true
}

# hegemon_ping — quick health check ping
hegemon_ping() {
  hegemon_notify "started" "" "Health ping from ${HEGEMON_HOSTNAME}"
}
