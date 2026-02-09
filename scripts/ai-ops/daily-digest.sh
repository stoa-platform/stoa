#!/usr/bin/env bash
# daily-digest.sh — Génère et envoie un résumé quotidien d'activité
# Usage: ./daily-digest.sh [date]
# Peut être lancé via cron: 0 9 * * * /path/to/daily-digest.sh

set -euo pipefail

DATE="${1:-$(date +%Y-%m-%d)}"
SLACK_WEBHOOK="${SLACK_WEBHOOK:-}"
PHASES_DIR=".stoa-ai/phases"

echo "📊 Generating daily digest for $DATE..."

# Compte les commits du jour
COMMITS_TODAY=$(git log --oneline --since="$DATE 00:00" --until="$DATE 23:59" 2>/dev/null | wc -l || echo "0")

# Compte les phases actives
PHASES_ACTIVE=$(find "$PHASES_DIR" -name "plan.md" -exec grep -l "🔄 IN PROGRESS" {} \; 2>/dev/null | wc -l || echo "0")

# Compte les phases terminées aujourd'hui (basé sur les logs)
PHASES_DONE=$(find "$PHASES_DIR" -name "*.log" -newermt "$DATE" -exec grep -l "Phase complete" {} \; 2>/dev/null | wc -l || echo "0")

# Tests status
if [ -f "pytest.log" ]; then
    TESTS_STATUS=$(tail -1 pytest.log 2>/dev/null || echo "Unknown")
else
    TESTS_STATUS="No test log found"
fi

# Build digest message
DIGEST=$(cat <<EOF
📊 *STOA AI Factory — Daily Digest*
📅 Date: $DATE

*Activity*
• Commits: $COMMITS_TODAY
• Phases active: $PHASES_ACTIVE
• Phases completed: $PHASES_DONE

*Tests*
$TESTS_STATUS

*Recent commits*
$(git log --oneline -5 --since="$DATE 00:00" 2>/dev/null || echo "No commits today")
EOF
)

echo "$DIGEST"

# Send to Slack if webhook configured
if [ -n "$SLACK_WEBHOOK" ]; then
    PAYLOAD=$(cat <<EOF
{
    "blocks": [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "📊 STOA AI Factory — Daily Digest",
                "emoji": true
            }
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": "*Date*\n$DATE"},
                {"type": "mrkdwn", "text": "*Commits*\n$COMMITS_TODAY"}
            ]
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": "*Phases Active*\n$PHASES_ACTIVE"},
                {"type": "mrkdwn", "text": "*Phases Done*\n$PHASES_DONE"}
            ]
        },
        {
            "type": "divider"
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Recent Commits*\n\`\`\`$(git log --oneline -5 --since="$DATE 00:00" 2>/dev/null | head -5 || echo "No commits")\`\`\`"
            }
        }
    ]
}
EOF
)

    curl -s -X POST "$SLACK_WEBHOOK" \
        -H 'Content-Type: application/json' \
        -d "$PAYLOAD" > /dev/null
    
    echo "✅ Digest sent to Slack"
else
    echo "⚠️  SLACK_WEBHOOK not set. Digest printed above."
fi
