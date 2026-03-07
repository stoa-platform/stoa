#!/usr/bin/env bash
# PR Hygiene — zero-token daily scan for stale/abandoned PRs.
# Labels PRs based on inactivity thresholds, auto-closes abandoned ones,
# and reopens their Linear tickets to prevent false-Done state.
# Usage: GH_TOKEN=$(gh auth token) bash scripts/ai-ops/pr-hygiene.sh
set -euo pipefail

REPO="${REPO:-stoa-platform/stoa}"
NOW_EPOCH=$(date +%s)
DRY_RUN="${DRY_RUN:-false}"

# --- Thresholds (seconds) ---
CLAUDE_STALE_SECS=$((48 * 3600))       # 48h
CLAUDE_ABANDON_SECS=$((7 * 86400))     # 7d
HUMAN_STALE_SECS=$((7 * 86400))        # 7d
HUMAN_ABANDON_SECS=$((30 * 86400))     # 30d

# --- Date helper (macOS + GNU compatible) ---
iso_to_epoch() {
  local dt="${1}"
  date -d "$dt" +%s 2>/dev/null || \
    python3 -c "from datetime import datetime; print(int(datetime.fromisoformat('${dt}'.replace('Z','+00:00')).timestamp()))" 2>/dev/null || \
    echo "$NOW_EPOCH"
}

# --- Is this a Claude/bot PR? ---
is_claude_pr() {
  local author="$1" branch="$2"
  [[ "$author" == "app/claude"* ]] && return 0
  [[ "$author" == "github-actions"* ]] && return 0
  [[ "$branch" == feat/cab-* ]] || [[ "$branch" == feat/CAB-* ]] && return 0
  return 1
}

# --- Label helpers (idempotent) ---
has_label() {
  local labels_json="$1" label="$2"
  echo "$labels_json" | jq -e --arg l "$label" 'any(.[]; .name == $l)' >/dev/null 2>&1
}

add_label() {
  local pr_num="$1" label="$2"
  gh pr edit "$pr_num" --repo "$REPO" --add-label "$label" 2>/dev/null || true
}

remove_label() {
  local pr_num="$1" label="$2"
  gh pr edit "$pr_num" --repo "$REPO" --remove-label "$label" 2>/dev/null || true
}

# --- Extract CAB-XXXX from PR title ---
extract_ticket_id() {
  echo "$1" | grep -oP 'CAB-\d{2,4}' | head -1 || echo ""
}

# --- Reopen a Linear ticket (Done → Todo) ---
reopen_linear_ticket() {
  local ticket_id="$1" pr_num="$2" reason="$3"

  # Source proxy library if available
  local proxy_lib
  proxy_lib="$(dirname "$0")/../ops/stoa-proxy.sh"
  # shellcheck source=/dev/null
  [[ -f "$proxy_lib" ]] && source "$proxy_lib"

  # Helper: call Linear GraphQL (proxy-first, direct fallback)
  _linear_gql() {
    local query="$1" resp_file="$2"
    if type stoa_proxy_linear_graphql &>/dev/null; then
      stoa_proxy_linear_graphql "$query" "$resp_file" && return 0
    fi
    if [[ -n "${LINEAR_API_KEY:-}" ]]; then
      curl -s -o "$resp_file" --max-time 15 \
        -X POST "https://api.linear.app/graphql" \
        -H "Content-Type: application/json" \
        -H "Authorization: ${LINEAR_API_KEY}" \
        -d "$query" 2>/dev/null && return 0
    fi
    return 1
  }

  # Check that at least one path is available
  if ! type stoa_proxy_linear_graphql &>/dev/null && [ -z "${LINEAR_API_KEY:-}" ]; then
    echo "  No Linear API path available — skipping reopen for $ticket_id"
    return 0
  fi

  local tmp_resp
  tmp_resp=$(mktemp)
  trap "rm -f '$tmp_resp'" RETURN

  # Find the issue
  _linear_gql "{\"query\": \"{ issues(filter: { identifier: { eq: \\\"$ticket_id\\\" } }) { nodes { id state { name type } } } }\"}" "$tmp_resp" || {
    echo "  Failed to query Linear for $ticket_id — skipping"
    return 0
  }

  ISSUE_ID=$(jq -r '.data.issues.nodes[0].id // empty' < "$tmp_resp")
  CURRENT_TYPE=$(jq -r '.data.issues.nodes[0].state.type // empty' < "$tmp_resp")

  if [ -z "$ISSUE_ID" ]; then
    echo "  $ticket_id not found in Linear — skipping"
    return 0
  fi

  # Only reopen if currently Done (completed)
  if [ "$CURRENT_TYPE" != "completed" ]; then
    echo "  $ticket_id is $CURRENT_TYPE (not completed) — no reopen needed"
    return 0
  fi

  # Get the "Todo" state ID
  _linear_gql "{\"query\": \"{ workflowStates(filter: { name: { eq: \\\"Todo\\\" }, team: { issues: { identifier: { eq: \\\"$ticket_id\\\" } } } }) { nodes { id name } } }\"}" "$tmp_resp" || {
    echo "  Failed to query Todo state for $ticket_id — skipping"
    return 0
  }

  TODO_STATE_ID=$(jq -r '.data.workflowStates.nodes[0].id // empty' < "$tmp_resp")

  if [ -z "$TODO_STATE_ID" ]; then
    echo "  Could not find Todo state for $ticket_id — skipping reopen"
    return 0
  fi

  if [ "$DRY_RUN" = "true" ]; then
    echo "  [DRY RUN] Would reopen $ticket_id (Done → Todo)"
    return 0
  fi

  # Move to Todo
  local mutation='mutation { issueUpdate(id: "'"$ISSUE_ID"'", input: { stateId: "'"$TODO_STATE_ID"'" }) { success } }'
  _linear_gql "{\"query\": \"$mutation\"}" "$tmp_resp" || true

  # Add comment explaining why
  local comment="Reopened automatically by PR hygiene.\n\nPR #${pr_num} was ${reason} without merging. Ticket was falsely marked Done.\n\n*Auto-reopened by pr-hygiene.sh*"
  local comment_mutation='mutation { commentCreate(input: { issueId: "'"$ISSUE_ID"'", body: "'"$comment"'" }) { success } }'
  _linear_gql "{\"query\": \"$comment_mutation\"}" "$tmp_resp" || true

  echo "  Reopened $ticket_id on Linear (Done → Todo)"
}

