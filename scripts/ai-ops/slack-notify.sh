#!/usr/bin/env bash
# DEPRECATED: Use scripts/ai-ops/ai-factory-notify.sh instead.
# This script is kept for backward compatibility but will be removed.
#
# slack-notify.sh — Envoie une notification Slack structurée
# Usage: ./slack-notify.sh <type> <ticket> <message> [url]
# Types: done, blocked, failed, info

set -euo pipefail

TYPE="${1:-info}"
TICKET="${2:-UNKNOWN}"
MESSAGE="${3:-No message}"
URL="${4:-}"

SLACK_WEBHOOK="${SLACK_WEBHOOK:-}"

if [ -z "$SLACK_WEBHOOK" ]; then
    echo "SLACK_WEBHOOK not set. Message:"
    echo "[$TYPE] $TICKET: $MESSAGE"
    exit 0
fi

if ! command -v curl &> /dev/null; then
    echo "Error: curl is required but not installed." >&2
    exit 1
fi

# Emoji et couleur selon le type
case "$TYPE" in
    done)
        EMOJI="🟢"
        COLOR="#36a64f"
        TITLE="Phase Complete"
        ;;
    blocked)
        EMOJI="🟡"
        COLOR="#ffcc00"
        TITLE="Decision Needed"
        ;;
    failed)
        EMOJI="🔴"
        COLOR="#ff0000"
        TITLE="Tests Failed"
        ;;
    *)
        EMOJI="ℹ️"
        COLOR="#439FE0"
        TITLE="Info"
        ;;
esac

# Build JSON payload
if [ -n "$URL" ]; then
    ACTIONS=",\"actions\":[{\"type\":\"button\",\"text\":{\"type\":\"plain_text\",\"text\":\"View\"},\"url\":\"$URL\"}]"
else
    ACTIONS=""
fi

PAYLOAD=$(cat <<EOF
{
    "blocks": [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "$EMOJI $TITLE: $TICKET",
                "emoji": true
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "$MESSAGE"
            }
        }
    ],
    "attachments": [
        {
            "color": "$COLOR"
            $ACTIONS
        }
    ]
}
EOF
)

# Send to Slack
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$SLACK_WEBHOOK" \
    -H 'Content-Type: application/json' \
    -d "$PAYLOAD")

if [ "$HTTP_STATUS" -ge 200 ] && [ "$HTTP_STATUS" -lt 300 ]; then
    echo "Notification sent: [$TYPE] $TICKET"
else
    echo "Error: Slack returned HTTP $HTTP_STATUS" >&2
    exit 1
fi
