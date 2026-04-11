#!/bin/bash
# Stop hook: auto-close Linear ticket if a PR was merged during this session.
#
# Logic:
# 1. Extract CAB-XXXX from current branch name
# 2. Check operations.log for PR-MERGED-HOOK entries in this session
# 3. If found → call Linear API to mark ticket Done + add comment
# 4. MEGA tickets are skipped (handled by /verify-mega)
#
# Requires: LINEAR_API_KEY env var (from Infisical or GitHub secrets)
# Kill-switch: DISABLE_LINEAR_SESSION_CLOSE=1
# Gracefully degrades: no API key = silent skip, never blocks session exit.

[ "${DISABLE_LINEAR_SESSION_CLOSE:-}" = "1" ] && exit 0

# Resolve LINEAR_API_KEY: env var → Infisical → skip
LINEAR_API_KEY="${LINEAR_API_KEY:-}"
if [ -z "$LINEAR_API_KEY" ] && command -v infisical >/dev/null 2>&1; then
  LINEAR_API_KEY=$(infisical secrets get LINEAR_API_KEY --plain 2>/dev/null || true)
fi
[ -z "$LINEAR_API_KEY" ] && exit 0

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$PROJECT_DIR" 2>/dev/null || exit 0

# 1. Extract ticket from branch
BRANCH=$(git branch --show-current 2>/dev/null)
[ -z "$BRANCH" ] && exit 0

TICKET_ID=$(echo "$BRANCH" | grep -oiE 'cab-[0-9]+' | head -1 | tr '[:lower:]' '[:upper:]')
[ -z "$TICKET_ID" ] && exit 0

# 2. Check if a PR was merged during this session
MEMORY_DIR="$HOME/.claude/projects/-Users-torpedo-hlfh-repos-stoa/memory"
LOG="${MEMORY_DIR}/operations.log"
[ ! -f "$LOG" ] && exit 0

# Find the last SESSION-START timestamp to scope our search
SESSION_START=$(grep 'SESSION-START' "$LOG" | tail -1 | cut -d'|' -f1 | tr -d ' ')
[ -z "$SESSION_START" ] && exit 0

