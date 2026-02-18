#!/usr/bin/env bash
# DEPRECATED: Use scripts/ai-ops/ai-factory-notify.sh instead.
# This script is kept for backward compatibility but will be removed.
#
# council-slack-report.sh — Send a rich Council validation report to Slack
# Usage: ./council-slack-report.sh <ticket> <score> <verdict> <summary> [issue_url]
# Called by GitHub Actions after Council validation.

set -euo pipefail

TICKET="${1:-UNKNOWN}"
SCORE="${2:-0}"
VERDICT="${3:-Redo}"
SUMMARY="${4:-No summary}"
ISSUE_URL="${5:-}"

SLACK_WEBHOOK="${SLACK_WEBHOOK:-}"

if [ -z "$SLACK_WEBHOOK" ]; then
    echo "SLACK_WEBHOOK not set. Council report:"
    echo "[$VERDICT] $TICKET: $SCORE/10 — $SUMMARY"
    exit 0
fi

# Determine emoji and color based on verdict
case "$VERDICT" in
    Go)
        EMOJI=":white_check_mark:"
        COLOR="#36a64f"
        ACTION_TEXT="React :white_check_mark: or comment \`/go\` on GitHub to start implementation"
        ;;
    Fix)
        EMOJI=":warning:"
        COLOR="#ffcc00"
        ACTION_TEXT="Adjustments needed. Review on GitHub and comment \`/go\` after fixes."
        ;;
    Redo)
        EMOJI=":x:"
        COLOR="#ff0000"
        ACTION_TEXT="Fundamental issues found. Revise the proposal."
        ;;
    *)
        EMOJI=":grey_question:"
        COLOR="#439FE0"
        ACTION_TEXT="Review the Council report on GitHub."
        ;;
esac

# Build review button if URL provided
if [ -n "$ISSUE_URL" ]; then
    BUTTON=",\"accessory\":{\"type\":\"button\",\"text\":{\"type\":\"plain_text\",\"text\":\"Review on GitHub\"},\"url\":\"$ISSUE_URL\"}"
else
    BUTTON=""
fi

PAYLOAD=$(cat <<EOF
{
    "blocks": [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "$EMOJI Council: $TICKET — $SCORE/10 $VERDICT",
                "emoji": true
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*$SUMMARY*\n\n$ACTION_TEXT"
            }
            $BUTTON
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "STOA AI Factory | Council Gate | $(date -u +%Y-%m-%d\ %H:%M) UTC"
                }
            ]
        }
    ],
    "attachments": [
        {
            "color": "$COLOR"
        }
    ]
}
EOF
)

HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$SLACK_WEBHOOK" \
    -H 'Content-Type: application/json' \
    -d "$PAYLOAD")

if [ "$HTTP_STATUS" -ge 200 ] && [ "$HTTP_STATUS" -lt 300 ]; then
    echo "Council report sent to Slack: [$VERDICT] $TICKET $SCORE/10"
else
    echo "Error: Slack returned HTTP $HTTP_STATUS" >&2
    exit 1
fi
