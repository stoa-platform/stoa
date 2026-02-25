#!/bin/bash
# Stop hook: Send Slack notification when Claude session ends.
# Sends a summary with instance role, branch, recent commits, and PR status.
#
# Requires: SLACK_WEBHOOK_URL env var (set in .claude/settings.json env or shell)
# Optional: STOA_INSTANCE env var (set by stoa-parallel or manually)
#
# Gracefully degrades: no webhook = no notification (silent skip).

WEBHOOK="${SLACK_WEBHOOK_URL:-}"
[ -z "$WEBHOOK" ] && exit 0

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$PROJECT_DIR" 2>/dev/null || exit 0

# Gather context
INSTANCE="${STOA_INSTANCE:-default}"
BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
RECENT_COMMITS=$(git log --oneline -3 2>/dev/null | head -3 | sed 's/"/\\"/g' | tr '\n' '\\' | sed 's/\\/\\n/g')
HOSTNAME=$(hostname -s 2>/dev/null || echo "local")

# Check for open PR on current branch
PR_INFO=""
if command -v gh &>/dev/null; then
  PR_NUM=$(gh pr view --json number -q '.number' 2>/dev/null || true)
  if [ -n "$PR_NUM" ]; then
    PR_STATE=$(gh pr view --json state -q '.state' 2>/dev/null || echo "UNKNOWN")
    PR_TITLE=$(gh pr view --json title -q '.title' 2>/dev/null | head -c 80 || true)
    PR_INFO="\\n*PR #${PR_NUM}*: ${PR_TITLE} (${PR_STATE})"
  fi
fi

# Check for modified files (uncommitted work)
DIRTY=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
DIRTY_MSG=""
if [ "$DIRTY" -gt 0 ]; then
  DIRTY_MSG="\\n:warning: ${DIRTY} uncommitted file(s)"
fi

# Build Slack message
EMOJI=":white_check_mark:"
[ "$INSTANCE" != "default" ] && ROLE_LABEL=" (instance:${INSTANCE})" || ROLE_LABEL=""

PAYLOAD=$(cat <<SLACKEOF
{
  "blocks": [
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "${EMOJI} *Claude session ended*${ROLE_LABEL}\\n\\n*Branch*: \`${BRANCH}\`\\n*Host*: ${HOSTNAME}${PR_INFO}${DIRTY_MSG}"
      }
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*Recent commits*:\\n\`\`\`${RECENT_COMMITS}\`\`\`"
      }
    },
    {
      "type": "context",
      "elements": [
        {
          "type": "mrkdwn",
          "text": ":hourglass: Waiting for next instruction | $(date '+%H:%M %Z')"
        }
      ]
    }
  ]
}
SLACKEOF
)

# Send (best-effort, never fail the parent hook)
curl -sf -X POST "$WEBHOOK" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" >/dev/null 2>&1 || true

exit 0
