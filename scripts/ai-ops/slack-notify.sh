#!/bin/bash
# slack-notify.sh — Envoie une notification Slack structurée
# Usage: ./slack-notify.sh <type> <ticket> <message> [url]
# Types: done, blocked, failed, info

set -e

TYPE="${1:-info}"
TICKET="${2:-UNKNOWN}"
MESSAGE="${3:-No message}"
URL="${4:-}"

SLACK_WEBHOOK="${SLACK_WEBHOOK:-}"

if [ -z "$SLACK_WEBHOOK" ]; then
    echo "⚠️  SLACK_WEBHOOK not set. Message:"
    echo "[$TYPE] $TICKET: $MESSAGE"
    exit 0
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
curl -s -X POST "$SLACK_WEBHOOK" \
    -H 'Content-Type: application/json' \
    -d "$PAYLOAD" > /dev/null

echo "✅ Notification sent: [$TYPE] $TICKET"