# Look for PR-MERGED-HOOK entries after session start
MERGED_PR=$(awk -v start="$SESSION_START" '
  /PR-MERGED-HOOK/ {
    ts = $1;
    gsub(/ /, "", ts);
    if (ts >= start) {
      match($0, /pr=([0-9]+)/, m);
      if (m[1] != "") print m[1];
    }
  }
' "$LOG" | tail -1)

# Also check for STEP-DONE step=merged entries (logged by Claude during git-workflow)
if [ -z "$MERGED_PR" ]; then
  MERGED_PR=$(awk -v start="$SESSION_START" -v ticket="$TICKET_ID" '
    /STEP-DONE.*step=merged/ {
      ts = $1;
      gsub(/ /, "", ts);
      if (ts >= start && index($0, ticket) > 0) {
        match($0, /pr=([0-9]+)/, m);
        if (m[1] != "") print m[1];
      }
    }
  ' "$LOG" | tail -1)
fi

[ -z "$MERGED_PR" ] && exit 0

# 3. Query Linear for issue state + MEGA detection
ISSUE_DATA=$(curl -s --max-time 5 -X POST https://api.linear.app/graphql \
  -H "Authorization: $LINEAR_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"{ issues(filter: { identifier: { eq: \\\"$TICKET_ID\\\" } }) { nodes { id identifier state { name type } children { nodes { id } } parent { id identifier } title } } }\"}" 2>/dev/null)

[ -z "$ISSUE_DATA" ] && exit 0

ISSUE_ID=$(echo "$ISSUE_DATA" | jq -r '.data.issues.nodes[0].id // empty' 2>/dev/null)
[ -z "$ISSUE_ID" ] && exit 0

CURRENT_STATE_TYPE=$(echo "$ISSUE_DATA" | jq -r '.data.issues.nodes[0].state.type // empty' 2>/dev/null)
ISSUE_TITLE=$(echo "$ISSUE_DATA" | jq -r '.data.issues.nodes[0].title // empty' 2>/dev/null)
CHILDREN_COUNT=$(echo "$ISSUE_DATA" | jq -r '.data.issues.nodes[0].children.nodes | length' 2>/dev/null)
PARENT_ID=$(echo "$ISSUE_DATA" | jq -r '.data.issues.nodes[0].parent.identifier // empty' 2>/dev/null)

# Skip if already in terminal state
if [ "$CURRENT_STATE_TYPE" = "completed" ] || [ "$CURRENT_STATE_TYPE" = "canceled" ]; then
  exit 0
fi

# 4. MEGA detection — skip auto-close for MEGA parents
IS_MEGA=false
if [ "$CHILDREN_COUNT" -gt 0 ] || echo "$ISSUE_TITLE" | grep -q '\[MEGA\]'; then
  IS_MEGA=true
fi

if [ "$IS_MEGA" = "true" ]; then
  echo "--- Linear: $TICKET_ID is a MEGA — skipping auto-close (use /verify-mega) ---"
  exit 0
fi

# 5. Get the Done state ID
DONE_DATA=$(curl -s --max-time 5 -X POST https://api.linear.app/graphql \
  -H "Authorization: $LINEAR_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"{ workflowStates(filter: { type: { eq: \\\"completed\\\" }, team: { issues: { identifier: { eq: \\\"$TICKET_ID\\\" } } } }) { nodes { id name } } }\"}" 2>/dev/null)

DONE_STATE_ID=$(echo "$DONE_DATA" | jq -r '.data.workflowStates.nodes[0].id // empty' 2>/dev/null)
[ -z "$DONE_STATE_ID" ] && exit 0

# 6. Move to Done
RESULT=$(curl -s --max-time 5 -X POST https://api.linear.app/graphql \
  -H "Authorization: $LINEAR_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"mutation { issueUpdate(id: \\\"$ISSUE_ID\\\", input: { stateId: \\\"$DONE_STATE_ID\\\" }) { success issue { identifier state { name } } } }\"}" 2>/dev/null)

SUCCESS=$(echo "$RESULT" | jq -r '.data.issueUpdate.success // false' 2>/dev/null)

if [ "$SUCCESS" != "true" ]; then
  exit 0
fi

# 7. Add completion comment
PR_URL="https://github.com/stoa-platform/stoa/pull/${MERGED_PR}"
COMMENT_BODY="Completed in PR #${MERGED_PR} ([link](${PR_URL}))\\n\\n*Auto-closed by session-end hook*"

curl -s --max-time 5 -X POST https://api.linear.app/graphql \
  -H "Authorization: $LINEAR_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"mutation { commentCreate(input: { issueId: \\\"$ISSUE_ID\\\", body: \\\"$COMMENT_BODY\\\" }) { success } }\"}" > /dev/null 2>&1

# 8. If this is a sub-ticket of a MEGA, check if all siblings are done
if [ -n "$PARENT_ID" ]; then
  PARENT_DATA=$(curl -s --max-time 5 -X POST https://api.linear.app/graphql \
    -H "Authorization: $LINEAR_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"query\": \"{ issues(filter: { identifier: { eq: \\\"$PARENT_ID\\\" } }) { nodes { children { nodes { state { type } } } } } }\"}" 2>/dev/null)

  ALL_DONE=$(echo "$PARENT_DATA" | jq -r '[.data.issues.nodes[0].children.nodes[].state.type] | all(. == "completed")' 2>/dev/null)

  if [ "$ALL_DONE" = "true" ]; then
    echo "--- Linear: All sub-tickets of $PARENT_ID are Done — run /verify-mega $PARENT_ID to close parent ---"
  fi
fi

# Log
echo "--- Linear: $TICKET_ID → Done (PR #$MERGED_PR, session-end hook) ---"
echo "$(date +%Y-%m-%dT%H:%M) | LINEAR-CLOSE | ticket=$TICKET_ID pr=$MERGED_PR hook=stop-linear-close" >> "$LOG" 2>/dev/null

exit 0
