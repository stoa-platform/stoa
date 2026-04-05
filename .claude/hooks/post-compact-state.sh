#!/bin/bash
# PostCompact hook: Re-inject critical state after context compaction.
# Prevents "context amnesia" where Claude loses track of current task/ticket after /compact.
#
# Outputs a systemMessage that gets injected into Claude's context after compaction.
# Rollback: Remove hook entry from settings.json → back to manual re-read.

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
BRIEF="$PROJECT_DIR/.claude/session-brief.json"
MEMORY="$PROJECT_DIR/memory.md"

# Build state summary
STATE=""

# 1. Session brief (if fresh)
if [ -f "$BRIEF" ]; then
  BRIEF_AGE=$(( $(date +%s) - $(stat -f%m "$BRIEF" 2>/dev/null || stat -c%Y "$BRIEF" 2>/dev/null || echo 0) ))
  if [ "$BRIEF_AGE" -lt 600 ]; then
    CYCLE_TICKETS=$(jq -r '.cycle_tickets // [] | map(.id + " " + .title) | join(", ")' "$BRIEF" 2>/dev/null || true)
    ACTIVE_CLAIMS=$(jq -r '.active_claims // [] | map(.ticket) | join(", ")' "$BRIEF" 2>/dev/null || true)
    [ -n "$CYCLE_TICKETS" ] && STATE="${STATE}Current cycle tickets: ${CYCLE_TICKETS}\n"
    [ -n "$ACTIVE_CLAIMS" ] && STATE="${STATE}Active claims: ${ACTIVE_CLAIMS}\n"
  fi
fi

# 2. Current branch + recent commit
BRANCH=$(git -C "$PROJECT_DIR" branch --show-current 2>/dev/null || echo "unknown")
LAST_COMMIT=$(git -C "$PROJECT_DIR" log --oneline -1 2>/dev/null || echo "none")
STATE="${STATE}Branch: ${BRANCH}\nLast commit: ${LAST_COMMIT}\n"

# 3. Active ticket from branch name (extract CAB-XXXX)
TICKET=$(echo "$BRANCH" | grep -oE 'CAB-[0-9]+' | head -1)
if [ -n "$TICKET" ]; then
  STATE="${STATE}Active ticket: ${TICKET} — re-read DoD from Linear if needed.\n"
fi

# 4. IN PROGRESS items from memory.md
if [ -f "$MEMORY" ]; then
  IN_PROGRESS=$(sed -n '/IN PROGRESS/,/^##/p' "$MEMORY" 2>/dev/null | grep -E '^\s*-' | head -5 || true)
  [ -n "$IN_PROGRESS" ] && STATE="${STATE}In progress:\n${IN_PROGRESS}\n"
fi

# 5. Git hygiene: clean up stale branches (non-blocking background)
(
  cd "$PROJECT_DIR" 2>/dev/null || exit 0
  git worktree prune 2>/dev/null
  git remote prune origin 2>/dev/null
  CURRENT_BRANCH="$BRANCH"
  WT_BRANCHES=$(git worktree list --porcelain 2>/dev/null | grep '^branch ' | sed 's|branch refs/heads/||')
  for b in $(git branch --merged main 2>/dev/null | sed 's/^[* ]*//' | grep -v '^main$'); do
    [ "$b" = "$CURRENT_BRANCH" ] && continue
    echo "$WT_BRANCHES" | grep -qx "$b" && continue
    [[ "$b" == wt/* ]] && continue
    git branch -d "$b" 2>/dev/null
  done
  for b in $(git branch --format='%(refname:short) %(upstream:track)' 2>/dev/null | grep '\[gone\]$' | awk '{print $1}'); do
    [ "$b" = "$CURRENT_BRANCH" ] && continue
    echo "$WT_BRANCHES" | grep -qx "$b" && continue
    git branch -D "$b" 2>/dev/null
  done
  for wt_dir in "$PROJECT_DIR/.claude/worktrees"/agent-*; do
    [ -d "$wt_dir" ] || continue
    git worktree list 2>/dev/null | grep -q "$wt_dir" || rm -rf "$wt_dir"
  done
) &

# Output as JSON with systemMessage
if [ -n "$STATE" ]; then
  MSG=$(printf 'Post-compact state recovery:\n%s' "$STATE")
  echo "$MSG" | jq -Rs '{"systemMessage": .}'
else
  echo '{}'
fi

exit 0
