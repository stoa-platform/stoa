#!/usr/bin/env bash
# PR Hygiene — zero-token daily scan for stale/abandoned PRs.
# Labels PRs based on inactivity thresholds, outputs JSON summary.
# Usage: GH_TOKEN=$(gh auth token) bash scripts/ai-ops/pr-hygiene.sh
set -euo pipefail

REPO="${REPO:-stoa-platform/stoa}"
NOW_EPOCH=$(date +%s)

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

# --- Fetch open PRs ---
PRS=$(gh pr list --repo "$REPO" --state open --limit 100 \
  --json number,updatedAt,isDraft,author,headRefName,labels \
  2>/dev/null || echo "[]")

TOTAL=$(echo "$PRS" | jq 'length')

if [ "$TOTAL" -eq 0 ]; then
  echo '{"total":0,"stale":0,"abandoned":0,"draft":0}'
  exit 0
fi

# --- Process each PR ---
echo "$PRS" | jq -c '.[]' | while IFS= read -r pr; do
  NUM=$(echo "$pr" | jq -r '.number')
  UPDATED=$(echo "$pr" | jq -r '.updatedAt')
  AUTHOR=$(echo "$pr" | jq -r '.author.login // "unknown"')
  BRANCH=$(echo "$pr" | jq -r '.headRefName')
  LABELS=$(echo "$pr" | jq '.labels')

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
    has_label "$LABELS" "abandoned" || add_label "$NUM" "abandoned"
    has_label "$LABELS" "stale" && remove_label "$NUM" "stale"
  elif [ "$AGE_SECS" -ge "$WARN_SECS" ]; then
    has_label "$LABELS" "stale" || add_label "$NUM" "stale"
    has_label "$LABELS" "abandoned" && remove_label "$NUM" "abandoned"
  else
    has_label "$LABELS" "stale" && remove_label "$NUM" "stale"
    has_label "$LABELS" "abandoned" && remove_label "$NUM" "abandoned"
  fi
done

# --- Re-fetch for accurate counts ---
PRS_AFTER=$(gh pr list --repo "$REPO" --state open --limit 100 \
  --json number,isDraft,labels 2>/dev/null || echo "[]")

TOTAL=$(echo "$PRS_AFTER" | jq 'length')
STALE=$(echo "$PRS_AFTER" | jq '[.[] | select(.labels | any(.name == "stale"))] | length')
ABANDONED=$(echo "$PRS_AFTER" | jq '[.[] | select(.labels | any(.name == "abandoned"))] | length')
DRAFT=$(echo "$PRS_AFTER" | jq '[.[] | select(.isDraft == true)] | length')

echo "{\"total\":${TOTAL},\"stale\":${STALE},\"abandoned\":${ABANDONED},\"draft\":${DRAFT}}"