# --- Close an abandoned PR ---
close_abandoned_pr() {
  local pr_num="$1" title="$2"

  if [ "$DRY_RUN" = "true" ]; then
    echo "  [DRY RUN] Would close PR #$pr_num"
    return 0
  fi

  gh pr close "$pr_num" --repo "$REPO" \
    --comment "Auto-closed by PR hygiene: abandoned (no activity past threshold). Reopen if still needed." \
    2>/dev/null || true

  echo "  Closed PR #$pr_num"
}

# --- Fetch open PRs ---
PRS=$(gh pr list --repo "$REPO" --state open --limit 100 \
  --json number,title,updatedAt,isDraft,author,headRefName,labels \
  2>/dev/null || echo "[]")

TOTAL=$(echo "$PRS" | jq 'length')
CLOSED_COUNT=0
REOPENED_COUNT=0

if [ "$TOTAL" -eq 0 ]; then
  echo '{"total":0,"stale":0,"abandoned":0,"draft":0,"closed":0,"reopened":0}'
  exit 0
fi

# --- Process each PR ---
echo "$PRS" | jq -c '.[]' | while IFS= read -r pr; do
  NUM=$(echo "$pr" | jq -r '.number')
  TITLE=$(echo "$pr" | jq -r '.title')
  UPDATED=$(echo "$pr" | jq -r '.updatedAt')
  AUTHOR=$(echo "$pr" | jq -r '.author.login // "unknown"')
  BRANCH=$(echo "$pr" | jq -r '.headRefName')
  LABELS=$(echo "$pr" | jq '.labels')

  # Skip Release Please PRs
  if [[ "$BRANCH" == release-please--* ]]; then
    continue
  fi

  UPDATED_EPOCH=$(iso_to_epoch "$UPDATED")

  # Pick thresholds
  if is_claude_pr "$AUTHOR" "$BRANCH"; then
    WARN_SECS=$CLAUDE_STALE_SECS
    ABANDON_SECS=$CLAUDE_ABANDON_SECS
  else
    WARN_SECS=$HUMAN_STALE_SECS
    ABANDON_SECS=$HUMAN_ABANDON_SECS
  fi

  AGE_SECS=$((NOW_EPOCH - UPDATED_EPOCH))

  if [ "$AGE_SECS" -ge "$ABANDON_SECS" ]; then
    echo "PR #$NUM ($BRANCH) — ABANDONED (${AGE_SECS}s old)"

    # Close the PR
    close_abandoned_pr "$NUM" "$TITLE"
    CLOSED_COUNT=$((CLOSED_COUNT + 1))

    # Reopen the Linear ticket if one is referenced
    TICKET_ID=$(extract_ticket_id "$TITLE")
    if [ -n "$TICKET_ID" ]; then
      reopen_linear_ticket "$TICKET_ID" "$NUM" "abandoned"
      REOPENED_COUNT=$((REOPENED_COUNT + 1))
    fi

  elif [ "$AGE_SECS" -ge "$WARN_SECS" ]; then
    has_label "$LABELS" "stale" || add_label "$NUM" "stale"
    has_label "$LABELS" "abandoned" && remove_label "$NUM" "abandoned" || true
  else
    has_label "$LABELS" "stale" && remove_label "$NUM" "stale" || true
    has_label "$LABELS" "abandoned" && remove_label "$NUM" "abandoned" || true
  fi
done

# --- Re-fetch for accurate counts ---
PRS_AFTER=$(gh pr list --repo "$REPO" --state open --limit 100 \
  --json number,isDraft,labels 2>/dev/null || echo "[]")

TOTAL=$(echo "$PRS_AFTER" | jq 'length')
STALE=$(echo "$PRS_AFTER" | jq '[.[] | select(.labels | any(.name == "stale"))] | length')
ABANDONED=$(echo "$PRS_AFTER" | jq '[.[] | select(.labels | any(.name == "abandoned"))] | length')
DRAFT=$(echo "$PRS_AFTER" | jq '[.[] | select(.isDraft == true)] | length')

echo "{\"total\":${TOTAL},\"stale\":${STALE},\"abandoned\":${ABANDONED},\"draft\":${DRAFT},\"closed\":${CLOSED_COUNT},\"reopened\":${REOPENED_COUNT}}"
